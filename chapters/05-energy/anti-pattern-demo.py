"""
Chapter 5 anti-pattern: the wrong tool surface.

Four failure shapes from the book, each the inverse of an invariant in spec.md:
    1. The firehose: returns the full dataset in one response. Filtering is
       pushed onto the model's context window.
    2. The single-string tool: one free-form `query` parameter that the tool
       re-parses. Structure is smuggled in a sentence, not in parameters.
    3. The silent-success tool: returns `{ok: true}` on a write that actually
       errored. No typed exception, no loud failure.
    4. The unchecked dispatcher: runs whatever tool name the model emits. No
       registry, no refusal.

Runs offline. Uses the same golden-dataset.csv as run-eval.py so the
failure surface is directly comparable to the passing version.

Usage:
    python anti-pattern-demo.py
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).parent


# -- Shared stand-in data ---------------------------------------------------
# Same tickets and orders as run-eval.py, with full bodies attached so the
# firehose tool has something bulky to return.


ORDERS = {f"ORD-{7700 + i:04d}": {"status": "shipped", "last_updated": "2026-04-16T12:00:00Z"} for i in range(60)}
ORDERS["ORD-7741"] = {"status": "processing", "last_updated": "2026-04-17T10:10:00Z"}
ORDERS["ORD-8820"] = {"status": "delivered", "last_updated": "2026-04-15T08:30:00Z"}

# Intentionally bulky. The firehose returns all of this in one call.
TICKET_BODY_FILLER = (
    "Customer reports the issue consistently across three browsers. Steps to "
    "reproduce are attached. Logs from the affected session follow. Timestamps "
    "in UTC. Related incidents cross-referenced. Retry history included. "
) * 8

ALL_TICKETS = [
    {"ticket_id": f"TCK-{5500 + i:04d}", "status": status, "title": f"Issue {i}", "body": TICKET_BODY_FILLER}
    for i, status in enumerate(["open"] * 20 + ["resolved"] * 15 + ["triage"] * 10 + ["closed"] * 5)
]


# -- Anti-pattern #1: the firehose ------------------------------------------
# Returns the full dataset. No max_rows, no summary shape, no pointer. The
# model has to filter through the blob. Context goes from healthy to
# saturated in one call.


@dataclass
class FirehoseResult:
    payload: list[dict]
    size_chars: int


def list_all_tickets() -> FirehoseResult:
    """One call. Every ticket. Full body. Model filters. Wallet burns."""
    return FirehoseResult(
        payload=ALL_TICKETS,
        size_chars=sum(len(json.dumps(t)) for t in ALL_TICKETS),
    )


# -- Anti-pattern #2: the single-string tool --------------------------------
# One parameter, typed `str`. The tool re-parses intent out of a sentence.
# Everything the pydantic models in run-eval.py enforce at the boundary is
# now enforced by regex, inside the tool, after dispatch.


@dataclass
class StringToolResult:
    tool_called: str
    parsed_args: dict
    parsed_ok: bool
    note: str


def do_helpdesk_thing(query: str) -> StringToolResult:
    """One tool, one string parameter, re-parses intent."""
    q = query.lower().strip()

    order_m = re.search(r"order\s+([a-z0-9\-]+)", q)
    if order_m:
        return StringToolResult("get_order_status", {"order_id": order_m.group(1).upper()}, True, "guessed order intent")

    cust_m = re.search(r"(cust-[a-z0-9\-]+)", q)
    if cust_m:
        return StringToolResult("get_customer_profile", {"customer_id": cust_m.group(1)}, True, "guessed customer intent")

    tkt_m = re.search(r"(tck-[a-z0-9\-]+)", q)
    if tkt_m and "escalate" in q:
        return StringToolResult("escalate_ticket", {"ticket_id": tkt_m.group(1).upper()}, True, "guessed escalate intent")

    if "open" in q or "resolved" in q or "triage" in q:
        return StringToolResult("search_tickets_by_status", {"status": "open"}, False, "status keyword detected, param defaulted")

    # Silent default. The bug. The tool ran, returned nothing, nobody knows why.
    return StringToolResult("unknown", {}, False, "parser returned nothing; default executed")


# -- Anti-pattern #3: the silent-success tool -------------------------------
# The write succeeds or fails silently. The tool returns `{ok: True}` even
# when nothing happened. The agent moves on. The ticket is not escalated.
# The queue fills up. Nobody notices for a week.


@dataclass
class SilentEscalationResult:
    ticket_id: str
    ok: bool
    what_really_happened: str  # only visible in the demo; in production this is lost


REAL_TICKET_IDS = {t["ticket_id"] for t in ALL_TICKETS}


def silent_escalate(ticket_id: str) -> SilentEscalationResult:
    """Anti-invariant: the tool returns ok=true regardless of outcome."""
    if ticket_id not in REAL_TICKET_IDS:
        # Right here, a typed exception would stop the agent cold. Instead:
        return SilentEscalationResult(
            ticket_id=ticket_id,
            ok=True,  # Lie.
            what_really_happened="no such ticket; no-op; caller told ok=true",
        )
    return SilentEscalationResult(ticket_id=ticket_id, ok=True, what_really_happened="escalated")


# -- Anti-pattern #4: the unchecked dispatcher ------------------------------
# Any tool name the model emits gets dispatched. No registry. No refusal.
# The model occasionally invents names. The side effects are whatever the
# runtime does with an unknown symbol.


REAL_TOOLS = {"get_order_status", "search_tickets_by_status", "get_customer_profile", "escalate_ticket"}


@dataclass
class UncheckedDispatchResult:
    tool_name: str
    dispatched: bool
    in_registry: bool
    side_effect: str


def unchecked_dispatcher(tool_call: dict) -> UncheckedDispatchResult:
    """No whitelist. The dispatcher runs whatever string comes in."""
    name = tool_call.get("name", "")
    return UncheckedDispatchResult(
        tool_name=name,
        dispatched=True,
        in_registry=name in REAL_TOOLS,
        side_effect=f"invoked {name}({tool_call.get('args', {})})",
    )


# -- Eval --------------------------------------------------------------------


@dataclass
class AntiPatternStats:
    firehose_chars: int = 0
    string_tool_miscalls: list[str] = field(default_factory=list)
    silent_success_lies: int = 0
    hallucinated_dispatches: list[str] = field(default_factory=list)


def main() -> None:
    with (HERE / "golden-dataset.csv").open() as f:
        rows = list(csv.DictReader(f))

    stats = AntiPatternStats()

    # 1. Firehose
    fire = list_all_tickets()
    stats.firehose_chars = fire.size_chars

    # 2. Single-string tool, replayed against the same queries run-eval.py grades
    for row in rows:
        result = do_helpdesk_thing(row["query"])
        expected_tool = row["expected_tool"]
        if expected_tool == "none":
            # Unscoped queries: the single-string tool has no way to refuse,
            # so it always invents something to do.
            if result.tool_called != "unknown":
                stats.string_tool_miscalls.append(
                    f"{row['query_id']}: unscoped query dispatched as {result.tool_called}"
                )
            continue
        if result.tool_called != expected_tool or not result.parsed_ok:
            stats.string_tool_miscalls.append(
                f"{row['query_id']}: expected {expected_tool}, got {result.tool_called} ({result.note})"
            )

    # 3. Silent-success escalate on a nonexistent ticket
    bad = silent_escalate("TCK-9999")
    if bad.ok and bad.what_really_happened.startswith("no such ticket"):
        stats.silent_success_lies += 1

    # 4. Unchecked dispatch of a tool the model invented
    hallucinated_names = ["delete_tenant_records", "sql_query", "run_shell"]
    for name in hallucinated_names:
        outcome = unchecked_dispatcher({"name": name, "args": {}})
        if outcome.dispatched and not outcome.in_registry:
            stats.hallucinated_dispatches.append(name)

    print("=== Chapter 5: Anti-Pattern (Wrong Tool Surface) ===")
    print(f"Queries replayed against the single-string tool: {len(rows)}")
    print()

    print("1. Firehose (list_all_tickets):")
    print(f"   Tickets returned in one call: {len(ALL_TICKETS)}")
    print(f"   Payload size (chars):         {stats.firehose_chars}")
    print(f"   Approx tokens at 4 chars/token: {stats.firehose_chars // 4}")
    print("   Bound in run-eval.py:         800 tokens per call")
    print(f"   Overshoot factor:             ~{(stats.firehose_chars // 4) / 800:.0f}x")
    print()

    print("2. Single-string tool (do_helpdesk_thing):")
    print(f"   Queries routed incorrectly:    {len(stats.string_tool_miscalls)}")
    for miss in stats.string_tool_miscalls:
        print(f"     - {miss}")
    print()

    print("3. Silent-success escalate (silent_escalate):")
    print(f"   Writes that reported ok=true while doing nothing: {stats.silent_success_lies}")
    print(f"     Call: silent_escalate('TCK-9999') -> ok={bad.ok}")
    print(f"     What actually happened: {bad.what_really_happened}")
    print()

    print("4. Unchecked dispatcher (unchecked_dispatcher):")
    print(f"   Hallucinated tool names dispatched: {len(stats.hallucinated_dispatches)}")
    for name in stats.hallucinated_dispatches:
        print(f"     - {name} ran without being in the registry")
    print()

    print("Four failures, one root cause:")
    print("  The tool surface encodes intent in the wrong place. A firehose")
    print("  asks the model to filter; a string parameter asks the model to")
    print("  speak SQL; a silent success hides the state of the world; an")
    print("  unchecked dispatcher trusts a generated name as an executable.")
    print()
    print("Compare to run-eval.py:")
    print("  Pydantic schemas at the boundary. Bounded outputs with pointers.")
    print("  Typed exceptions on failure. Whitelist at dispatch. The model's")
    print("  job is tool selection; the tool's job is correctness.")


if __name__ == "__main__":
    main()
