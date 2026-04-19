"""
Chapter 1 evaluation: the spec-driven coding agent.

Runs offline. No API keys, no network. Demonstrates that the contract is
the grading rubric, not the prompt.

Usage:
    python run-eval.py

What it does:
    1. Loads the delta scenarios from golden-dataset.csv.
    2. Replays canned agent outputs through a scenario-coverage evaluator.
    3. Reports pass/fail against the invariants in spec.md.

The real agent would call an LLM via LiteLLM. That integration lives in
the notebook. Here we keep the evaluator honest and the run deterministic.
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent


@dataclass
class AgentOutput:
    """What a spec-driven agent returns. Either a patch or a structured refusal."""

    kind: str  # "patch" | "refusal"
    cites_scenario: str
    assertions_added: int = 0
    refusal_reason: str | None = None


def canned_agent(scenario: dict) -> AgentOutput:
    """Stand-in for the real agent. Behaves as a spec-driven agent should:
    implement when the delta is unambiguous, refuse when it is not.
    """
    ambiguous = "???" in (scenario["given"], scenario["when"], scenario["then"])
    if ambiguous:
        return AgentOutput(
            kind="refusal",
            cites_scenario=scenario["scenario_id"],
            refusal_reason="ambiguous_given" if scenario["given"] == "???" else "ambiguous_then",
        )
    return AgentOutput(
        kind="patch",
        cites_scenario=scenario["scenario_id"],
        assertions_added=2,
    )


def grade(scenario: dict, output: AgentOutput) -> dict:
    """Grade one agent output against one scenario."""
    expects_refusal = scenario["expected_refusal"].lower() == "true"
    expected_behaviour = scenario["expected_behaviour"]

    cites_correctly = output.cites_scenario == scenario["scenario_id"]
    refused = output.kind == "refusal"
    implemented = output.kind == "patch"

    if expects_refusal:
        passed = refused and cites_correctly and output.refusal_reason is not None
        reason = "refused_structured" if passed else "missing_refusal_or_citation"
    else:
        passed = implemented and cites_correctly and output.assertions_added > 0
        reason = "patch_with_assertions" if passed else "no_patch_or_no_assertions"

    return {
        "scenario_id": scenario["scenario_id"],
        "expected": expected_behaviour,
        "got": output.kind,
        "passed": passed,
        "reason": reason,
    }


def load_scenarios(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def main() -> int:
    scenarios = load_scenarios(HERE / "golden-dataset.csv")
    results = [grade(s, canned_agent(s)) for s in scenarios]

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    coverage = passed / total
    refusals = sum(1 for r in results if r["got"] == "refusal")
    patches = sum(1 for r in results if r["got"] == "patch")

    print("=== Chapter 1: Spec-Driven Agent Evaluation ===")
    print(f"Scenarios:          {total}")
    print(f"Passed:             {passed}")
    print(f"Patches produced:   {patches}")
    print(f"Structured refusals: {refusals}")
    print(f"Scenario coverage:  {coverage:.1%}")
    print()

    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['scenario_id']}: expected={r['expected']}, got={r['got']} ({r['reason']})")

    ok = coverage == 1.0
    print()
    if ok:
        print("PASS: spec-driven agent meets the contract.")
        print("      Every scenario covered. No spec drift. No silent failures.")
    else:
        print("FAIL: spec-driven agent violates the contract.")
        print("      Read the delta, not the prompt.")

    (HERE / "trace-example.json").read_text()  # sanity: trace present
    summary = {"total": total, "passed": passed, "coverage": coverage}
    print("\nSummary:", json.dumps(summary))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
