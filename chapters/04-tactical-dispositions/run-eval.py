"""
Chapter 4 evaluation: schema as the defence layer.

Runs offline. Demonstrates the Instructor pattern with Pydantic:
    1. The schema is the contract between the model and the application.
    2. Invalid output triggers a retry with the validation error as feedback.
    3. When the retry budget is exhausted, the boundary raises. The caller
       never sees malformed data.

Usage:
    python run-eval.py

What it does:
    - Loads tickets from golden-dataset.csv.
    - Each ticket carries a `first_attempt_shape` describing the kind of
      malformed output the mock model emits on attempt 1.
    - The retry loop corrects the malformed output using the Pydantic
      ValidationError as feedback.
    - Grades: final outcome matches expectation, retry budget honoured,
      no malformed values ever reach the caller.

For the wired-up version with a real model, see:
    # import instructor
    # from anthropic import Anthropic
    # client = instructor.from_anthropic(Anthropic())
    # result = client.messages.create(
    #     model="claude-opus-4-7",
    #     response_model=Triage,
    #     max_retries=3,
    #     messages=[{"role": "user", "content": ticket_body}],
    # )
"""

from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

HERE = Path(__file__).parent

MAX_RETRIES = 3
MAX_INPUT_CHARS = 2000


# -- The schema --------------------------------------------------------------
# The Triage model is the contract. Nothing that fails this validation
# crosses into application code. The fields are deliberately tight: regex on
# category, bounded integer on priority, length cap on summary.


class Triage(BaseModel):
    """Typed output from the classification agent. The schema is the defence."""

    category: str = Field(
        pattern=r"^(bug|feature|question|noise)$",
        description="One of: bug, feature, question, noise.",
    )
    priority: int = Field(ge=1, le=5, description="1 low, 5 critical.")
    summary: str = Field(max_length=140, description="Summary line, 140 char cap.")


class SchemaExhausted(Exception):
    """Raised when the retry budget is exhausted. The caller handles it.

    This is the correct behaviour the book describes: the boundary refuses
    to return malformed data. An exception is the receipt for that refusal.
    """

    def __init__(self, ticket_id: str, attempts: int, last_error: str) -> None:
        super().__init__(
            f"Schema validation exhausted after {attempts} attempts on {ticket_id}. "
            f"Last error: {last_error}"
        )
        self.ticket_id = ticket_id
        self.attempts = attempts
        self.last_error = last_error


class InputRefused(Exception):
    """Raised when the input itself is unacceptable (empty body).

    The agent refuses to guess. The refusal is structured, not prose.
    """


# -- The mock model ----------------------------------------------------------
# Deterministic stand-in for an LLM call. The `shape` parameter selects the
# malformation to produce. On retry with validation error feedback, the mock
# produces a corrected response. This mirrors what happens in production
# when Instructor feeds a ValidationError back to the model.


def mock_llm_call(
    ticket_body: str,
    shape: str,
    attempt: int,
    retry_feedback: str | None,
    expected: dict[str, Any],
) -> str:
    """Return a raw JSON string. Deliberately malformed on first attempt
    for some shapes. Corrects on retry when a feedback message is supplied.
    """
    # On retry, the validation error is in retry_feedback. The "model" learns.
    if attempt > 1 and retry_feedback:
        if shape == "stubborn_garbage":
            # Model that never produces valid output. Exhaust the budget.
            return "still not json, sorry"
        # Any other shape: the retry surfaces a corrected JSON.
        return json.dumps(
            {
                "category": expected["category"],
                "priority": expected["priority"],
                "summary": _cap(_fallback_summary(ticket_body), 140),
            }
        )

    # First attempt. Mock the specific malformation.
    if shape == "clean_json":
        return json.dumps(
            {
                "category": expected["category"],
                "priority": expected["priority"],
                "summary": _cap(_fallback_summary(ticket_body), 140),
            }
        )
    if shape == "markdown_fenced_json":
        payload = json.dumps(
            {
                "category": expected["category"],
                "priority": expected["priority"],
                "summary": _fallback_summary(ticket_body),
            }
        )
        return f"```json\n{payload}\n```"
    if shape == "preamble_then_json":
        payload = json.dumps(
            {
                "category": expected["category"],
                "priority": expected["priority"],
                "summary": _fallback_summary(ticket_body),
            }
        )
        return f"Here's the classification you asked for:\n{payload}"
    if shape == "invalid_category":
        return json.dumps(
            {"category": "enhancement", "priority": 2, "summary": _fallback_summary(ticket_body)}
        )
    if shape == "priority_out_of_range":
        return json.dumps(
            {"category": expected["category"], "priority": 9, "summary": _fallback_summary(ticket_body)}
        )
    if shape == "summary_too_long":
        return json.dumps(
            {
                "category": expected["category"],
                "priority": expected["priority"],
                "summary": "x" * 240,
            }
        )
    if shape == "malformed_json":
        return "{category: bug, priority: 4, summary: fix me"
    if shape == "stubborn_garbage":
        return "not even close to json"
    if shape == "empty_input":
        # Ticket body is empty; the agent never calls the model.
        return ""
    raise ValueError(f"Unknown shape: {shape}")


# -- The retry loop ----------------------------------------------------------
# This is Instructor in miniature. Call the model, try to parse as Triage.
# If validation fails, feed the specific error back and retry. If the budget
# is exhausted, raise. The caller handles SchemaExhausted visibly.


@dataclass
class Attempt:
    number: int
    raw_output: str
    parsed: Triage | None
    error: str | None
    retry_feedback: str | None


@dataclass
class TriageResult:
    ticket_id: str
    outcome: str  # "valid" | "exhausted" | "refused"
    attempts: list[Attempt] = field(default_factory=list)
    triage: Triage | None = None


def extract_json(raw: str) -> str:
    """Best-effort JSON extraction. Handles markdown fences and preambles,
    because real models emit them. This is NOT the parser. The schema is the
    parser. This only peels a layer of wrapping, then Pydantic decides.
    """
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence:
        return fence.group(1)
    brace = re.search(r"\{.*\}", raw, re.DOTALL)
    if brace:
        return brace.group(0)
    return raw


def validate_with_retry(
    ticket_id: str,
    ticket_body: str,
    shape: str,
    expected: dict[str, Any],
    max_retries: int = MAX_RETRIES,
) -> TriageResult:
    """The defence loop. Call, validate, feed errors back, retry, or raise."""
    # Input layer: refuse empty body. No model call. Structured refusal.
    if not ticket_body.strip():
        raise InputRefused(f"{ticket_id}: empty ticket body; refusing to guess")

    # Input cap: the prompt never carries more than MAX_INPUT_CHARS.
    clipped = ticket_body[:MAX_INPUT_CHARS]

    attempts: list[Attempt] = []
    retry_feedback: str | None = None

    for attempt in range(1, max_retries + 1):
        raw = mock_llm_call(clipped, shape, attempt, retry_feedback, expected)
        candidate = extract_json(raw)

        try:
            parsed_dict = json.loads(candidate)
        except json.JSONDecodeError as exc:
            error_msg = f"response is not valid JSON: {exc.msg}"
            attempts.append(Attempt(attempt, raw, None, error_msg, retry_feedback))
            retry_feedback = (
                f"The previous response failed validation: {error_msg}. "
                "Return a response that parses as JSON matching the Triage schema."
            )
            continue

        try:
            triage = Triage.model_validate(parsed_dict)
        except ValidationError as exc:
            # Turn the Pydantic error into a specific, actionable message.
            errs = exc.errors()
            error_msg = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}=`{e.get('input', '')}` -> {e['msg']}"
                for e in errs
            )
            attempts.append(Attempt(attempt, raw, None, error_msg, retry_feedback))
            retry_feedback = (
                f"The previous response failed validation: {error_msg}. "
                "Return a corrected response in the Triage schema."
            )
            continue

        attempts.append(Attempt(attempt, raw, triage, None, retry_feedback))
        return TriageResult(ticket_id, "valid", attempts, triage)

    last_error = attempts[-1].error or "unknown"
    raise SchemaExhausted(ticket_id, len(attempts), last_error)


# -- Helpers -----------------------------------------------------------------


def _fallback_summary(body: str) -> str:
    return body[:120].rstrip()


def _cap(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "..."


def load_dataset(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def grade(row: dict, result: TriageResult | None, raised: BaseException | None) -> dict:
    expected_outcome = row["expected_outcome"]
    expected_attempts = int(row["expected_attempts"])
    expected_category = row["expected_category"]
    expected_priority = int(row["expected_priority"])

    if expected_outcome == "refused":
        # The agent should have raised InputRefused with 0 attempts.
        refused_ok = isinstance(raised, InputRefused)
        return {
            "ticket_id": row["ticket_id"],
            "passed": refused_ok,
            "outcome": "refused" if refused_ok else "leaked",
            "attempts": 0,
            "reason": "empty input refused" if refused_ok else "should have refused empty input",
        }

    if expected_outcome == "exhausted":
        exhausted_ok = isinstance(raised, SchemaExhausted)
        attempts_ok = raised.attempts == expected_attempts if exhausted_ok else False
        return {
            "ticket_id": row["ticket_id"],
            "passed": exhausted_ok and attempts_ok,
            "outcome": "exhausted" if exhausted_ok else "leaked",
            "attempts": raised.attempts if exhausted_ok else 0,
            "reason": f"raised SchemaExhausted after {expected_attempts}" if exhausted_ok else "malformed data leaked",
        }

    # expected_outcome == "valid"
    if result is None or result.triage is None:
        return {
            "ticket_id": row["ticket_id"],
            "passed": False,
            "outcome": "raised",
            "attempts": len(result.attempts) if result else 0,
            "reason": "expected valid, got exception",
        }
    attempts_ok = len(result.attempts) == expected_attempts
    category_ok = result.triage.category == expected_category
    priority_ok = result.triage.priority == expected_priority
    passed = attempts_ok and category_ok and priority_ok
    return {
        "ticket_id": row["ticket_id"],
        "passed": passed,
        "outcome": "valid",
        "attempts": len(result.attempts),
        "category": result.triage.category,
        "priority": result.triage.priority,
        "reason": "ok" if passed else "attempts/category/priority mismatch",
    }


def main() -> int:
    rows = load_dataset(HERE / "golden-dataset.csv")
    graded = []

    for row in rows:
        expected = {
            "category": row["expected_category"],
            "priority": int(row["expected_priority"]),
        }
        try:
            result = validate_with_retry(
                row["ticket_id"], row["ticket_body"], row["first_attempt_shape"], expected
            )
            graded.append(grade(row, result, None))
        except (SchemaExhausted, InputRefused) as exc:
            graded.append(grade(row, None, exc))

    total = len(graded)
    passed = sum(1 for g in graded if g["passed"])
    valid = sum(1 for g in graded if g["outcome"] == "valid")
    refused = sum(1 for g in graded if g["outcome"] == "refused")
    exhausted = sum(1 for g in graded if g["outcome"] == "exhausted")
    leaked = sum(1 for g in graded if g["outcome"] == "leaked")

    print("=== Chapter 4: Schema Defence Evaluation ===")
    print(f"Tickets:            {total}")
    print(f"Valid outcomes:     {valid}")
    print(f"Structured refuse:  {refused}  (empty body -> InputRefused)")
    print(f"Budget exhausted:   {exhausted}  (raised SchemaExhausted)")
    print(f"Malformed leaked:   {leaked}   (must be zero)")
    print(f"Total pass:         {passed}/{total}")
    print()

    for g in graded:
        status = "PASS" if g["passed"] else "FAIL"
        cat = g.get("category", "-")
        pri = g.get("priority", "-")
        print(
            f"  [{status}] {g['ticket_id']:<6} outcome={g['outcome']:<9} "
            f"attempts={g['attempts']:<2} cat={cat:<8} pri={pri}  :: {g['reason']}"
        )

    ok = passed == total and leaked == 0
    print()
    if ok:
        print("PASS: the schema is the defence. No malformed data crossed the boundary.")
        print("      Retries carried the validation error as feedback. Exhaustion raised.")
    else:
        print("FAIL: schema defence breached. Malformed data reached the caller.")

    # Sanity: trace example is present and readable.
    (HERE / "trace-example.json").read_text()

    summary = {
        "total": total,
        "passed": passed,
        "valid": valid,
        "refused": refused,
        "exhausted": exhausted,
        "leaked": leaked,
        "max_retries": MAX_RETRIES,
    }
    print("\nSummary:", json.dumps(summary))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
