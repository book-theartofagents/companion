"""
Chapter 14 evaluation: framework timeline analyser and adapter protocol.

Runs offline. Two outputs in one script:
    1. Survivability report over a dataset of real events from 2022-2026.
    2. Adapter protocol demo: same call runs against two implementations.

Usage:
    python run-eval.py

The lesson from the chapter is procedural: frameworks are mortal, protocols
outlast them. The report measures the ecology. The adapter shows how to
code for it.
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

HERE = Path(__file__).parent


# --- Framework timeline analyser ------------------------------------------

@dataclass
class ProjectState:
    project: str
    current_state: str   # ACTIVE | ACQUIRED | PIVOTED | DEPRECATED | ABSORBED | PROTOCOL
    governance: str
    bus_factor: str      # high | medium | low
    last_event: str
    last_event_date: str


STATE_PRIORITY = {
    # Later events override earlier ones when both are terminal.
    "launch": 0,
    "adoption": 1,
    "people_move": 1,
    "commercial": 1,
    "pivot": 2,
    "acquired": 3,
    "absorbed": 4,
    "deprecated": 5,
    "protocol": 6,
}

STATE_MAP = {
    "launch": "ACTIVE",
    "adoption": "ACTIVE",
    "people_move": "ACTIVE",
    "commercial": "ACTIVE",
    "pivot": "PIVOTED",
    "acquired": "ACQUIRED",
    "absorbed": "ABSORBED",
    "deprecated": "DEPRECATED",
    "protocol": "PROTOCOL",
}


def classify(events: list[dict]) -> dict[str, ProjectState]:
    """One row in, one state out per project. Later terminal events win.
    The rule is mechanical: look at the events, pick the highest priority.
    No judgement, no folklore.
    """
    by_project: dict[str, list[dict]] = {}
    for row in events:
        by_project.setdefault(row["project"], []).append(row)

    out: dict[str, ProjectState] = {}
    for project, rows in by_project.items():
        rows.sort(key=lambda r: (STATE_PRIORITY.get(r["event_type"], 0), r["event_date"]))
        winner = rows[-1]
        out[project] = ProjectState(
            project=project,
            current_state=STATE_MAP.get(winner["event_type"], "ACTIVE"),
            governance=winner["governance"],
            bus_factor=winner["bus_factor"],
            last_event=winner["event_type"],
            last_event_date=winner["event_date"],
        )
    return out


def report(states: dict[str, ProjectState]) -> dict:
    counts: dict[str, int] = {}
    for s in states.values():
        counts[s.current_state] = counts.get(s.current_state, 0) + 1
    bus_factor_low = [s.project for s in states.values() if s.bus_factor == "low"]
    standards_backed = [s.project for s in states.values() if s.governance == "standards_body"]
    return {
        "projects": len(states),
        "state_counts": counts,
        "bus_factor_low": bus_factor_low,
        "standards_backed": standards_backed,
    }


# --- Adapter protocol demo ------------------------------------------------
# The caller speaks one protocol. The framework sits behind an adapter.
# Swap the adapter, the caller does not notice.

class ToolAdapter(Protocol):
    """The protocol. Every framework has to satisfy this shape."""

    def search_orders(self, customer_id: int, since: str) -> list[dict]: ...
    def framework_name(self) -> str: ...


class FrameworkAlphaAdapter:
    """Stand-in for a framework with its own conventions. Real frameworks
    rename arguments and wrap returns in their own types. Here we keep
    shapes identical on purpose so the output comparison is meaningful.
    """

    def search_orders(self, customer_id: int, since: str) -> list[dict]:
        # Framework Alpha speaks in camelCase with a wrapper object.
        native = {
            "customerId": customer_id,
            "sinceDate": since,
            "rows": [
                {"orderId": 101, "total": 120.0},
                {"orderId": 117, "total": 340.0},
                {"orderId": 133, "total": 80.0},
            ],
        }
        # Adapter translates to the protocol's shape.
        return [
            {"order_id": r["orderId"], "total": r["total"]}
            for r in native["rows"]
        ]

    def framework_name(self) -> str:
        return "framework_alpha"


class FrameworkBetaAdapter:
    """Stand-in for a different framework. Native output shape differs. The
    adapter absorbs the difference.
    """

    def search_orders(self, customer_id: int, since: str) -> list[dict]:
        native = {
            "query": {"customer": customer_id, "from": since},
            "results": [
                ("101", 120.0),
                ("117", 340.0),
                ("133", 80.0),
            ],
        }
        return [
            {"order_id": int(row[0]), "total": row[1]}
            for row in native["results"]
        ]

    def framework_name(self) -> str:
        return "framework_beta"


def caller(adapter: ToolAdapter) -> list[dict]:
    """Application code. Knows the protocol, nothing else. This function
    does not change when the adapter changes.
    """
    return adapter.search_orders(customer_id=42, since="2026-01-01")


# --- Wire it up -----------------------------------------------------------

def main() -> int:
    # 1. Timeline analysis.
    with (HERE / "golden-dataset.csv").open() as f:
        events = list(csv.DictReader(f))

    states = classify(events)
    rep = report(states)

    print("=== Chapter 14: Framework Timeline Analyser ===")
    print(f"Events loaded:      {len(events)}")
    print(f"Projects tracked:   {rep['projects']}")
    print()
    print("-- State distribution --")
    for state, count in sorted(rep["state_counts"].items()):
        print(f"  {state:<11s} {count}")
    print()
    print("-- Bus factor low (plan for continuity) --")
    for name in sorted(rep["bus_factor_low"]):
        s = states[name]
        print(f"  {name}  state={s.current_state}  last={s.last_event} on {s.last_event_date}")
    print()
    print("-- Standards-backed --")
    for name in sorted(rep["standards_backed"]):
        s = states[name]
        print(f"  {name}  governance={s.governance}  last={s.last_event} on {s.last_event_date}")
    print()

    for name in sorted(states):
        s = states[name]
        print(
            f"  {name:<26s} state={s.current_state:<10s} "
            f"gov={s.governance:<20s} bus={s.bus_factor:<6s} "
            f"last={s.last_event} on {s.last_event_date}"
        )

    # 2. Adapter demo. Same caller, two adapters.
    print()
    print("=== Adapter Protocol Demo ===")

    alpha = FrameworkAlphaAdapter()
    beta = FrameworkBetaAdapter()

    out_alpha = caller(alpha)
    out_beta = caller(beta)

    print(f"framework_alpha returned: {out_alpha}")
    print(f"framework_beta  returned: {out_beta}")

    shapes_match = out_alpha == out_beta
    print(f"Shapes match:   {shapes_match}  (caller does not notice the swap)")

    # 3. Invariant check.
    required_states = {"ACTIVE", "ACQUIRED", "PIVOTED", "ABSORBED", "PROTOCOL"}
    present_states = set(rep["state_counts"].keys())
    missing = required_states - present_states

    ok = (
        not missing
        and shapes_match
        and len(rep["bus_factor_low"]) >= 1
        and len(rep["standards_backed"]) >= 1
    )

    print()
    if ok:
        print("PASS: ecology classified, protocol survives the swap.")
    else:
        print("FAIL: either a state is missing or the adapter did not hold.")
        if missing:
            print(f"      Missing states: {sorted(missing)}")

    summary = {
        "projects": rep["projects"],
        "states": rep["state_counts"],
        "bus_factor_low_count": len(rep["bus_factor_low"]),
        "standards_backed_count": len(rep["standards_backed"]),
        "adapter_swap_transparent": shapes_match,
    }
    print("\nSummary:", json.dumps(summary))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
