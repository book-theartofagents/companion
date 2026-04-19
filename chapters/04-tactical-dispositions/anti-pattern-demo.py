"""
Chapter 4 anti-pattern: the unchecked output.

Three failure shapes from the book, all running on the same golden-dataset.csv
tickets used by run-eval.py:
    1. The string-as-contract: regex parses model output, returns empty on
       drift, downstream code treats empty as "no category".
    2. The optimistic JSON: bare `json.loads` in try/except, returns empty
       dict on failure, downstream continues with missing fields.
    3. The hallucinated tool call: no whitelist, any tool name the model
       emits gets dispatched.

Runs offline. Mirrors the field note from Chapter 4: a monitoring pipeline
lost about two percent of critical events for three weeks because the regex
failed on a reworded response and the default route was "informational".

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


# -- Shared mock model output -----------------------------------------------
# Same shapes used by run-eval.py. Here they are not corrected on retry,
# because the anti-pattern parsers have no retry loop.


def mock_raw_output(ticket_body: str, shape: str, expected_category: str, expected_priority: int) -> str:
    if shape == "clean_json":
        return json.dumps({"category": expected_category, "priority": expected_priority, "summary": ticket_body[:120]})
    if shape == "markdown_fenced_json":
        payload = json.dumps({"category": expected_category, "priority": expected_priority, "summary": ticket_body[:120]})
        return f"```json\n{payload}\n```"
    if shape == "preamble_then_json":
        payload = json.dumps({"category": expected_category, "priority": expected_priority, "summary": ticket_body[:120]})
        return f"Here's the classification:\n{payload}"
    if shape == "invalid_category":
        return json.dumps({"category": "enhancement", "priority": 2, "summary": ticket_body[:120]})
    if shape == "priority_out_of_range":
        return json.dumps({"category": expected_category, "priority": 9, "summary": ticket_body[:120]})
    if shape == "summary_too_long":
        return json.dumps({"category": expected_category, "priority": expected_priority, "summary": "x" * 240})
    if shape == "malformed_json":
        return "{category: bug, priority: 4, summary: fix me"
    if shape == "stubborn_garbage":
        return "not json"
    if shape == "empty_input":
        return ""
    # Reproduce the Ch. 4 field note: model prefixes a framing sentence.
    if shape == "reworded":
        return f"The category of this ticket is {expected_category}, with priority {expected_priority}."
    return ""


# -- Anti-pattern #1: regex parsing -----------------------------------------
# The monitoring pipeline in the book's field note. Regex matched on
# "Severity: critical". When the model wrote "The severity of this event is
# critical, because..." the regex returned nothing. Empty string routed to
# the default queue. Three weeks, thirty-eight missed critical events.


CATEGORY_REGEX = re.compile(r'"category"\s*:\s*"([a-z]+)"')


@dataclass
class RegexResult:
    category: str  # may be "" on regex miss; downstream treats as "noise"
    priority: int  # may be 0 on miss; downstream treats as "low"
    parsed_ok: bool


def regex_parser(raw: str) -> RegexResult:
    """String-as-contract. The regex is the parser. When the shape drifts,
    the regex returns nothing and the downstream system silently defaults.
    """
    m = CATEGORY_REGEX.search(raw)
    category = m.group(1) if m else ""
    pm = re.search(r'"priority"\s*:\s*(\d+)', raw)
    priority = int(pm.group(1)) if pm else 0
    return RegexResult(category=category, priority=priority, parsed_ok=bool(m and pm))


# -- Anti-pattern #2: optimistic JSON ---------------------------------------
# try/except around json.loads returning an empty dict. The empty dict looks
# like "no data present" to the downstream system. The system treats it as
# normal. The warning log accumulates. Nobody reads the warning log.


@dataclass
class OptimisticResult:
    data: dict
    parsed_ok: bool


def optimistic_json_parser(raw: str) -> OptimisticResult:
    try:
        return OptimisticResult(data=json.loads(raw), parsed_ok=True)
    except Exception:
        # This is the bug. "Handled" means swallowed.
        return OptimisticResult(data={}, parsed_ok=False)


# -- Anti-pattern #3: hallucinated tool call --------------------------------
# The agent emits a tool call. The dispatcher runs whatever comes in. No
# whitelist. The model occasionally invents a tool name.


REAL_TOOLS = {"escalate_ticket", "close_ticket", "tag_ticket"}


@dataclass
class ToolDispatchResult:
    tool_name: str
    dispatched: bool
    side_effect: str


def unchecked_dispatcher(tool_call: dict) -> ToolDispatchResult:
    """No whitelist. The dispatcher runs whatever comes in.

    Compare the whitelist version in the book's Ch. 5 MCP discussion.
    """
    name = tool_call.get("name", "")
    # Runs even if the name is not in REAL_TOOLS. That is the bug.
    return ToolDispatchResult(
        tool_name=name,
        dispatched=True,
        side_effect=f"invoked {name}({tool_call.get('args', {})})",
    )


# -- Eval --------------------------------------------------------------------


@dataclass
class AntiPatternStats:
    parsed_ok: int = 0
    silently_empty: int = 0
    category_correct: int = 0
    missed_critical: list[str] = field(default_factory=list)


def main() -> None:
    with (HERE / "golden-dataset.csv").open() as f:
        rows = list(csv.DictReader(f))

    regex_stats = AntiPatternStats()
    optimistic_stats = AntiPatternStats()

    # Add a synthetic "reworded" case to mirror the Ch. 4 field note: the
    # model prefixes a framing sentence around the JSON. Regex misses it.
    reworded_cases = [
        {
            "ticket_id": "T-FIELDNOTE-1",
            "ticket_body": "Database write failed with authentication error",
            "first_attempt_shape": "reworded",
            "expected_category": "bug",
            "expected_priority": 5,
        }
    ]
    combined = rows + reworded_cases

    for row in combined:
        raw = mock_raw_output(
            row["ticket_body"],
            row["first_attempt_shape"],
            row["expected_category"],
            int(row["expected_priority"]),
        )
        expected_priority = int(row["expected_priority"])

        # Regex anti-pattern
        rx = regex_parser(raw)
        if rx.parsed_ok:
            regex_stats.parsed_ok += 1
        else:
            regex_stats.silently_empty += 1
        if rx.category == row["expected_category"]:
            regex_stats.category_correct += 1
        # Field note: critical events routed to default because regex missed.
        if expected_priority == 5 and rx.category != row["expected_category"]:
            regex_stats.missed_critical.append(row["ticket_id"])

        # Optimistic JSON anti-pattern
        opt = optimistic_json_parser(raw)
        if opt.parsed_ok:
            optimistic_stats.parsed_ok += 1
        else:
            optimistic_stats.silently_empty += 1
        if opt.data.get("category") == row["expected_category"]:
            optimistic_stats.category_correct += 1
        if expected_priority == 5 and opt.data.get("category") != row["expected_category"]:
            optimistic_stats.missed_critical.append(row["ticket_id"])

    # Hallucinated tool call: model emits one that does not exist.
    hallucinated = unchecked_dispatcher({"name": "delete_tenant_records", "args": {"confirm": True}})

    print("=== Chapter 4: Anti-Pattern (Unchecked Output) ===")
    print(f"Tickets replayed:   {len(combined)}")
    print()

    print("String-as-contract (regex parsing):")
    print(f"  Parsed OK:              {regex_stats.parsed_ok}")
    print(f"  Silently returned empty: {regex_stats.silently_empty}")
    print(f"  Category correct:       {regex_stats.category_correct}/{len(combined)}")
    print(f"  Critical tickets missed: {len(regex_stats.missed_critical)} {regex_stats.missed_critical}")
    print()

    print("Optimistic JSON (bare try/except):")
    print(f"  Parsed OK:              {optimistic_stats.parsed_ok}")
    print(f"  Silently returned {{}}:  {optimistic_stats.silently_empty}")
    print(f"  Category correct:       {optimistic_stats.category_correct}/{len(combined)}")
    print(f"  Critical tickets missed: {len(optimistic_stats.missed_critical)} {optimistic_stats.missed_critical}")
    print()

    print("Hallucinated tool call (no whitelist):")
    print(f"  Tool emitted by model:  {hallucinated.tool_name}")
    print(f"  In REAL_TOOLS set:      {hallucinated.tool_name in REAL_TOOLS}")
    print(f"  Dispatched anyway:      {hallucinated.dispatched}")
    print(f"  Side effect:            {hallucinated.side_effect}")
    print()

    print("Three failures, one root cause:")
    print("  Model output is trusted as if it were structured. It is a string.")
    print("  The schema-less parsers cannot distinguish drift from emptiness.")
    print("  Empty is treated as `no problem`. Drift accumulates silently for weeks.")
    print()
    print("Compare to run-eval.py:")
    print("  Pydantic schema at the boundary. ValidationError becomes retry feedback.")
    print("  No malformed data reaches the caller. Budget exhausted raises visibly.")


if __name__ == "__main__":
    main()
