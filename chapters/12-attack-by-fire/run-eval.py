"""
Chapter 12 evaluation: cookbook-first router.

Runs offline. No API keys, no network. Demonstrates the restraint principle
from the book: cookbook first, AI second, agent third, in that order.

Usage:
    python run-eval.py

What it does:
    1. Loads ten realistic analytics questions from golden-dataset.csv.
    2. Routes each one through a three-stage decision tree.
    3. Runs cookbook queries against a small in-memory dataset (or DuckDB
       if the library is available).
    4. Reports route distribution, aggregate cost, and pass/fail against
       the invariants in spec.md.

The text-to-SQL and agent stages are stubs. Real calls live in the notebook.
Here the evaluator stays deterministic so the test is reproducible.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).parent

# Cost per route, USD. Matches the table in spec.md.
COOKBOOK_COST = 0.00
TEXT_TO_SQL_COST = 0.01
AGENT_COST = 0.03


# --- The cookbook ---------------------------------------------------------
# Named, parameterised queries. This is the "institutional memory" from the
# book. Each entry is a stored query, version-controlled, human-readable.
COOKBOOK: dict[str, dict] = {
    "revenue_by_month": {
        "triggers": ["revenue by month", "monthly revenue", "revenue per month"],
        "sql": (
            "SELECT strftime(created_at, '%Y-%m') AS month, SUM(total) AS revenue "
            "FROM orders GROUP BY 1 ORDER BY 1"
        ),
    },
    "top_n_products": {
        "triggers": ["top 10 products", "top products by revenue", "best selling products"],
        "sql": (
            "SELECT product, SUM(total) AS revenue FROM orders "
            "GROUP BY product ORDER BY revenue DESC LIMIT 10"
        ),
    },
    "active_users_by_cohort": {
        "triggers": ["active users by cohort", "users by cohort", "cohort retention"],
        "sql": (
            "SELECT cohort, COUNT(DISTINCT user_id) AS active "
            "FROM events WHERE event = 'login' GROUP BY cohort"
        ),
    },
    "funnel_conversion": {
        "triggers": ["conversion rate", "funnel step", "conversion by funnel"],
        "sql": "SELECT step, users, users * 1.0 / lag(users) OVER () AS conv FROM funnel",
    },
    "customers_by_segment": {
        "triggers": ["customer count", "customers by segment", "segment breakdown"],
        "sql": "SELECT segment, COUNT(*) AS n FROM customers GROUP BY segment",
    },
}

# --- Heuristics -----------------------------------------------------------
# Text-to-SQL route: schema-bound phrasing. Looks like a lookup.
TEXT_TO_SQL_SHAPE = re.compile(
    r"\b(show|list|which|find|filter|greater than|less than|between|unpaid|exceeded|after|before)\b",
    re.IGNORECASE,
)

# Agent route: words that demand narrative or multi-step reasoning.
AGENT_SHAPE = re.compile(
    r"\b(compare|explain|why|draft|summarise|summarize|narrative|drivers|reasoning)\b",
    re.IGNORECASE,
)


# --- In-memory dataset (DuckDB fallback) ----------------------------------
ORDERS_SAMPLE = [
    {"order_id": 1, "product": "A", "total": 120.0, "created_at": "2026-01-14"},
    {"order_id": 2, "product": "B", "total": 80.0, "created_at": "2026-02-03"},
    {"order_id": 3, "product": "A", "total": 90.0, "created_at": "2026-02-18"},
    {"order_id": 4, "product": "C", "total": 200.0, "created_at": "2026-03-05"},
    {"order_id": 5, "product": "B", "total": 150.0, "created_at": "2026-03-22"},
]


@dataclass
class Call:
    question: str
    route: str  # cookbook | text_to_sql | agent
    cookbook_key: str | None
    sql: str | None
    cost_usd: float
    rows: int = 0
    guardrails_fired: list[str] = field(default_factory=list)


def cookbook_lookup(question: str) -> tuple[str, str] | None:
    q = question.lower()
    for key, entry in COOKBOOK.items():
        for trigger in entry["triggers"]:
            if trigger in q:
                return key, entry["sql"]
    return None


def run_cookbook_query(sql: str) -> int:
    """Run the cookbook query. Try DuckDB first; fall back to a tiny in-memory
    aggregation so the eval still runs when the library is missing.
    """
    try:
        import duckdb  # type: ignore[import-not-found]

        con = duckdb.connect()
        con.execute(
            "CREATE TABLE orders (order_id INT, product TEXT, total DOUBLE, created_at TIMESTAMP)"
        )
        con.executemany(
            "INSERT INTO orders VALUES (?, ?, ?, ?)",
            [(r["order_id"], r["product"], r["total"], r["created_at"]) for r in ORDERS_SAMPLE],
        )
        # Only actually execute the simple ones we prepared data for.
        if "FROM orders" in sql:
            return len(con.execute(sql).fetchall())
        return len(ORDERS_SAMPLE)
    except ModuleNotFoundError:
        # Deterministic fallback. Row count is the dataset size.
        return len(ORDERS_SAMPLE)


def route_question(question: str) -> Call:
    """Decision tree from spec.md. Cookbook first. Text-to-SQL second. Agent third.

    Agent shape wins when both it and text-to-SQL match, because narrative
    questions must not be short-circuited to a SQL template.
    """
    hit = cookbook_lookup(question)
    if hit is not None:
        key, sql = hit
        rows = run_cookbook_query(sql)
        return Call(
            question=question, route="cookbook", cookbook_key=key,
            sql=sql, cost_usd=COOKBOOK_COST, rows=rows,
        )

    if AGENT_SHAPE.search(question):
        return Call(
            question=question, route="agent", cookbook_key=None,
            sql=None, cost_usd=AGENT_COST,
        )

    if TEXT_TO_SQL_SHAPE.search(question):
        # The model proposes SQL, the app inspects before running. Here the
        # SQL is a placeholder because we do not call the model in the test.
        proposed_sql = f"-- proposed for: {question}\nSELECT ..."
        return Call(
            question=question, route="text_to_sql", cookbook_key=None,
            sql=proposed_sql, cost_usd=TEXT_TO_SQL_COST,
        )

    return Call(
        question=question, route="agent", cookbook_key=None,
        sql=None, cost_usd=AGENT_COST,
    )


def grade(expected: dict, got: Call) -> dict:
    route_ok = expected["expected_route"] == got.route
    cost_ok = abs(float(expected["expected_cost_usd"]) - got.cost_usd) < 1e-6
    if expected["cookbook_key"]:
        cookbook_ok = got.cookbook_key == expected["cookbook_key"]
    else:
        cookbook_ok = got.cookbook_key is None
    passed = route_ok and cost_ok and cookbook_ok
    return {
        "question": expected["question"],
        "route_ok": route_ok,
        "cost_ok": cost_ok,
        "cookbook_ok": cookbook_ok,
        "passed": passed,
        "got": got,
    }


def main() -> int:
    with (HERE / "golden-dataset.csv").open() as f:
        rows = list(csv.DictReader(f))

    calls = [route_question(r["question"]) for r in rows]
    results = [grade(r, c) for r, c in zip(rows, calls)]

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    cookbook_rate = sum(1 for c in calls if c.route == "cookbook") / total
    sql_rate = sum(1 for c in calls if c.route == "text_to_sql") / total
    agent_rate = sum(1 for c in calls if c.route == "agent") / total
    total_cost = sum(c.cost_usd for c in calls)

    try:
        import duckdb  # noqa: F401
        engine = "duckdb"
    except ModuleNotFoundError:
        engine = "in-memory-fallback"

    print("=== Chapter 12: Cookbook-First Router Evaluation ===")
    print(f"Engine:             {engine}")
    print(f"Questions:          {total}")
    print(f"Routed correctly:   {passed}/{total} ({passed / total:.1%})")
    print(f"Cookbook route:     {cookbook_rate:.1%}  (target >= 40%)")
    print(f"Text-to-SQL route:  {sql_rate:.1%}  (target >= 30%)")
    print(f"Agent route:        {agent_rate:.1%}  (target <= 30%)")
    print(f"Total cost (USD):   {total_cost:.2f}  (target < 0.15)")
    print()

    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        c = r["got"]
        key = c.cookbook_key or "-"
        print(
            f"  [{status}] route={c.route:<11s} key={key:<25s} "
            f"${c.cost_usd:.2f}  {r['question'][:56]}"
        )

    ok = (
        passed == total
        and cookbook_rate >= 0.40
        and sql_rate >= 0.30
        and agent_rate <= 0.30
        and total_cost < 0.15
    )

    print()
    if ok:
        print("PASS: router honours the cookbook-first contract.")
        print("      Most questions resolved without a model call.")
    else:
        print("FAIL: router violates at least one invariant.")
        print("      Re-read Ch. 12: cookbook first, AI second, agent third.")

    summary = {
        "total": total,
        "cookbook_rate": cookbook_rate,
        "text_to_sql_rate": sql_rate,
        "agent_rate": agent_rate,
        "total_cost_usd": total_cost,
    }
    print("\nSummary:", json.dumps(summary))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
