"""
Chapter 2 anti-pattern: the uncapped agent.

Three failure shapes from the book:
    1. The token black hole: no attribution, spend diffuses.
    2. Replay-everything agents: full history on every turn.
    3. The prompt cache that wasn't: timestamp in system prefix breaks the key.

Runs offline. Prints the cost of each anti-pattern, contrasted with the
gateway version in run-eval.py.

Usage:
    python anti-pattern-demo.py
"""

from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent


@dataclass
class UncappedCall:
    question: str
    input_tokens: int
    cache_hit: bool
    cost_usd: float
    replayed_history_tokens: int = 0


# The knowledge base the book's team prepended on every call, "in case the
# ticket referenced an unusual product". This is the shape of the bug, not
# an indictment of knowledge bases.
KNOWLEDGE_BASE_TOKENS = 40_000


def uncapped_agent(question: str, history: list[str]) -> UncappedCall:
    """Anti-pattern. Replays full history, rebuilds system prompt with a
    timestamp (breaking cache), sends everything to the LLM even when a SQL
    query would answer it in milliseconds.
    """
    # Failure 1: no routing. Every question goes to the LLM.
    # Failure 2: replay everything. Tokens grow linearly with turns.
    history_tokens = sum(len(h) // 4 + 10 for h in history)

    # Failure 3: timestamp in the system prefix, fresh on every call, kills
    # the cache key. The book calls this "the prompt cache that wasn't".
    system_prompt = (
        f"You are a helpful assistant. "
        f"Current time: {dt.datetime.now().isoformat()}. "
        f"Answer the user's question."
    )
    system_tokens = len(system_prompt) // 4

    user_tokens = len(question) // 4 + 20
    input_tokens = system_tokens + KNOWLEDGE_BASE_TOKENS + history_tokens + user_tokens

    # No cache hit ever, because the prefix changes each call.
    cache_hit = False

    # Claude Opus pricing (April 2026 ballpark, for illustration only):
    #   input:  $15 per 1M tokens
    #   output: $75 per 1M tokens
    cost_usd = round(input_tokens * 15 / 1_000_000 + 120 * 75 / 1_000_000, 4)

    return UncappedCall(
        question=question,
        input_tokens=input_tokens,
        cache_hit=cache_hit,
        cost_usd=cost_usd,
        replayed_history_tokens=history_tokens,
    )


def main() -> None:
    with (HERE / "golden-dataset.csv").open() as f:
        rows = list(csv.DictReader(f))

    # Simulate a growing conversation. Each question after the first replays
    # the prior ones as "history", which is exactly the anti-pattern.
    history: list[str] = []
    calls: list[UncappedCall] = []
    for row in rows:
        q = row["question"]
        calls.append(uncapped_agent(q, history))
        history.append(q)

    total_tokens = sum(c.input_tokens for c in calls)
    total_cost = sum(c.cost_usd for c in calls)
    cache_hits = sum(1 for c in calls if c.cache_hit)

    # Book field note: 300k tickets/week. Extrapolate one week from this run.
    weekly_cost = total_cost / len(calls) * 300_000

    print("=== Chapter 2: Anti-Pattern (Uncapped Agent) ===")
    print(f"Calls:              {len(calls)}")
    print(f"Total input tokens: {total_tokens}")
    print(f"Cache hit rate:     {cache_hits / len(calls):.1%}  (should be >= 70%)")
    print(f"Per-call cost:      USD {total_cost / len(calls):.3f}")
    print(f"Total cost (USD):   {total_cost:.2f}")
    print(f"At 300k tickets/wk: USD {weekly_cost:,.0f}")
    print()

    for c in calls:
        print(
            f"  tokens={c.input_tokens:6d}  history={c.replayed_history_tokens:4d}  "
            f"cache={'HIT' if c.cache_hit else 'MISS'}  ${c.cost_usd:.3f}  "
            f"{c.question[:60]}"
        )

    print()
    print("Three failures in one agent:")
    print("  1. Token black hole: every question is an LLM call, even `which customers spent over $10k?`.")
    print(f"  2. Replay-everything: {KNOWLEDGE_BASE_TOKENS:,} KB tokens on every call plus growing history.")
    print("  3. Cache that wasn't: timestamp in the system prefix makes the cache key unique per call.")
    print()
    print("Compare (same traffic):")
    print("  run-eval.py          (gateway pattern)  ~ USD 0.20 for 10 calls.")
    print(f"  anti-pattern-demo.py (uncapped agent)   USD {total_cost:.2f} for 10 calls.")
    print()
    print(f"At production scale (300k tickets/wk), this is the $83k/month invoice from the book.")


if __name__ == "__main__":
    main()
