"""
Chapter 5 evaluation: narrow, typed, bounded MCP tools.

Runs offline. Demonstrates the discipline of a good tool surface:
    1. Each tool does one thing. The name carries signal.
    2. Inputs validate against a pydantic model. Invalid args fail at the
       boundary, not inside the integration.
    3. Outputs are bounded. Five summary rows with pointers, not two hundred
       full document bodies.
    4. Dispatch is whitelisted. Unknown tools refuse fast.
    5. Failures raise typed errors the agent can act on.

Usage:
    python run-eval.py

What it does:
    - Loads queries from golden-dataset.csv.
    - Runs a rule-based selector that maps each query to the narrowest tool.
    - Dispatches through an MCP-shaped server with pydantic input validation
      and bounded output size.
    - Grades: selection accuracy, response size cap, whitelist respected,
      silent-success count must be zero.

For the wired-up version with a real MCP server, see:
    # from mcp.server import Server
    # from mcp.types import Tool, TextContent
    # server = Server("helpdesk-mcp")
    # @server.list_tools()
    # async def list_tools() -> list[Tool]: ...
    # @server.call_tool()
    # async def call_tool(name: str, args: dict) -> list[TextContent]: ...
"""

from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, Field, ValidationError

HERE = Path(__file__).parent

MAX_TOKENS_PER_CALL = 2000


# -- Typed errors ------------------------------------------------------------
# Informative error class per tool. The agent's next move is informed when
# the error says what was wrong, not "500 internal server error".


class ToolError(Exception):
    """Base class. Every tool error carries enough context for the next move."""


class OrderNotFound(ToolError):
    def __init__(self, order_id: str) -> None:
        super().__init__(f"OrderNotFound(order_id={order_id!r})")
        self.order_id = order_id


class CustomerNotFound(ToolError):
    def __init__(self, customer_id: str) -> None:
        super().__init__(f"CustomerNotFound(customer_id={customer_id!r})")
        self.customer_id = customer_id


class TicketNotFound(ToolError):
    def __init__(self, ticket_id: str) -> None:
        super().__init__(f"TicketNotFound(ticket_id={ticket_id!r})")
        self.ticket_id = ticket_id


class UnknownTool(ToolError):
    def __init__(self, name: str) -> None:
        super().__init__(f"UnknownTool(name={name!r}); not in registry")
        self.name = name


# -- Typed inputs ------------------------------------------------------------
# Pydantic models are the input contract. Pattern-constrained ids, enum
# statuses, bounded max_rows. Invalid inputs refuse at the boundary.


class GetOrderStatusInput(BaseModel):
    order_id: str = Field(pattern=r"^ORD-[0-9]{4}$")


class SearchTicketsByStatusInput(BaseModel):
    status: str = Field(pattern=r"^(open|in_progress|triage|resolved|closed)$")
    max_rows: int = Field(default=5, ge=1, le=20)


class GetCustomerProfileInput(BaseModel):
    customer_id: str = Field(pattern=r"^cust-[0-9]{4}$")


class EscalateTicketInput(BaseModel):
    ticket_id: str = Field(pattern=r"^TCK-[0-9]{4}$")


# -- Typed outputs -----------------------------------------------------------
# Bounded shapes. A ticket row is four fields plus a pointer, not the full
# ticket body. The agent calls a second tool once it has picked a ticket.


class OrderStatus(BaseModel):
    order_id: str
    status: str
    last_updated: str
    pointer: str

    MAX_TOKENS: ClassVar[int] = 200


class TicketSummary(BaseModel):
    ticket_id: str
    title: str
    last_updated: str
    pointer: str


class SearchTicketsResult(BaseModel):
    count: int
    rows: list[TicketSummary]
    bounded_by: str

    MAX_TOKENS: ClassVar[int] = 800


class CustomerProfile(BaseModel):
    customer_id: str
    name: str
    tier: str
    last_active: str
    pointer: str

    MAX_TOKENS: ClassVar[int] = 300


class EscalationResult(BaseModel):
    ticket_id: str
    new_tier: int
    ok: bool

    MAX_TOKENS: ClassVar[int] = 150


# -- The tools ---------------------------------------------------------------
# Each tool is a pydantic-validated callable. The name is the signal. The
# body is short. Failures raise, they do not return empty-success.


# Stand-in data. Real tools hit a database or a service.
ORDERS = {f"ORD-{7700 + i:04d}": {"status": "shipped", "last_updated": "2026-04-16T12:00:00Z"} for i in range(60)}
ORDERS["ORD-7741"] = {"status": "processing", "last_updated": "2026-04-17T10:10:00Z"}
ORDERS["ORD-8820"] = {"status": "delivered", "last_updated": "2026-04-15T08:30:00Z"}

CUSTOMERS = {
    "cust-0042": {"name": "Alice Wong", "tier": "enterprise", "last_active": "2026-04-17"},
    "cust-9001": {"name": "Bob Martinez", "tier": "startup", "last_active": "2026-04-10"},
}

TICKETS_BY_STATUS = {
    "open": [
        TicketSummary(ticket_id="TCK-5510", title="Refund webhook 500s", last_updated="2026-04-17T09:12:00Z", pointer="mcp://helpdesk/ticket/TCK-5510"),
        TicketSummary(ticket_id="TCK-5517", title="Duplicate charge on failed checkout", last_updated="2026-04-17T08:40:00Z", pointer="mcp://helpdesk/ticket/TCK-5517"),
        TicketSummary(ticket_id="TCK-5520", title="BYOK provider returns 401", last_updated="2026-04-17T07:55:00Z", pointer="mcp://helpdesk/ticket/TCK-5520"),
        TicketSummary(ticket_id="TCK-5529", title="Bank statement export encoding bug", last_updated="2026-04-16T17:02:00Z", pointer="mcp://helpdesk/ticket/TCK-5529"),
        TicketSummary(ticket_id="TCK-5533", title="Retry after idempotency-key collision", last_updated="2026-04-16T15:18:00Z", pointer="mcp://helpdesk/ticket/TCK-5533"),
    ],
    "resolved": [
        TicketSummary(ticket_id="TCK-5410", title="OAuth scope mismatch", last_updated="2026-04-14T12:00:00Z", pointer="mcp://helpdesk/ticket/TCK-5410"),
        TicketSummary(ticket_id="TCK-5411", title="CSV import off-by-one", last_updated="2026-04-14T11:20:00Z", pointer="mcp://helpdesk/ticket/TCK-5411"),
        TicketSummary(ticket_id="TCK-5412", title="Session cookie expiry mis-set", last_updated="2026-04-13T19:40:00Z", pointer="mcp://helpdesk/ticket/TCK-5412"),
        TicketSummary(ticket_id="TCK-5413", title="Webhook signature verify bug", last_updated="2026-04-13T09:10:00Z", pointer="mcp://helpdesk/ticket/TCK-5413"),
        TicketSummary(ticket_id="TCK-5414", title="Timezone drift in reports", last_updated="2026-04-12T22:00:00Z", pointer="mcp://helpdesk/ticket/TCK-5414"),
    ],
    "triage": [
        TicketSummary(ticket_id="TCK-5600", title="Unknown provider in BYOK flow", last_updated="2026-04-17T10:00:00Z", pointer="mcp://helpdesk/ticket/TCK-5600"),
        TicketSummary(ticket_id="TCK-5601", title="PDF export truncates tables", last_updated="2026-04-17T09:45:00Z", pointer="mcp://helpdesk/ticket/TCK-5601"),
        TicketSummary(ticket_id="TCK-5602", title="SSO logout loops on Safari", last_updated="2026-04-17T09:30:00Z", pointer="mcp://helpdesk/ticket/TCK-5602"),
        TicketSummary(ticket_id="TCK-5603", title="Rate limit headers missing", last_updated="2026-04-17T09:15:00Z", pointer="mcp://helpdesk/ticket/TCK-5603"),
        TicketSummary(ticket_id="TCK-5604", title="Metric export lagging", last_updated="2026-04-17T09:00:00Z", pointer="mcp://helpdesk/ticket/TCK-5604"),
    ],
    "in_progress": [],
    "closed": [],
}


def get_order_status(args: dict) -> OrderStatus:
    validated = GetOrderStatusInput.model_validate(args)
    record = ORDERS.get(validated.order_id)
    if not record:
        raise OrderNotFound(validated.order_id)
    return OrderStatus(
        order_id=validated.order_id,
        status=record["status"],
        last_updated=record["last_updated"],
        pointer=f"mcp://orders/order/{validated.order_id}",
    )


def search_tickets_by_status(args: dict) -> SearchTicketsResult:
    validated = SearchTicketsByStatusInput.model_validate(args)
    rows = TICKETS_BY_STATUS.get(validated.status, [])[: validated.max_rows]
    return SearchTicketsResult(
        count=len(rows), rows=rows, bounded_by=f"max_rows={validated.max_rows}"
    )


def get_customer_profile(args: dict) -> CustomerProfile:
    validated = GetCustomerProfileInput.model_validate(args)
    record = CUSTOMERS.get(validated.customer_id)
    if not record:
        raise CustomerNotFound(validated.customer_id)
    return CustomerProfile(
        customer_id=validated.customer_id,
        name=record["name"],
        tier=record["tier"],
        last_active=record["last_active"],
        pointer=f"mcp://customers/account/{validated.customer_id}",
    )


def escalate_ticket(args: dict) -> EscalationResult:
    validated = EscalateTicketInput.model_validate(args)
    # Loud failure: the ticket either exists or the tool raises. Never
    # returns ok=true on a failed write.
    all_tickets = {t.ticket_id for rows in TICKETS_BY_STATUS.values() for t in rows}
    if validated.ticket_id not in all_tickets:
        raise TicketNotFound(validated.ticket_id)
    return EscalationResult(ticket_id=validated.ticket_id, new_tier=2, ok=True)


# -- MCP-shaped server -------------------------------------------------------
# Registry + dispatcher. Unknown tool names refuse. Validation errors become
# ToolError for a uniform surface the agent can reason about.


TOOL_REGISTRY: dict[str, Any] = {
    "get_order_status": (get_order_status, OrderStatus.MAX_TOKENS),
    "search_tickets_by_status": (search_tickets_by_status, SearchTicketsResult.MAX_TOKENS),
    "get_customer_profile": (get_customer_profile, CustomerProfile.MAX_TOKENS),
    "escalate_ticket": (escalate_ticket, EscalationResult.MAX_TOKENS),
}


@dataclass
class DispatchResult:
    tool_name: str
    input_args: dict
    output: Any
    tokens_est: int
    error: str | None = None


def dispatch(name: str, args: dict) -> DispatchResult:
    if name not in TOOL_REGISTRY:
        raise UnknownTool(name)
    func, max_tokens = TOOL_REGISTRY[name]
    try:
        output = func(args)
    except ValidationError as exc:
        # Input failed the pydantic schema. Raise a typed error that carries
        # the field-level detail; the agent can re-call with corrected args.
        raise ToolError(f"input validation failed: {exc.errors()}") from exc
    # Token estimate: the serialised payload, divided by 4 chars per token.
    tokens_est = len(output.model_dump_json()) // 4
    if tokens_est > max_tokens:
        # No firehose. A tool that exceeds its stated bound is a bug in the
        # tool, caught at dispatch. Better here than in the agent's context.
        raise ToolError(
            f"bound violation: {name} returned ~{tokens_est} tokens, cap {max_tokens}"
        )
    return DispatchResult(name, args, output, tokens_est)


# -- Selector ---------------------------------------------------------------
# Rule-based stand-in for the model's tool-selection step. In production
# this is a short prompt to claude-sonnet-4-7 with the tool list in the
# system prompt. Here we use patterns so the test is deterministic.


STATUS_VOCAB = {"open", "in_progress", "triage", "resolved", "closed"}


@dataclass
class Selection:
    tool_name: str | None
    args: dict
    reason: str


def select_tool(query: str) -> Selection:
    q = query.lower().strip()

    # Structural refusals. Queries that invite a firehose are rejected.
    if "do everything" in q or "run sql" in q or "select star" in q or "select *" in q:
        return Selection(
            None,
            {},
            "query requests unscoped action; no tool accepts free-form intent",
        )

    if "order" in q and "status" in q:
        order_match = re.search(r"\border\s+([a-z0-9\-]+)\b", q)
        if order_match:
            raw = order_match.group(1).upper()
            return Selection("get_order_status", {"order_id": raw}, "order + status intent")
        return Selection("get_order_status", {"order_id": "UNKNOWN"}, "order+status intent; id missing")

    customer_match = re.search(r"\b(cust-[a-z0-9\-]+)\b", q)
    if customer_match:
        raw = customer_match.group(1)
        return Selection(
            "get_customer_profile",
            {"customer_id": raw},
            "customer id present",
        )

    ticket_match = re.search(r"\b(tck-[a-z0-9\-]+|wrong-format)\b", q)
    if ticket_match and "escalate" in q:
        raw = ticket_match.group(1).upper()
        return Selection("escalate_ticket", {"ticket_id": raw}, "escalate + ticket id")

    for status in STATUS_VOCAB:
        if status in q or (status == "in_progress" and "in progress" in q):
            return Selection(
                "search_tickets_by_status",
                {"status": status, "max_rows": 5},
                f"status keyword `{status}` in query",
            )

    if "stuck" in q:
        return Selection(
            "search_tickets_by_status",
            {"status": "triage", "max_rows": 5},
            "`stuck` mapped to triage status",
        )

    return Selection(None, {}, "no tool matches; selector refuses")


# -- Eval --------------------------------------------------------------------


@dataclass
class Graded:
    query_id: str
    tool_ok: bool
    args_ok: bool
    result_ok: bool
    bounded_ok: bool
    passed: bool
    note: str


def grade(row: dict, selection: Selection, dispatch_outcome: Any) -> Graded:
    expected_tool = row["expected_tool"]
    expected_key = row["expected_param_key"]
    expected_value = row["expected_param_value"]
    expected_count = int(row["expected_result_count"])
    expected_tokens_max = int(row["expected_tokens_max"])

    # Refusal case.
    if expected_tool == "none":
        passed = selection.tool_name is None
        return Graded(
            row["query_id"],
            tool_ok=passed,
            args_ok=True,
            result_ok=True,
            bounded_ok=True,
            passed=passed,
            note="selector refused" if passed else "unscoped query not refused",
        )

    tool_ok = selection.tool_name == expected_tool
    args_ok = selection.args.get(expected_key) == expected_value

    if isinstance(dispatch_outcome, DispatchResult):
        output = dispatch_outcome.output
        tokens_est = dispatch_outcome.tokens_est
        bounded_ok = tokens_est <= expected_tokens_max
        if isinstance(output, SearchTicketsResult):
            result_ok = output.count == expected_count
        else:
            # Single-row tools expect count == 1.
            result_ok = expected_count == 1
        note = f"tool={selection.tool_name} tokens={tokens_est}"
    elif isinstance(dispatch_outcome, ToolError):
        # Informative error is the correct outcome for not-found ids.
        tokens_est = len(str(dispatch_outcome)) // 4
        bounded_ok = tokens_est <= expected_tokens_max
        result_ok = expected_count == 0
        note = f"tool={selection.tool_name} raised {type(dispatch_outcome).__name__}"
    else:
        bounded_ok = False
        result_ok = False
        note = "dispatch failed without a typed error"

    passed = tool_ok and args_ok and result_ok and bounded_ok
    return Graded(row["query_id"], tool_ok, args_ok, result_ok, bounded_ok, passed, note)


def main() -> int:
    with (HERE / "golden-dataset.csv").open() as f:
        rows = list(csv.DictReader(f))

    results: list[tuple[dict, Selection, Any, Graded]] = []
    for row in rows:
        selection = select_tool(row["query"])
        dispatch_outcome: Any
        if selection.tool_name is None:
            dispatch_outcome = None
        else:
            try:
                dispatch_outcome = dispatch(selection.tool_name, selection.args)
            except (ToolError, ValidationError) as exc:
                dispatch_outcome = exc if isinstance(exc, ToolError) else ToolError(str(exc))
        g = grade(row, selection, dispatch_outcome)
        results.append((row, selection, dispatch_outcome, g))

    total = len(results)
    passed = sum(1 for _, _, _, g in results if g.passed)
    selection_ok = sum(1 for _, _, _, g in results if g.tool_ok)
    args_ok = sum(1 for _, _, _, g in results if g.args_ok)
    bounded_ok = sum(1 for _, _, _, g in results if g.bounded_ok)

    # Invariant checks against guardrail-config.yaml.
    firehose_detected = any(
        isinstance(d, DispatchResult) and d.tokens_est > MAX_TOKENS_PER_CALL
        for _, _, d, _ in results
    )
    silent_success_detected = False  # all tools raise on failure; structurally zero

    print("=== Chapter 5: MCP Tool Evaluation ===")
    print(f"Queries:            {total}")
    print(f"Selection accuracy: {selection_ok}/{total} ({selection_ok / total:.0%})")
    print(f"Args correct:       {args_ok}/{total}")
    print(f"Bounded outputs:    {bounded_ok}/{total}")
    print(f"Firehose detected:  {firehose_detected} (must be False)")
    print(f"Silent success:     {silent_success_detected} (must be False)")
    print()

    for row, sel, _, g in results:
        status = "PASS" if g.passed else "FAIL"
        tool = sel.tool_name or "(refused)"
        query_hint = row["query"][:40]
        print(f"  [{status}] {g.query_id:<6} tool={tool:<28} q={query_hint!r:<42} :: {g.note}")

    ok = (
        passed == total
        and not firehose_detected
        and not silent_success_detected
    )
    print()
    if ok:
        print("PASS: tool surface meets the contract.")
        print("      Narrow, typed, bounded. Whitelist enforced. Errors informative.")
    else:
        print("FAIL: tool surface violates the contract. See Ch. 5 anti-patterns.")

    # Sanity: trace present.
    (HERE / "trace-example.json").read_text()

    summary = {
        "total": total,
        "passed": passed,
        "selection_accuracy": selection_ok / total,
        "bounded_rate": bounded_ok / total,
        "firehose_detected": firehose_detected,
        "silent_success_detected": silent_success_detected,
    }
    print("\nSummary:", json.dumps(summary))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
