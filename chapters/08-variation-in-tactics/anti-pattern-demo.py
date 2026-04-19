"""
Chapter 8 anti-pattern: the wrong formation.

Three failure shapes from the book:
    1. The premature swarm: five agents doing work that fits one.
    2. The wrong-formation fit: pipeline-as-swarm and swarm-as-pipeline.
    3. The undifferentiated multi-agent soup: agents that chat without a
       termination condition.

Runs offline. Replays the book's document-processing field note in code:
five agents, $4/request, 80s latency, then the refactor to a solo agent
with four tools at $0.40/request and 12s latency.

Usage:
    python anti-pattern-demo.py
"""

from __future__ import annotations

import csv
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).parent
random.seed(42)


# -- Anti-pattern #1: the premature swarm --------------------------------
@dataclass
class AgentMetrics:
    name: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    cost_usd: float


def premature_swarm() -> tuple[list[AgentMetrics], int]:
    """Five-agent document-processing system from the field note. Each
    agent prompt explains what the other four agents have already done.
    Half the tokens are coordination overhead."""
    # Each agent pays the cost of describing the others to themselves.
    per_agent_coordination = 1800  # tokens spent explaining the shape
    metrics = [
        AgentMetrics("intake", 2100, 320, 11_000, 0.64),
        AgentMetrics("classify", 2400, 260, 14_000, 0.72),
        AgentMetrics("parse", 3100, 520, 22_000, 1.10),
        AgentMetrics("validate", 2200, 280, 13_000, 0.70),
        AgentMetrics("store", 1600, 160, 8_000, 0.40),
    ]
    return metrics, per_agent_coordination


def refactored_solo() -> AgentMetrics:
    """One agent, four tools, one loop. The fix from the field note."""
    return AgentMetrics(
        name="document_agent (solo + 4 tools)",
        tokens_in=1200,
        tokens_out=360,
        latency_ms=12_000,
        cost_usd=0.40,
    )


# -- Anti-pattern #2: the wrong-formation fit ----------------------------
def pipeline_as_swarm(stages: int = 4) -> dict:
    """Sequential work forced into parallel execution. Each stage waits
    for the previous, so the swarm serialises itself. The framework
    overhead of parallelism is paid with none of the benefit."""
    stage_latency_ms = 2400
    overhead_per_handoff = 800  # message bus, context transport, merge prep
    # Stages cannot run in parallel because each needs the previous one's
    # output. The swarm degenerates to a slow pipeline with extra cost.
    latency = stages * stage_latency_ms + (stages - 1) * overhead_per_handoff
    cost = 0.30 * stages + 0.05 * (stages - 1)
    return {"shape": "pipeline-as-swarm", "latency_ms": latency, "cost_usd": round(cost, 2)}


def swarm_as_pipeline(candidates: int = 3) -> dict:
    """Independent sub-problems forced into sequence. Three approaches
    that could have run concurrently in ten seconds now take thirty."""
    per_candidate_latency_ms = 10_000
    latency = candidates * per_candidate_latency_ms
    cost = 0.12 * candidates
    return {"shape": "swarm-as-pipeline", "latency_ms": latency, "cost_usd": round(cost, 2)}


# -- Anti-pattern #3: the undifferentiated multi-agent soup --------------
@dataclass
class SoupChatter:
    """Agents that prompt each other with no shared state, no termination
    condition, no named formation. The happy path produces an answer.
    The unhappy path runs until a token budget cuts it off."""

    agents: list[str] = field(default_factory=lambda: ["planner", "critic", "doer", "reviewer"])
    turns: list[tuple[str, str]] = field(default_factory=list)
    token_budget: int = 8000
    tokens_used: int = 0

    def run(self) -> dict:
        speakers = list(self.agents)
        while self.tokens_used < self.token_budget:
            # Pick who speaks next. There is no contract. They "figure it out".
            speaker = speakers[len(self.turns) % len(speakers)]
            listener = speakers[(len(self.turns) + 1) % len(speakers)]
            tokens = 300 + random.randint(50, 200)
            self.tokens_used += tokens
            self.turns.append((speaker, f"-> {listener} (tokens={tokens})"))
        return {
            "shape": "soup",
            "turns": len(self.turns),
            "tokens_burned": self.tokens_used,
            "termination": "token_budget_cutoff",
            "final_answer": "partial (the model ran out of budget mid-thought)",
        }


def main() -> None:
    print("=== Chapter 8: Anti-Pattern Demo ===")
    print()

    # 1. Premature swarm. The field-note document processor.
    print("-- 1. The premature swarm --")
    agents, coord_per = premature_swarm()
    total_latency = sum(a.latency_ms for a in agents) + 1000 * (len(agents) - 1)  # bus hops
    total_cost = sum(a.cost_usd for a in agents)
    total_coord = coord_per * len(agents)
    print(f"Agents:              {len(agents)}")
    print(f"Total latency:       {total_latency / 1000:.1f} s  (book: 80s)")
    print(f"Total cost per doc:  USD {total_cost:.2f}  (book: ~$4)")
    print(f"Coordination tokens: {total_coord} per document (half of the tokens are coordination)")
    print()
    print("The refactor (same work, solo formation, four tools):")
    solo = refactored_solo()
    print(f"Agents:              1")
    print(f"Latency:             {solo.latency_ms / 1000:.1f} s  (book: 12s)")
    print(f"Cost per doc:        USD {solo.cost_usd:.2f}  (book: ~$0.40)")
    print(f"Ratio:               {total_cost / solo.cost_usd:.0f}x cost saved, {total_latency / solo.latency_ms:.0f}x faster.")
    print()

    # 2. Wrong-formation fit.
    print("-- 2. The wrong-formation fit --")
    paf = pipeline_as_swarm()
    sap = swarm_as_pipeline()
    print(f"Pipeline-as-swarm:  latency={paf['latency_ms']/1000:.1f}s cost=USD {paf['cost_usd']}")
    print("  Sequential stages forced into a swarm. They serialise anyway.")
    print("  You pay parallel overhead with none of the benefit.")
    print()
    print(f"Swarm-as-pipeline:  latency={sap['latency_ms']/1000:.1f}s cost=USD {sap['cost_usd']}")
    print("  Independent candidates forced into sequence.")
    print("  Three approaches that could have run in ten seconds take thirty.")
    print()

    # 3. Undifferentiated multi-agent soup.
    print("-- 3. The undifferentiated multi-agent soup --")
    soup = SoupChatter()
    r = soup.run()
    print(f"Agents in the chat:  {len(soup.agents)}")
    print(f"Turns exchanged:     {r['turns']}")
    print(f"Tokens burned:       {r['tokens_burned']}")
    print(f"Termination:         {r['termination']}")
    print(f"Final answer:        {r['final_answer']}")
    print()
    print("The interaction diagram cannot be drawn because the interactions are emergent.")
    print("The happy path works. The unhappy path has no affordance because it was not designed.")
    print()

    # Book's question: if you removed one agent, would the work still get done?
    print("-- Decision-box question --")
    print("If you removed one agent from the design, would the work still get done?")
    print()
    print("Solo (refactored):     yes, by definition, nothing to remove.")
    print("Pipeline:              no; each stage has a narrow contract.")
    print("Swarm:                 maybe; the merge has fewer inputs.")
    print("Hierarchy:             maybe; the planner rebalances.")
    print("Premature swarm:       yes, usually. That is the diagnosis.")
    print()

    # Reference the golden dataset for completeness.
    with (HERE / "golden-dataset.csv").open() as f:
        rows = list(csv.DictReader(f))
    counts: dict[str, int] = {}
    for r in rows:
        k = r["expected_best_formation"]
        counts[k] = counts.get(k, 0) + 1
    print(f"Best-fit distribution across {len(rows)} tasks: {counts}")
    print("Solo dominates because most problems fit solo once the tools are defined.")


if __name__ == "__main__":
    main()
    sys.exit(0)
