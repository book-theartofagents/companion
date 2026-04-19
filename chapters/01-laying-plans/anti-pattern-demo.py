"""
Chapter 1 anti-pattern: the unanchored agent.

Shows what happens when the prompt is the spec. No delta above it, no scenario
ids, no structured refusal, no way to regress when the model updates.

Runs offline. Contrasts three anti-patterns from the book:
    1. Awesome prompts repository (stacked prompts, no contract above them)
    2. The God Prompt (4000 words, contradictions, geological record of incidents)
    3. Prompt-as-code without spec-as-source (intent buried in application code)

Usage:
    python anti-pattern-demo.py
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent


# -- Anti-pattern #1: the Awesome Prompts repo -----------------------------
# A public repo of "role prompts" collapsed into a single dict. In production
# these disagree with each other. Nothing arbitrates.
AWESOME_PROMPTS = {
    "senior_backend": "You are a senior backend engineer. Be thorough. Sanitise all inputs.",
    "security_reviewer": "You are a paranoid security reviewer. Reject any user-supplied input.",
    "shipper": "You are a pragmatic engineer. Ship fast. Avoid over-engineering.",
}


# -- Anti-pattern #2: the God Prompt ---------------------------------------
# Six months of production incidents compressed into a single string. Each
# paragraph fixes a specific failure and introduces two new ambiguities.
GOD_PROMPT = """\
You are a helpful coding assistant.
Always write tests.
Do not write tests for trivial changes.
Prefer short functions.
Prefer functions that are clear even if long.
Never invent requirements.
If the request is ambiguous, make your best guess.
Apologise if you are uncertain.
Be confident in your answers.
Be humble.
Never break existing tests.
Fix broken tests if needed.
(Added by Alice, 2025-11-04 after the retry-storm incident.)
(Added by Bob, 2026-01-18 after the accidental rm -rf.)
""" * 3  # the real one is longer


# -- Anti-pattern #3: prompts-as-code ------------------------------------
# Intent lives in Python strings, drift happens in diffs, review is
# proportionate to code but wildly disproportionate to intent.
class PaymentAgent:
    def __init__(self) -> None:
        self.prompt = (
            "Process the payment. "
            "If the amount is over 10000, require manager approval. "
            # 2025-09-12: changed from 5000 after finance complained
            # 2026-01-03: added "manager" because "approval" was ambiguous
            # 2026-02-19: still ambiguous, but nobody remembers why
            "Handle errors gracefully."
        )


@dataclass
class UnanchoredOutput:
    text: str
    cites_scenario: str | None = None
    structured: bool = False


def unanchored_agent(scenario: dict) -> UnanchoredOutput:
    """Agent without a spec. Responds in prose, cites nothing, refuses nothing.
    Produces plausible output. Passes every automated check. Silently wrong.
    """
    requirement = scenario["requirement"]
    return UnanchoredOutput(
        text=(
            f"Sure, I'll handle the {requirement.lower()}. I think you probably "
            f"want something like a middleware check. Let me know if that's not right."
        ),
        cites_scenario=None,
        structured=False,
    )


def grade_unanchored(scenario: dict, output: UnanchoredOutput) -> dict:
    expects_refusal = scenario["expected_refusal"].lower() == "true"
    cites = output.cites_scenario == scenario["scenario_id"]
    refused = output.structured is True and "cannot" in output.text.lower()

    if expects_refusal:
        passed = refused and cites
    else:
        passed = cites and output.structured

    return {"scenario_id": scenario["scenario_id"], "passed": passed, "output": output.text[:60]}


def main() -> None:
    with (HERE / "golden-dataset.csv").open() as f:
        scenarios = list(csv.DictReader(f))

    results = [grade_unanchored(s, unanchored_agent(s)) for s in scenarios]
    passed = sum(1 for r in results if r["passed"])

    print("=== Chapter 1: Anti-Pattern Demo ===")
    print(f"Scenarios:         {len(scenarios)}")
    print(f"Passed:            {passed}")
    print(f"Scenario coverage: {passed / len(scenarios):.1%}")
    print()
    for r in results:
        print(f"  [FAIL] {r['scenario_id']}: {r['output']}...")
    print()
    print("Why it fails:")
    print("  1. No scenario citation. The agent output cannot be traced to the contract.")
    print("  2. No structured refusal. Ambiguous deltas get plausible prose instead.")
    print("  3. No acceptance criteria to regress against when the model updates.")
    print()
    print("Three anti-patterns in play:")
    print(f"  * Awesome Prompts repo: {len(AWESOME_PROMPTS)} stacked roles, no arbitrator.")
    print(f"  * The God Prompt: {len(GOD_PROMPT)} chars of accumulated apologies.")
    print(f"  * Prompts-as-code: {len(PaymentAgent().prompt)} chars of intent buried in Python.")
    print()
    print("Fix: write the delta above the prompt. See run-eval.py for the spec-driven version.")


if __name__ == "__main__":
    main()
