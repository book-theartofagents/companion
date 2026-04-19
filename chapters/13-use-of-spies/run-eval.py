"""
Chapter 13 evaluation: the Spec Loop in miniature.

Runs offline. No API keys, no network. Demonstrates the feedback loop that
closes the book: run, measure, fail, delta, re-run, improve.

Usage:
    python run-eval.py

What it does:
    1. Loads a 10-item golden dataset (Proefballon support Q&A).
    2. Runs a baseline agent against it (deterministic stub).
    3. Computes faithfulness and answer-correctness with a small heuristic
       that mimics Ragas' role. No LLM call.
    4. Detects failures, produces a structured delta per failure, applies
       the delta as a "post-optimisation" version of the agent.
    5. Re-runs and reports the before-and-after score.

The notebook shows the real version. It wires DSPy signatures and an
optimiser, calls Ragas metrics on a dataframe, and closes the loop with a
live judge. The shape of the loop is the same. The pieces are swapped.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent

# Thresholds from spec.md and guardrail-config.yaml.
FAITHFULNESS_MIN = 0.80
CORRECTNESS_MIN = 0.70


# --- DSPy / Ragas stubs ---------------------------------------------------
# The real code imports dspy and ragas. Neither is required here because the
# test path is deterministic. Names match the libraries so the notebook
# migration is mechanical.

def stub_dspy_available() -> bool:
    try:
        import importlib
        importlib.import_module("dspy")
        return True
    except ModuleNotFoundError:
        return False


def stub_ragas_available() -> bool:
    try:
        import importlib
        importlib.import_module("ragas")
        return True
    except ModuleNotFoundError:
        return False


# --- The agent under test -------------------------------------------------

@dataclass
class AgentOutput:
    answer: str
    used_context: bool
    scenario_id: str


def baseline_agent(row: dict) -> AgentOutput:
    """Minimal stand-in for a RAG agent. Copies the context when it is short,
    paraphrases poorly when it is not. On purpose: the baseline should have
    real, repeatable failures so the loop has something to fix.
    """
    q = row["question"].lower()
    ctx = row["retrieved_context"]

    # Baseline quirk 1: on "can I ..." questions, the baseline forgets to
    # cite the guardrail. This shows up as a correctness miss.
    if q.startswith("can i "):
        return AgentOutput(
            answer=f"Yes, you can {q.split('can i ', 1)[1].rstrip('?')}.",
            used_context=False,
            scenario_id=row["scenario_id"],
        )

    # Baseline quirk 2: on "what is" questions about jargon, the baseline
    # emits a one-word answer instead of the expected grounded phrasing.
    if q.startswith("what is "):
        token = q.split("what is ", 1)[1].split(" ", 1)[0].rstrip("?")
        return AgentOutput(
            answer=token,
            used_context=False,
            scenario_id=row["scenario_id"],
        )

    # Default: echo the context. Works for the recall-shaped questions.
    return AgentOutput(answer=ctx, used_context=True, scenario_id=row["scenario_id"])


def optimised_agent(row: dict) -> AgentOutput:
    """The agent after the deltas are applied.

    The deltas from this loop: always ground answers in the context, return
    a refusal with reason when the question asks about a constraint that
    the context states as prohibited.
    """
    ctx = row["retrieved_context"]
    q = row["question"].lower()

    # Delta SCN-105 / SCN-110: refusal with context citation.
    if ("can " in q or "is there " in q) and ctx.startswith("no "):
        return AgentOutput(answer=ctx, used_context=True, scenario_id=row["scenario_id"])

    # Delta on "what is X": paraphrase the context, do not collapse to a token.
    return AgentOutput(answer=ctx, used_context=True, scenario_id=row["scenario_id"])


# --- Metrics --------------------------------------------------------------
# Deterministic heuristics that mimic the shape of Ragas metrics. The real
# call signs show up in the notebook:
#   from ragas import evaluate
#   from ragas.metrics import faithfulness, answer_correctness
#   scores = evaluate(dataset, metrics=[faithfulness, answer_correctness])

WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(WORD_RE.findall(text.lower()))


def faithfulness(answer: str, context: str) -> float:
    """Fraction of answer tokens that appear in the context. A crude proxy
    for Ragas' faithfulness metric. Good enough for a deterministic test.
    """
    a, c = _tokens(answer), _tokens(context)
    if not a:
        return 0.0
    return len(a & c) / len(a)


def answer_correctness(answer: str, reference: str, notes: str) -> float:
    """Token overlap with the reference, boosted when acceptance notes match.
    Real Ragas does a weighted blend with an LLM judge. This is the cheap
    stand-in: deterministic, reproducible, calibrated by the dataset author.
    """
    a, r = _tokens(answer), _tokens(reference)
    if not r:
        return 0.0
    base = len(a & r) / len(r)

    # Bump for acceptance-note matches. The note is the human's extra signal.
    for keyword in WORD_RE.findall(notes.lower()):
        if keyword in a and keyword not in r:
            base += 0.05

    return min(base, 1.0)


# --- The loop -------------------------------------------------------------

@dataclass
class Result:
    scenario_id: str
    faithfulness: float
    correctness: float
    passed: bool
    answer: str


@dataclass
class DeltaProposal:
    scenario_id: str
    failure_reason: str
    proposed_delta: str


def run_against_dataset(
    agent: Callable[[dict], AgentOutput],
    rows: list[dict],
) -> list[Result]:
    results: list[Result] = []
    for row in rows:
        out = agent(row)
        fa = faithfulness(out.answer, row["retrieved_context"])
        co = answer_correctness(out.answer, row["reference_answer"], row["acceptance_notes"])
        passed = fa >= FAITHFULNESS_MIN and co >= CORRECTNESS_MIN
        results.append(
            Result(
                scenario_id=row["scenario_id"],
                faithfulness=fa,
                correctness=co,
                passed=passed,
                answer=out.answer,
            )
        )
    return results


def propose_deltas(results: list[Result], rows: list[dict]) -> list[DeltaProposal]:
    """For every failure, emit a structured delta. Shape matches the schema
    in guardrail-config.yaml. In production the optimiser would write these
    to the spec repository.
    """
    proposals: list[DeltaProposal] = []
    for r, row in zip(results, rows, strict=False):
        if r.passed:
            continue
        question_hint = row.get("question", "")[:60]
        if r.faithfulness < FAITHFULNESS_MIN:
            reason = f"faithfulness {r.faithfulness:.2f} below {FAITHFULNESS_MIN}"
            delta = (
                f"agent must ground answer for {r.scenario_id} ({question_hint!r}) "
                f"in retrieved context; collapse to context phrasing when question "
                f"starts with `what is`"
            )
        else:
            reason = f"correctness {r.correctness:.2f} below {CORRECTNESS_MIN}"
            delta = (
                f"agent must refuse with context citation for {r.scenario_id} "
                f"({question_hint!r}); add scenario notes about `can ...` refusals "
                f"grounded in policy"
            )
        proposals.append(
            DeltaProposal(
                scenario_id=r.scenario_id,
                failure_reason=reason,
                proposed_delta=delta,
            )
        )
    return proposals


def score(results: list[Result]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    avg_fa = sum(r.faithfulness for r in results) / total if total else 0.0
    avg_co = sum(r.correctness for r in results) / total if total else 0.0
    return {
        "total": total,
        "passed": passed,
        "avg_faithfulness": round(avg_fa, 3),
        "avg_correctness": round(avg_co, 3),
    }


def main() -> int:
    with (HERE / "golden-dataset.csv").open() as f:
        rows = list(csv.DictReader(f))

    print("=== Chapter 13: Spec Loop Evaluation ===")
    print(f"Dataset items:      {len(rows)}")
    print(f"dspy available:     {stub_dspy_available()}  (real optimiser in notebook)")
    print(f"ragas available:    {stub_ragas_available()}  (real metrics in notebook)")
    print()

    baseline = run_against_dataset(baseline_agent, rows)
    base_score = score(baseline)
    print("-- Baseline --")
    for r in baseline:
        tag = "PASS" if r.passed else "FAIL"
        print(
            f"  [{tag}] {r.scenario_id}  "
            f"fa={r.faithfulness:.2f} co={r.correctness:.2f}  "
            f"answer={r.answer[:48]!r}"
        )
    print(
        f"  Baseline: {base_score['passed']}/{base_score['total']} passed, "
        f"fa={base_score['avg_faithfulness']}, co={base_score['avg_correctness']}"
    )
    print()

    deltas = propose_deltas(baseline, rows)
    print(f"-- Deltas proposed: {len(deltas)} --")
    for d in deltas:
        print(f"  {d.scenario_id}: {d.failure_reason}")
        print(f"    -> {d.proposed_delta}")
    print()

    optimised = run_against_dataset(optimised_agent, rows)
    opt_score = score(optimised)
    print("-- After optimisation --")
    for b, o in zip(baseline, optimised, strict=False):
        arrow = "->" if not b.passed and o.passed else "  "
        tag = "PASS" if o.passed else "FAIL"
        print(
            f"  [{tag}] {o.scenario_id}  fa={o.faithfulness:.2f} co={o.correctness:.2f}  {arrow}"
        )
    print(
        f"  Optimised: {opt_score['passed']}/{opt_score['total']} passed, "
        f"fa={opt_score['avg_faithfulness']}, co={opt_score['avg_correctness']}"
    )
    print()

    improvement = opt_score["avg_correctness"] - base_score["avg_correctness"]
    print(f"Improvement in correctness: {improvement:+.3f}")
    print(f"Deltas produced:            {len(deltas)}")

    ok = (
        base_score["passed"] < base_score["total"]  # baseline must have real failures
        and len(deltas) >= 2                        # loop must surface them
        and opt_score["passed"] > base_score["passed"]  # deltas must help
        and opt_score["avg_correctness"] >= CORRECTNESS_MIN
        and opt_score["avg_faithfulness"] >= FAITHFULNESS_MIN
    )

    print()
    if ok:
        print("PASS: the loop closed. Failures surfaced, deltas proposed, score went up.")
    else:
        print("FAIL: the loop did not close. See Ch. 13 vibes-driven release.")

    summary = {
        "baseline": base_score,
        "optimised": opt_score,
        "deltas_produced": len(deltas),
        "improvement": round(improvement, 3),
    }
    print("\nSummary:", json.dumps(summary))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
