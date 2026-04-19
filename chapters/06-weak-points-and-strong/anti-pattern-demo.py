"""
Chapter 6 anti-pattern: the black-box agent.

Three failure shapes from the book:
    1. The print-statement tracer: prose logs, no hierarchy, no attribution.
    2. The dashboard that shows volume: aggregates, no per-step drill-down.
    3. The silent wrong answer: 200 OK, grammatical, wrong, unaudited.

Runs offline. Produces the same operational questions the run-eval answers
in seconds, and shows how long they take when the only artefact is a log
file.

Usage:
    python anti-pattern-demo.py
"""

from __future__ import annotations

import csv
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent
random.seed(42)


# -- Anti-pattern #1: the print-statement tracer --------------------------
# Flat text. No trace_id. No feature. No cost. No hierarchy.
# The grep queries below are real. They do not work well.
LOG_LINES = [
    "INFO starting request",
    "INFO retrieving docs",
    "INFO got 5 docs",
    "INFO calling model",
    "INFO model returned 180 tokens",
    "INFO done",
    "WARN rate limit close",
    "INFO starting request",
    "INFO retrieving docs",
    "INFO got 5 docs",
    "INFO calling model",
    "ERROR model timed out after 30s",
    "INFO retrying",
    "INFO model returned 210 tokens",
    "INFO done",
    "INFO starting request",
    "INFO calling model",
    "INFO model returned 200 tokens",
    "INFO done",
] * 20


def grep(pattern: str, lines: list[str]) -> list[str]:
    r = re.compile(pattern)
    return [line for line in lines if r.search(line)]


# -- Anti-pattern #2: the dashboard that shows volume ---------------------
# Four metrics. All green. Answers nothing.
@dataclass
class VolumeDashboard:
    requests_per_minute: int
    error_rate_pct: float
    p95_latency_ms: int
    monthly_token_spend_usd: float

    def render(self) -> str:
        return (
            f"REQ/min: {self.requests_per_minute}  "
            f"ERR: {self.error_rate_pct:.2f}%  "
            f"p95: {self.p95_latency_ms}ms  "
            f"SPEND: ${self.monthly_token_spend_usd:,.0f}/mo"
        )


# -- Anti-pattern #3: the silent wrong answer -----------------------------
@dataclass
class SilentCall:
    question: str
    response: str
    http_status: int
    latency_ms: int
    token_count: int
    # No evaluator. No reviewer sample. Grammatical, plausible, wrong.


def silent_agent(question: str) -> SilentCall:
    """Produces a grammatically correct answer. Content not verified."""
    return SilentCall(
        question=question,
        response=(
            "Yes. Our policy explicitly covers that case. Please see section 4.2 "
            "of the employee handbook, paragraph 3, which was added last quarter."
        ),
        http_status=200,
        latency_ms=820,
        token_count=180,
    )


def main() -> None:
    print("=== Chapter 6: Anti-Pattern Demo ===")
    print()

    # 1. Print-statement tracer. Operator questions become grep queries.
    print("-- 1. The print-statement tracer --")
    print(f"Log lines in buffer: {len(LOG_LINES)}")
    errors = grep("ERROR", LOG_LINES)
    timeouts = grep("timed out", LOG_LINES)
    print(f"grep ERROR:     {len(errors)} lines (no trace_id, no user, no feature)")
    print(f"grep 'timed out': {len(timeouts)} lines")
    print("Question the operator asks: which feature does the timeout belong to?")
    print("Answer the logs give: unknown. No feature, no user, no cost, no parent span.")
    print()

    # 2. Volume dashboard. Everything is green. Nothing is answered.
    print("-- 2. The dashboard that shows volume --")
    dash = VolumeDashboard(
        requests_per_minute=312,
        error_rate_pct=0.41,
        p95_latency_ms=1240,
        monthly_token_spend_usd=11_000,
    )
    print(f"Dashboard: {dash.render()}")
    print("CFO asks: which feature grew the bill from $1k to $11k?")
    print("Dashboard answers: single number. No per-feature split, no drill-down.")
    print("Team writes ad hoc SQL for weeks. Finance asks again next month.")
    print()

    # 3. Silent wrong answer. 200 OK. Grammatical. Incorrect.
    print("-- 3. The silent wrong answer --")
    calls = [silent_agent(f"q{i}") for i in range(40)]
    grammatically_correct = sum(1 for c in calls if c.response.endswith("."))
    reviewed = 0  # nobody sampled the production output
    print(f"Calls handled:           {len(calls)}")
    print(f"HTTP 200:                {sum(1 for c in calls if c.http_status == 200)}")
    print(f"Grammatically correct:   {grammatically_correct}")
    print(f"Reviewed against domain: {reviewed}")
    print()
    print("What classical monitoring sees: every call green.")
    print("What the audit finds (three months later): forty hallucinated policies.")
    print("The customer found the bug before the team did.")
    print()

    # Compare the two worlds. The book's argument in numbers.
    print("-- Compare --")
    with (HERE / "golden-dataset.csv").open() as f:
        rows = list(csv.DictReader(f))
    traces = len(rows)
    features = {r["feature"] for r in rows}
    wrong = sum(1 for r in rows if r["evaluator_label"] == "incorrect")
    print(f"Trace-first (run-eval.py):")
    print(f"  {traces} traces, {len(features)} features, {wrong} silent-wrong caught by evaluator.")
    print("  p95/cost/cache/fallback answered in one query.")
    print()
    print("Log-first (this demo):")
    print(f"  {len(LOG_LINES)} log lines, 0 features attributed, 0 silent-wrong caught.")
    print("  Each question is an afternoon of grep archaeology.")
    print()
    print("Fix: trace every span. Attach feature, user, model, prompt version, cost.")
    print("     Langfuse for what ran. Phoenix for whether it was right.")

    return None


if __name__ == "__main__":
    main()
    sys.exit(0)
