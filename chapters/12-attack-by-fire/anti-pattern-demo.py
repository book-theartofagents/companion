"""
Chapter 12 anti-pattern: the LLM hammer.

Three shapes from the book, collapsed into one agent that treats every
question as a reasoning problem:
    1. LLM as calculator (sums and averages via the model, not SQL).
    2. Agent over the rules engine (business logic behind a prompt).
    3. AI status meeting (every feature starts with "can we add AI?").

Runs offline. Contrasts the bill with run-eval.py's cookbook-first router.

Usage:
    python anti-pattern-demo.py
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent


# --- Anti-pattern: the reasoning-first agent ------------------------------
# Every question goes to the LLM because "the agent is more flexible".
LLM_PROMPT = (
    "You are a senior analyst. "
    "Answer the question using the company's data. "
    "Do the arithmetic in your head. "
    "Apply the pricing rules from memory. "
    "Handle edge cases with judgement."
)


@dataclass
class HammerCall:
    question: str
    model: str
    input_tokens: int
    cost_usd: float
    would_have_been_cookbook: bool
    would_have_been_rules_engine: bool


# Claude Opus pricing, April 2026 ballpark, input tokens only for illustration.
#   $15 per million input tokens
#   $75 per million output tokens
INPUT_PRICE_PER_TOKEN = 15 / 1_000_000
OUTPUT_PRICE_PER_TOKEN = 75 / 1_000_000


def hammer_agent(question: str) -> HammerCall:
    """Every question gets the same treatment: stuff the full system prompt
    plus a schema dump plus the question into the LLM, ignore the shape of
    the input entirely.
    """
    schema_dump_tokens = 2_400  # "in case the question references a rare table"
    system_tokens = len(LLM_PROMPT) // 4
    user_tokens = len(question) // 4 + 20
    input_tokens = system_tokens + schema_dump_tokens + user_tokens
    output_tokens = 180

    cost_usd = round(
        input_tokens * INPUT_PRICE_PER_TOKEN + output_tokens * OUTPUT_PRICE_PER_TOKEN,
        4,
    )

    # Flag the shape this question really was.
    q = question.lower()
    cookbook_shape = any(
        s in q for s in ["revenue by month", "top 10", "cohort", "conversion", "customer count"]
    )
    rules_shape = any(
        s in q for s in ["discount", "tier", "threshold", "eligibility", "pricing"]
    )

    return HammerCall(
        question=question,
        model="claude-opus-4-7",
        input_tokens=input_tokens,
        cost_usd=cost_usd,
        would_have_been_cookbook=cookbook_shape,
        would_have_been_rules_engine=rules_shape,
    )


def main() -> None:
    with (HERE / "golden-dataset.csv").open() as f:
        rows = list(csv.DictReader(f))

    calls = [hammer_agent(r["question"]) for r in rows]
    total_cost = sum(c.cost_usd for c in calls)
    cookbook_shaped = sum(1 for c in calls if c.would_have_been_cookbook)
    rules_shaped = sum(1 for c in calls if c.would_have_been_rules_engine)

    # Book field note scale: the 300k-ticket team paid USD 8,000/month for a
    # reasoning-first analytics agent. Extrapolate one month here.
    monthly_cost = total_cost / len(calls) * 300_000

    print("=== Chapter 12: Anti-Pattern (LLM Hammer) ===")
    print(f"Questions:          {len(calls)}")
    print(f"Total cost (USD):   {total_cost:.2f}  (vs 0.15 for cookbook-first)")
    print(f"Questions that were cookbook-shaped: {cookbook_shaped}")
    print(f"Questions that were rules-shaped:    {rules_shaped}")
    print(f"Monthly at 300k tickets: USD {monthly_cost:,.0f}")
    print()

    for c in calls:
        tags = []
        if c.would_have_been_cookbook:
            tags.append("COOKBOOK-SHAPED")
        if c.would_have_been_rules_engine:
            tags.append("RULES-SHAPED")
        tag_str = ", ".join(tags) if tags else "ambiguous"
        print(
            f"  tokens={c.input_tokens:5d}  ${c.cost_usd:.3f}  [{tag_str:20s}]  "
            f"{c.question[:56]}"
        )

    print()
    print("Three shapes in play (Ch. 12):")
    print("  1. LLM as calculator: 'revenue by month' routed to the model,")
    print("     not the database. Non-deterministic, slow, wrong on decimals.")
    print("  2. Agent over the rules engine: 'discount greater than 30 percent'")
    print("     could be a WHERE clause, not a reasoning step.")
    print("  3. AI status meeting: every question assumed to need AI because")
    print("     the agent is the team's only tool.")
    print()
    print("Compare the same ten questions through run-eval.py:")
    print("  run-eval.py          (cookbook first)   ~ USD 0.06 aggregate.")
    print(f"  anti-pattern-demo.py (LLM hammer)        USD {total_cost:.2f} aggregate.")
    print()
    print("The fix is not more model. The fix is the cookbook nobody wrote.")


if __name__ == "__main__":
    main()
