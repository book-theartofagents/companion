"""
Chapter 6 evaluation: trace-first observability.

Runs offline. No API keys, no network. Demonstrates that operational
questions about an agent system are queries over structured traces, not
grep invocations over text logs.

Usage:
    python run-eval.py

What it does:
    1. Loads a synthesised set of traces from golden-dataset.csv.
    2. Runs the operator queries the book names as the baseline: p95 latency
       by feature, cost by feature, cache hit rate, fallback rate, silent
       wrong answer rate.
    3. Grades the answers against the thresholds in spec.md.

The real pipeline emits Langfuse traces (OTel compatible) and exports them
into Phoenix for evaluation. Both SDKs are stubbed here so the evaluator
stays deterministic and free of network calls. A commented block at the
bottom shows what the live code would look like.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).parent


# -- Stubbed SDKs ----------------------------------------------------------
# The production code uses langfuse.Langfuse and phoenix.evals. Offline we
# record the same shape so the evaluator can run without a backend.
class StubLangfuseClient:
    """Collects spans in memory. Mirrors the Langfuse 4.2 shape."""

    def __init__(self) -> None:
        self.traces: list[dict] = []

    def record_trace(self, trace: dict) -> None:
        self.traces.append(trace)


@dataclass
class Trace:
    trace_id: str
    feature: str
    user_id: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: float
    cache_hit: bool
    fallback_used: str | None
    evaluator_label: str
    evaluator_score: float


def load_traces(path: Path) -> list[Trace]:
    rows: list[Trace] = []
    with path.open() as f:
        for row in csv.DictReader(f):
            rows.append(
                Trace(
                    trace_id=row["trace_id"],
                    feature=row["feature"],
                    user_id=row["user_id"],
                    model=row["model"],
                    prompt_version=row["prompt_version"],
                    input_tokens=int(row["input_tokens"]),
                    output_tokens=int(row["output_tokens"]),
                    latency_ms=int(row["latency_ms"]),
                    cost_usd=float(row["cost_usd"]),
                    cache_hit=row["cache_hit"].lower() == "true",
                    fallback_used=row["fallback_used"] or None,
                    evaluator_label=row["evaluator_label"],
                    evaluator_score=float(row["evaluator_score"]),
                )
            )
    return rows


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    values = sorted(values)
    rank = 0.95 * (len(values) - 1)
    lo, hi = math.floor(rank), math.ceil(rank)
    return values[lo] + (values[hi] - values[lo]) * (rank - lo)


# -- Queries the book names as the baseline -------------------------------
@dataclass
class Report:
    traces: int
    p95_by_feature: dict[str, float]
    cost_by_feature: dict[str, float]
    cost_by_user: dict[str, float]
    cache_hit_rate: float
    fallback_rate: float
    silent_wrong_rate: float
    prompt_versions_seen: dict[str, set[str]] = field(default_factory=dict)


def operator_report(traces: list[Trace]) -> Report:
    by_feature: dict[str, list[int]] = {}
    cost_by_feature: dict[str, float] = {}
    cost_by_user: dict[str, float] = {}
    cache_hits = 0
    fallbacks = 0
    silent_wrong = 0
    prompts_by_feature: dict[str, set[str]] = {}

    for t in traces:
        by_feature.setdefault(t.feature, []).append(t.latency_ms)
        cost_by_feature[t.feature] = cost_by_feature.get(t.feature, 0.0) + t.cost_usd
        cost_by_user[t.user_id] = cost_by_user.get(t.user_id, 0.0) + t.cost_usd
        if t.cache_hit:
            cache_hits += 1
        if t.fallback_used:
            fallbacks += 1
        # Silent wrong answer: grader says incorrect, but no hard failure
        # surfaced. Latency and tokens looked fine.
        if t.evaluator_label == "incorrect":
            silent_wrong += 1
        if t.prompt_version:
            prompts_by_feature.setdefault(t.feature, set()).add(t.prompt_version)

    return Report(
        traces=len(traces),
        p95_by_feature={f: p95(v) for f, v in by_feature.items()},
        cost_by_feature={f: round(c, 4) for f, c in cost_by_feature.items()},
        cost_by_user={u: round(c, 4) for u, c in cost_by_user.items()},
        cache_hit_rate=round(cache_hits / len(traces), 4),
        fallback_rate=round(fallbacks / len(traces), 4),
        silent_wrong_rate=round(silent_wrong / len(traces), 4),
        prompt_versions_seen=prompts_by_feature,
    )


def grade(report: Report) -> list[dict]:
    """Grade the report against the invariants in spec.md."""
    checks: list[dict] = []

    checks.append(
        {
            "name": "p95-support-answer",
            "passed": report.p95_by_feature.get("support.answer", 1e9) <= 2500,
            "detail": f"p95={report.p95_by_feature.get('support.answer', 0):.0f}ms target<=2500ms",
        }
    )
    checks.append(
        {
            "name": "p95-research-wiki",
            "passed": report.p95_by_feature.get("research.wiki", 1e9) <= 2500,
            "detail": f"p95={report.p95_by_feature.get('research.wiki', 0):.0f}ms target<=2500ms",
        }
    )
    checks.append(
        {
            "name": "cache-hit-rate",
            "passed": report.cache_hit_rate >= 0.5,
            "detail": f"hit_rate={report.cache_hit_rate:.1%} target>=50%",
        }
    )
    checks.append(
        {
            "name": "fallback-rate-visible",
            "passed": 0 <= report.fallback_rate < 0.5,
            "detail": f"fallback_rate={report.fallback_rate:.1%} target<50%",
        }
    )
    checks.append(
        {
            "name": "silent-wrong-detected",
            "passed": report.silent_wrong_rate > 0,
            "detail": (
                f"silent_wrong_rate={report.silent_wrong_rate:.1%}. "
                f"Evaluator caught the silent wrong answer that classical monitoring missed."
            ),
        }
    )
    checks.append(
        {
            "name": "cost-attribution-works",
            "passed": len(report.cost_by_user) > 1 and len(report.cost_by_feature) > 1,
            "detail": (
                f"cost_by_user keys={len(report.cost_by_user)}, "
                f"cost_by_feature keys={len(report.cost_by_feature)}"
            ),
        }
    )
    checks.append(
        {
            "name": "prompt-version-tracked",
            "passed": all(len(v) >= 1 for v in report.prompt_versions_seen.values()),
            "detail": (
                "prompt versions seen per feature: "
                + ", ".join(f"{k}={sorted(v)}" for k, v in report.prompt_versions_seen.items())
            ),
        }
    )
    return checks


def main() -> int:
    traces = load_traces(HERE / "golden-dataset.csv")
    lf = StubLangfuseClient()
    for t in traces:
        lf.record_trace({"trace_id": t.trace_id, "feature": t.feature, "cost_usd": t.cost_usd})

    report = operator_report(traces)
    checks = grade(report)

    print("=== Chapter 6: Trace-First Observability ===")
    print(f"Traces loaded:        {report.traces}")
    print(f"Features:             {sorted(report.p95_by_feature)}")
    print(f"Cache hit rate:       {report.cache_hit_rate:.1%}")
    print(f"Fallback rate:        {report.fallback_rate:.1%}")
    print(f"Silent wrong rate:    {report.silent_wrong_rate:.1%}")
    print()
    print("p95 latency by feature:")
    for feature, ms in sorted(report.p95_by_feature.items()):
        print(f"  {feature:<20s} {ms:>6.0f} ms")
    print()
    print("Cost by feature (USD):")
    for feature, c in sorted(report.cost_by_feature.items()):
        print(f"  {feature:<20s} {c:>6.3f}")
    print()
    print("Cost by user (USD):")
    for user, c in sorted(report.cost_by_user.items()):
        print(f"  {user:<20s} {c:>6.3f}")
    print()

    for c in checks:
        status = "PASS" if c["passed"] else "FAIL"
        print(f"  [{status}] {c['name']}: {c['detail']}")

    ok = all(c["passed"] for c in checks)
    print()
    if ok:
        print("PASS: the trace store answers operational questions by query.")
        print("      Langfuse for what ran. Phoenix for whether it was right.")
    else:
        print("FAIL: at least one query had to fall back to archaeology. See Ch. 6.")

    # Sanity: the exported trace tree exists and parses.
    trace_tree = json.loads((HERE / "trace-example.json").read_text())
    assert trace_tree["trace_id"].startswith("trace_")
    assert trace_tree["spans"], "trace has no spans"

    summary = {
        "traces": report.traces,
        "p95_support_answer_ms": report.p95_by_feature.get("support.answer", 0),
        "cache_hit_rate": report.cache_hit_rate,
        "fallback_rate": report.fallback_rate,
        "silent_wrong_rate": report.silent_wrong_rate,
        "cost_by_feature_usd": report.cost_by_feature,
    }
    print("\nSummary:", json.dumps(summary, sort_keys=True))
    return 0 if ok else 1


# -- Live integration (commented) ------------------------------------------
# from langfuse import Langfuse
# from langfuse.decorators import observe
#
# langfuse = Langfuse()
#
# @observe()
# def support_answer(question: str, user_id: str) -> str:
#     docs = retrieve(question)
#     return synthesise(question, docs, user_id=user_id)
#
# @observe(as_type="generation")
# def synthesise(question: str, docs: list[str], user_id: str) -> str:
#     prompt = langfuse.get_prompt("support.answer", version=12)
#     langfuse.update_current_observation(
#         model="claude-opus-4-7",
#         metadata={"prompt_version": 12, "feature": "support.answer", "user_id": user_id},
#     )
#     # ... model call here ...


if __name__ == "__main__":
    sys.exit(main())
