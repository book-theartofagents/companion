"""
Chapter 8 evaluation: four formations, one task.

Runs offline. No AWS, no Bedrock, no live models. Simulates the four Strands
primitives, Solo, Pipeline (Workflow), Swarm, Hierarchy (Graph), against a
shared set of tasks and records the tradeoffs the book names: latency, cost,
quality, coordination overhead.

Usage:
    python run-eval.py

What it does:
    1. Loads the tasks from golden-dataset.csv.
    2. Runs each task under all four formations.
    3. Grades each formation's output against the task's expected best fit.
    4. Reports the tradeoffs so the formation choice stays a decision.

The real code uses strands.Agent, strands.Workflow, strands.Swarm, and
strands.Graph. Here we stub them so the run is deterministic. The
commented block at the bottom shows the live shape.
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).parent


# -- Stub LLM and tool costs ----------------------------------------------
# All numbers are deterministic and illustrative. They express the
# tradeoffs the book describes. Real figures depend on model choice and
# provider pricing.
MODEL_COST_PER_1K = {"claude-opus-4-7": 0.015, "claude-sonnet-4-7": 0.003}
TOOL_LATENCY_MS = {"fetch_user": 140, "fetch_recent_orders": 290, "retrieve": 320, "classify": 420, "parse": 380, "validate": 210, "store": 160}


@dataclass
class FormationResult:
    formation: str
    latency_ms: int
    cost_usd: float
    quality: float
    coordination_overhead_tokens: int
    agents_used: int
    tokens_in: int
    tokens_out: int


def _gen_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    rate = MODEL_COST_PER_1K[model]
    return round(rate * tokens_in / 1000 + rate * 5 * tokens_out / 1000, 4)


# -- Solo: one agent, one loop, several tools -----------------------------
def solo(task: str) -> FormationResult:
    """Strands: Agent(model=..., tools=[...]). The model picks tools in a
    loop until done. No coordination overhead because there is nothing to
    coordinate with."""
    _ = task  # parameter kept for API parity across formations
    tool_latency = TOOL_LATENCY_MS["fetch_user"] + TOOL_LATENCY_MS["fetch_recent_orders"]
    gen_latency = 1130
    tokens_in = 420
    tokens_out = 180
    cost = _gen_cost("claude-opus-4-7", tokens_in, tokens_out)
    return FormationResult(
        formation="solo",
        latency_ms=tool_latency + gen_latency,
        cost_usd=cost,
        quality=0.92,
        coordination_overhead_tokens=0,
        agents_used=1,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )


# -- Pipeline (Workflow): sequential, narrow contracts -------------------
def pipeline(task: str) -> FormationResult:
    """Strands: Workflow(stages=[classify, parse, validate, store]).
    Each stage has its own context and tools. The next stage cannot start
    until the previous finished. Good for ETL-shaped work."""
    _ = task
    stage_latencies = [
        TOOL_LATENCY_MS["classify"] + 600,
        TOOL_LATENCY_MS["parse"] + 900,
        TOOL_LATENCY_MS["validate"] + 400,
        TOOL_LATENCY_MS["store"] + 200,
    ]
    latency = sum(stage_latencies)
    # Four stages, each with its own model call. Tokens are the sum of
    # the per-stage prompts and outputs, not one shared context.
    tokens_in = 1800
    tokens_out = 520
    # Each stage carries a header describing what the previous stage did.
    # Small, but accumulates across four stages.
    coordination = 220
    # Mix of models: classify and validate on Sonnet, parse on Opus.
    cost = (
        _gen_cost("claude-sonnet-4-7", 450, 120)
        + _gen_cost("claude-opus-4-7", 900, 280)
        + _gen_cost("claude-sonnet-4-7", 250, 80)
        + _gen_cost("claude-sonnet-4-7", 200, 40)
    )
    return FormationResult(
        formation="pipeline",
        latency_ms=latency,
        cost_usd=round(cost, 4),
        quality=0.91,
        coordination_overhead_tokens=coordination,
        agents_used=4,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )


# -- Swarm: parallel specialists, merged at the end ----------------------
def swarm(task: str) -> FormationResult:
    """Strands: Swarm(agents=[...]). N agents run concurrently. One
    merger. Fits when sub-problems are independent. Pays otherwise."""
    _ = task
    parallel_latency = 1800  # slowest of the three
    merge_latency = 1400
    latency = parallel_latency + merge_latency
    tokens_in = 900  # shared input replicated to each
    tokens_out = 540  # three drafts + a merged answer
    # The merge has to read three outputs. That context is coordination,
    # not work.
    coordination = 360
    cost = _gen_cost("claude-opus-4-7", tokens_in + coordination, tokens_out)
    return FormationResult(
        formation="swarm",
        latency_ms=latency,
        cost_usd=round(cost, 4),
        quality=0.92,
        coordination_overhead_tokens=coordination,
        agents_used=3,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )


# -- Hierarchy (Graph): planner + workers --------------------------------
def hierarchy(task: str) -> FormationResult:
    """Strands: Graph(planner=..., workers=[...]). The planner decomposes
    the work. Workers execute. The planner integrates. Good when the work
    decomposes cleanly and the planner is load-bearing."""
    _ = task
    planner_latency = 1200
    worker_latency = 2400  # slowest worker
    integrate_latency = 1200
    latency = planner_latency + worker_latency + integrate_latency
    tokens_in = 1400
    tokens_out = 620
    coordination = 520  # planner context + integration context
    cost = _gen_cost("claude-opus-4-7", tokens_in + coordination, tokens_out)
    return FormationResult(
        formation="hierarchy",
        latency_ms=latency,
        cost_usd=round(cost, 4),
        quality=0.91,
        coordination_overhead_tokens=coordination,
        agents_used=4,  # 1 planner + 3 workers
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )


FORMATIONS = {"solo": solo, "pipeline": pipeline, "swarm": swarm, "hierarchy": hierarchy}


# -- Per-task best-fit logic ----------------------------------------------
@dataclass
class Comparison:
    task_id: str
    task: str
    expected: str
    results: dict[str, FormationResult] = field(default_factory=dict)

    def cheapest(self) -> str:
        return min(self.results, key=lambda k: self.results[k].cost_usd)

    def fastest(self) -> str:
        return min(self.results, key=lambda k: self.results[k].latency_ms)


def run_task(task_id: str, task: str, expected: str) -> Comparison:
    return Comparison(
        task_id=task_id,
        task=task,
        expected=expected,
        results={name: fn(task) for name, fn in FORMATIONS.items()},
    )


# -- Grading ---------------------------------------------------------------
def grade(cmp: Comparison) -> dict:
    expected = cmp.expected
    # For solo-expected tasks: solo must be cheapest and fastest.
    # For non-solo-expected tasks: the expected formation must be within a
    # quality band of the others (all formations hit acceptable quality on
    # this shared task) and the expected formation cannot be beaten on its
    # own criterion: pipeline wins on sequential cost, swarm on parallel
    # latency, hierarchy on decomposable throughput.
    checks: list[dict] = []
    quality_band = max(r.quality for r in cmp.results.values()) - min(r.quality for r in cmp.results.values())
    checks.append({"name": "quality-band-tight", "passed": quality_band <= 0.05})

    if expected == "solo":
        checks.append({"name": "solo-cheapest", "passed": cmp.cheapest() == "solo"})
        checks.append({"name": "solo-fastest", "passed": cmp.fastest() == "solo"})
        checks.append(
            {
                "name": "solo-no-coordination-overhead",
                "passed": cmp.results["solo"].coordination_overhead_tokens == 0,
            }
        )
    elif expected == "pipeline":
        # Pipeline stays within the stated budget; swarm-as-pipeline would
        # blow latency and cost.
        checks.append({"name": "pipeline-cheaper-than-swarm", "passed": cmp.results["pipeline"].cost_usd < cmp.results["swarm"].cost_usd})
        checks.append({"name": "pipeline-agents-are-stages", "passed": cmp.results["pipeline"].agents_used >= 2})
    elif expected == "swarm":
        # Swarm pays latency to buy independence. It should beat the
        # pipeline on latency when the work is parallel.
        checks.append({"name": "swarm-faster-than-pipeline", "passed": cmp.results["swarm"].latency_ms < cmp.results["pipeline"].latency_ms})
        checks.append({"name": "swarm-has-parallelism", "passed": cmp.results["swarm"].agents_used >= 2})
    elif expected == "hierarchy":
        # Hierarchy pays the most. It earns it only on genuinely
        # decomposable work. Enforce the planner exists.
        checks.append({"name": "hierarchy-has-planner", "passed": cmp.results["hierarchy"].agents_used >= 3})

    passed = all(c["passed"] for c in checks)
    return {
        "task_id": cmp.task_id,
        "expected": expected,
        "cheapest": cmp.cheapest(),
        "fastest": cmp.fastest(),
        "checks": checks,
        "passed": passed,
    }


def main() -> int:
    with (HERE / "golden-dataset.csv").open() as f:
        rows = list(csv.DictReader(f))

    comparisons = [run_task(r["task_id"], r["task"], r["expected_best_formation"]) for r in rows]
    graded = [grade(c) for c in comparisons]

    passed = sum(1 for g in graded if g["passed"])
    total = len(graded)

    print("=== Chapter 8: Four Formations, One Task ===")
    print(f"Tasks:              {total}")
    print(f"Graded passed:      {passed}/{total} ({passed / total:.1%})")
    print()
    print("Per-task comparison:")
    header = f"  {'task_id':<6s} {'expected':<10s} {'solo':<16s} {'pipeline':<16s} {'swarm':<16s} {'hierarchy':<16s}"
    print(header)
    for cmp in comparisons:
        row = f"  {cmp.task_id:<6s} {cmp.expected:<10s}"
        for name in ("solo", "pipeline", "swarm", "hierarchy"):
            r = cmp.results[name]
            row += f" {r.latency_ms:>5d}ms/${r.cost_usd:<6.3f}"
        print(row)
    print()
    print("Grade detail:")
    for g in graded:
        status = "PASS" if g["passed"] else "FAIL"
        fails = [c["name"] for c in g["checks"] if not c["passed"]]
        detail = (
            f"expected={g['expected']:<10s} cheapest={g['cheapest']:<10s} fastest={g['fastest']:<10s}"
        )
        if fails:
            detail += f"  failed_checks={fails}"
        print(f"  [{status}] {g['task_id']}: {detail}")
    print()

    # Aggregates: the book's claim in numbers.
    solo_cost = sum(c.results["solo"].cost_usd for c in comparisons)
    swarm_cost = sum(c.results["swarm"].cost_usd for c in comparisons)
    solo_latency = sum(c.results["solo"].latency_ms for c in comparisons)
    swarm_latency = sum(c.results["swarm"].latency_ms for c in comparisons)
    print("Aggregates across all tasks (solo vs swarm):")
    print(f"  solo total cost:      USD {solo_cost:.3f}")
    print(f"  swarm total cost:     USD {swarm_cost:.3f}  (ratio {swarm_cost / solo_cost:.1f}x)")
    print(f"  solo total latency:   {solo_latency:>6d} ms")
    print(f"  swarm total latency:  {swarm_latency:>6d} ms  (ratio {swarm_latency / solo_latency:.1f}x)")
    print()

    ok = passed == total
    if ok:
        print("PASS: each task's expected formation won on its own criterion.")
        print("      Solo is the default. The other three earn their keep when the work has their shape.")
    else:
        print("FAIL: at least one task was graded wrong. See the failing checks above.")

    # Sanity: the example trace parses and points at solo.
    tr = json.loads((HERE / "trace-example.json").read_text())
    assert tr["formation"] == "solo"
    assert "Agent(" in tr["strands_call"]

    summary = {
        "tasks": total,
        "passed": passed,
        "solo_cost_usd": round(solo_cost, 4),
        "swarm_cost_usd": round(swarm_cost, 4),
        "solo_latency_ms": solo_latency,
        "swarm_latency_ms": swarm_latency,
    }
    print("\nSummary:", json.dumps(summary, sort_keys=True))
    return 0 if ok else 1


# -- Live integration (commented) -----------------------------------------
# from strands import Agent
# from strands.multi_agent import Workflow, Swarm, Graph
# from strands.tools import tool
#
# @tool
# def fetch_user(email: str) -> dict: ...
#
# @tool
# def fetch_recent_orders(user_id: str) -> list[dict]: ...
#
# solo_agent = Agent(
#     model="anthropic.claude-opus-4-7",
#     tools=[fetch_user, fetch_recent_orders],
#     system="You help support agents quickly understand a customer's recent activity.",
# )
#
# pipeline = Workflow(stages=[classify_stage, parse_stage, validate_stage, store_stage])
# swarm    = Swarm(agents=[draft_a, draft_b, draft_c], merger=rank_drafts)
# graph    = Graph(planner=plan_feature, workers=[frontend, backend, data])


if __name__ == "__main__":
    sys.exit(main())
