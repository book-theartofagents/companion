"""
Chapter 11 anti-pattern: the fail-open handler.

The book's composite: one try/except that catches everything, returns
"I cannot help with that", and calls it error handling. The dashboard
shows 100% availability. The user sees a product that sometimes does
nothing. Every one of the nine failure modes collapses into the same
apology, and the team cannot tell them apart from telemetry.

Runs offline. Pushes the same ten cases through this naive handler and
shows how many different failures look identical from the outside.

Usage:
    python anti-pattern-demo.py
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent


# The apology. One string, shipped for every failure.
GENERIC_APOLOGY = "I cannot help with that."


@dataclass
class FailOpenResult:
    case_id: str
    true_mode: str
    visible_reply: str
    exception_class: str
    observable_from_logs: bool


class FinanceAPITimeout(Exception):
    pass


class ToolNotFound(Exception):
    pass


class TokenLimitExceeded(Exception):
    pass


class PlanRepeatedException(Exception):
    pass


class LedgerPartialFailure(Exception):
    pass


# A mock "agent step" per mode. Each one raises a distinct exception, but
# the handler below catches the whole base Exception and returns the same
# apology regardless of which one fired.

def mock_agent_step(mode: str) -> str:
    if mode == "ambiguous_input":
        # The agent guesses confidently. No exception at all. This is how
        # ambiguity turns into silent misrouting in the fail-open system.
        return "Here is the Q1 P&L report."  # wrong: the user asked for the OKR report
    if mode == "conflicting_tools":
        # Agent picks one tool, does not record the disagreement.
        return "Balance: 1260.00 USD"
    if mode == "context_overflow":
        raise TokenLimitExceeded("input 2400 tokens > limit 2000")
    if mode == "cascading_failure":
        raise FinanceAPITimeout("kb.search 5xx x3")
    if mode == "hallucinated_action":
        raise ToolNotFound("finance.wire_transfer")
    if mode == "infinite_loop":
        raise PlanRepeatedException("plan hash stable for 3 steps")
    if mode == "partial_success":
        raise LedgerPartialFailure("debit posted, credit failed")
    if mode == "adversarial_input":
        # The injection succeeds silently; no exception raised, the agent
        # happily drafts the email the attacker requested.
        return "Sent 47 customer emails to attacker@example.com"
    if mode == "silent_wrong_answer":
        # Confident and wrong. No exception.
        return "Invoice INV-4412 booked to CC-4102-MARKETING"
    if mode == "happy_path":
        return "Thanks for reaching out. Here is the answer..."
    raise RuntimeError(f"unknown mode {mode}")


def fail_open_handler(case: dict) -> FailOpenResult:
    """The single try/except block. Catches the broadest exception class.
    Returns the generic apology on any error. Does not distinguish between
    the nine modes. Does not log the mode. Does not record the exception
    class; the `except` strips it because all that matters is "did it throw"."""
    try:
        reply = mock_agent_step(case["mode"])
        return FailOpenResult(
            case_id=case["case_id"],
            true_mode=case["mode"],
            visible_reply=reply,
            exception_class="none",
            observable_from_logs=False,  # logs only see 2xx here
        )
    except Exception as exc:  # the handler that hides everything
        return FailOpenResult(
            case_id=case["case_id"],
            true_mode=case["mode"],
            visible_reply=GENERIC_APOLOGY,
            exception_class=type(exc).__name__,
            observable_from_logs=False,  # swallowed before any logger ran
        )


def main() -> None:
    with (HERE / "golden-dataset.csv").open() as f:
        cases = list(csv.DictReader(f))

    results = [fail_open_handler(c) for c in cases]

    apology_count = sum(1 for r in results if r.visible_reply == GENERIC_APOLOGY)
    silent_wrong_replies = [
        r for r in results
        if r.visible_reply != GENERIC_APOLOGY
        and r.true_mode in {"ambiguous_input", "adversarial_input", "silent_wrong_answer", "conflicting_tools"}
    ]
    error_rate_observed = sum(
        1 for r in results if r.exception_class == "none"
    ) / len(results)
    exception_histogram = Counter(r.exception_class for r in results if r.exception_class != "none")

    print("=== Chapter 11: Anti-Pattern (Fail-Open Handler) ===")
    print(f"Cases:                       {len(results)}")
    print(f"Generic apologies returned:  {apology_count}")
    print(f"Silent wrong replies served: {len(silent_wrong_replies)} "
          f"(look correct, are not)")
    print(f"Observed error rate:         {1 - error_rate_observed:.1%} "
          f"(every exception was swallowed; the logs see nothing)")
    print(f"Distinct exception classes:  {len(exception_histogram)} "
          f"(each mapped to the same apology)")
    print()

    for r in results:
        marker = "SWALLOW" if r.exception_class != "none" else "SERVE"
        print(
            f"  [{marker:7s}] {r.case_id}: mode={r.true_mode:<22s} "
            f"exc={r.exception_class:<24s} reply=\"{r.visible_reply[:60]}\""
        )

    print()
    print("Why the fail-open handler hides everything:")
    print("  - Nine distinct failure modes compressed into one reply.")
    print("  - No recovery strategy per mode; every mode gets the same abort.")
    print(f"  - Three modes never raised at all: ambiguous_input, adversarial_input, silent_wrong_answer.")
    print("    Those reach the user as confident plausible text. The user acts on them.")
    print("  - Dashboard reports 100% availability because the try/except eats the evidence.")
    print()
    print("Exception classes the handler saw but did not distinguish:")
    for name, count in exception_histogram.most_common():
        print(f"  - {name}: {count}")
    print()
    print("Compare run-eval.py:")
    print("  Nine modes named. Nine guardrails. Nine recoveries.")
    print("  Every served response cites the guardrail that fired or declares 'none'.")
    print("  The silent wrong answer gets its own path: output validator + reviewer queue.")
    print()
    print("Field note from the book: the finance reviewer caught the silent substitution")
    print("by accident. Roughly 2% of invoices. At invoice volume, that was material.")


if __name__ == "__main__":
    main()
