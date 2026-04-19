"""
Chapter 14 anti-pattern: the framework-coupled application.

Code that hard-codes one framework's proprietary API. When the framework is
acquired, pivoted, or absorbed, the application has to be rewritten.

Three shapes from the chapter:
    1. Direct dependency on a vendor's private SDK types.
    2. Business logic that imports framework internals.
    3. No adapter layer. Swapping frameworks means a multi-file diff.

Runs offline. Simulates a framework pivot and counts the files that would
need to change.

Usage:
    python anti-pattern-demo.py
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent


# --- Anti-pattern: application imports framework internals ---------------

class FrameworkAlphaInternals:
    """Stand-in for a framework's private types. The application ends up
    importing these directly because it feels convenient at the time.
    """

    class Query:
        def __init__(self, customer: int, since: str) -> None:
            self.customer = customer
            self.since = since

    class ResultRow:
        def __init__(self, order_id: str, total: float) -> None:
            self.order_id = order_id
            self.total = total


def fetch_orders_directly(customer_id: int, since: str) -> list[FrameworkAlphaInternals.ResultRow]:
    """Application code. Imports Query and ResultRow from the framework.
    Every call site now speaks Framework Alpha. Every call site will break
    when Framework Alpha is absorbed into a successor.
    """
    # Building the framework's Query type inline is the anti-pattern on
    # display. Every caller needs to know this private shape.
    query = FrameworkAlphaInternals.Query(customer=customer_id, since=since)
    assert query.customer == customer_id  # pretend this hits the framework
    return [
        FrameworkAlphaInternals.ResultRow(order_id="101", total=120.0),
        FrameworkAlphaInternals.ResultRow(order_id="117", total=340.0),
    ]


# --- Anti-pattern: business logic knows about framework internals --------

def summarise_spend(customer_id: int) -> float:
    """Calls the direct function, reads framework types, does arithmetic.
    A rewrite of the framework forces a rewrite of this function. This is
    how hundreds of files get coupled to one framework choice.
    """
    rows = fetch_orders_directly(customer_id, since="2026-01-01")
    # Access framework-specific attribute names. These break on framework pivot.
    return sum(row.total for row in rows)


# --- Anti-pattern: no adapter, framework mentioned by name everywhere ----

@dataclass
class AuditEvent:
    event: str
    where: str


def trace_framework_mentions() -> list[AuditEvent]:
    """Scan the anti-pattern's own source for framework name leakage.
    In a real codebase this would be grep "FrameworkAlpha" across the repo.
    """
    source = Path(__file__).read_text()
    hits = []
    for lineno, line in enumerate(source.splitlines(), 1):
        if "FrameworkAlpha" in line and "#" not in line.split("FrameworkAlpha")[0]:
            hits.append(AuditEvent(event="direct_reference", where=f"line {lineno}"))
    return hits


def main() -> None:
    # Load the timeline to demonstrate the lifecycle pressure.
    with (HERE / "golden-dataset.csv").open() as f:
        events = list(csv.DictReader(f))

    terminal = [e for e in events if e["event_type"] in {"acquired", "absorbed", "deprecated", "pivot"}]

    # Simulate the pivot hitting this codebase.
    spend = summarise_spend(customer_id=42)
    mentions = trace_framework_mentions()

    # Count the files in a plausible project that would change.
    hypothetical_call_sites = 27   # one for each service plus a few scripts
    lines_to_change_per_site = 4
    total_lines = hypothetical_call_sites * lines_to_change_per_site

    print("=== Chapter 14: Anti-Pattern (Framework-Coupled Application) ===")
    print(f"Framework events in dataset: {len(events)}")
    print(f"Terminal events (acquire/absorb/deprecate/pivot): {len(terminal)}")
    print()
    print("Example computation that works today:")
    print(f"  summarise_spend(42) = {spend}")
    print()
    print(f"Direct framework references in this one file: {len(mentions)}")
    for m in mentions[:6]:
        print(f"  - {m.event} at {m.where}")
    print()
    print("If Framework Alpha is absorbed tomorrow:")
    print(f"  call sites to migrate:   {hypothetical_call_sites}")
    print(f"  lines to change:         {total_lines}")
    print(f"  test files to rewrite:   {hypothetical_call_sites}")
    print("  release-blocking?         yes")
    print()
    print("Three shapes in play (Ch. 14):")
    print("  1. Imports vendor types into application code.")
    print("  2. Business logic depends on framework attribute names.")
    print("  3. No adapter layer. Swap cost is linear in call sites.")
    print()
    print("Fix: the adapter protocol in run-eval.py. Caller speaks the protocol;")
    print("     adapters absorb the framework's shape. Swap one line to swap the vendor.")


if __name__ == "__main__":
    main()
