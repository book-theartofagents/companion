"""
Chapter 3 anti-pattern: the monolithic agent.

Three failure shapes from the book:
    1. The collapsed-responsibility agent: one prompt doing four jobs.
    2. The implicit state machine: conversation history as state.
    3. The premature swarm: five agents where three nodes would do.

Runs offline. Contrasts one 4000-word prompt doing everything with the
graph version in run-eval.py.

Usage:
    python anti-pattern-demo.py
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).parent


# -- Anti-pattern #1: the God Prompt, one step up ----------------------------
# Four responsibilities folded into a single string. Each responsibility pulls
# the prompt in a different direction. Routing wants terse, synthesis wants
# deep, critique wants adversarial, formatting wants rigid.

GOD_PROMPT = """\
You are a research assistant. You will:

1. Classify the user's query as retrieval, synthesis, or clarification.
2. If retrieval, search the knowledge base and return sources.
3. If synthesis, summarise the relevant sources into a grounded answer.
4. If clarification, ask the user for more detail.
5. After drafting, check your own answer against your own sources.
6. If the check fails, revise silently and try again.
7. If still wrong, apologise and return what you have.

Be confident. Be humble. Be fast. Be thorough. Do not invent sources.
If a source is missing, make a reasonable guess, clearly labelled.
Prefer short answers. Provide detail when asked. Handle edge cases gracefully.

(Added by Alice, 2025-10-11, after the hallucination incident.)
(Added by Bob, 2025-12-04, after the routing incident.)
(Added by Carol, 2026-02-03, after the recursion incident.)
(Added by Dan, 2026-03-15, because the critic now apologises too much.)
""" * 4  # the real one is ~4000 words


@dataclass
class MonolithOutput:
    """What the God Prompt emits. Plausible prose. No seam to intervene at."""

    text: str
    cited_role: str = "unknown"  # which of the four jobs did this?
    edge_reason: str = "model picked"


def monolith_agent(query: str, history: list[str]) -> MonolithOutput:
    """One agent, one prompt, four jobs.

    The output is a paragraph. Nothing declares which job produced which
    sentence. Nothing separates the route from the draft, or the draft
    from the critique. The model's own prose is the state machine.
    """
    # Failure 1: the prompt is stuffed. Four responsibilities compete.
    _ = GOD_PROMPT  # loaded on every call

    # Failure 2: the state IS the history. Implicit state machine.
    context = "\n".join(history[-10:])

    # Plausible output that looks like it worked.
    text = (
        f"Sure, I looked into `{query}`. I think it's probably a synthesis "
        f"question, so I searched the knowledge base and found some stuff. "
        f"I'm fairly confident the answer is {context[:40] if context else 'yes'}. "
        f"Let me know if you want more detail."
    )
    return MonolithOutput(text=text)


# -- Anti-pattern #2: the premature swarm -----------------------------------
# Five agents cooperating through a bespoke message bus. Each message is
# another LLM call. The coordination cost dominates the actual work.


@dataclass
class SwarmCall:
    agent: str
    prompt_tokens: int
    output_tokens: int
    latency_ms: int


def premature_swarm(query: str) -> list[SwarmCall]:
    """A system that should be three graph nodes, splayed into five services.

    Each agent is a separate prompt, a separate model call, a separate place
    the team debugs from. The coordination happens over a message bus.
    """
    return [
        SwarmCall("router_agent", prompt_tokens=800, output_tokens=40, latency_ms=520),
        SwarmCall("retrieval_agent", prompt_tokens=1200, output_tokens=200, latency_ms=1800),
        SwarmCall("synthesis_agent", prompt_tokens=1600, output_tokens=300, latency_ms=2400),
        SwarmCall("critic_agent", prompt_tokens=900, output_tokens=120, latency_ms=1100),
        SwarmCall("orchestrator_agent", prompt_tokens=700, output_tokens=60, latency_ms=600),
    ]


# -- Eval --------------------------------------------------------------------


@dataclass
class RunStats:
    total_tokens: int = 0
    cost_usd: float = 0.0
    debuggable: bool = False
    seams: int = 0
    writes_fields_named: bool = False
    outputs: list[str] = field(default_factory=list)


def run_monolith(rows: list[dict]) -> RunStats:
    stats = RunStats()
    history: list[str] = []
    for row in rows:
        out = monolith_agent(row["query"], history)
        history.append(row["query"])
        # Rough token accounting: God Prompt every call + query + history.
        prompt_tokens = len(GOD_PROMPT) // 4 + len(row["query"]) // 4 + len(history) * 20
        output_tokens = len(out.text) // 4
        stats.total_tokens += prompt_tokens + output_tokens
        # Opus pricing ballpark for illustration.
        stats.cost_usd += prompt_tokens * 15 / 1_000_000 + output_tokens * 75 / 1_000_000
        stats.outputs.append(out.text[:60])
    stats.debuggable = False
    stats.seams = 0
    stats.writes_fields_named = False
    return stats


def run_swarm(rows: list[dict]) -> RunStats:
    stats = RunStats()
    for row in rows:
        calls = premature_swarm(row["query"])
        prompt = sum(c.prompt_tokens for c in calls)
        output = sum(c.output_tokens for c in calls)
        stats.total_tokens += prompt + output
        stats.cost_usd += prompt * 15 / 1_000_000 + output * 75 / 1_000_000
        stats.outputs.append(f"five-agent chain for `{row['query'][:40]}`")
    # Debuggable in the sense that there are agents, but each agent has its
    # own prompt, and the seams are concealed behind a message bus.
    stats.debuggable = False
    stats.seams = 5
    stats.writes_fields_named = False
    return stats


def main() -> None:
    with (HERE / "golden-dataset.csv").open() as f:
        rows = list(csv.DictReader(f))

    mono = run_monolith(rows)
    swarm = run_swarm(rows)

    print("=== Chapter 3: Anti-Pattern (Monolithic vs Premature Swarm) ===")
    print(f"Queries replayed:   {len(rows)}")
    print()

    print("The God Prompt (one agent, four jobs):")
    print(f"  Total tokens:       {mono.total_tokens:,}")
    print(f"  Cost (USD):         {mono.cost_usd:.3f}")
    print(f"  Seams to intervene: {mono.seams}")
    print(f"  Debug protocol:     read prompt, read output, guess")
    print(f"  Sample output:      {mono.outputs[0]}...")
    print()

    print("The Premature Swarm (five agents over a message bus):")
    print(f"  Total tokens:       {swarm.total_tokens:,}")
    print(f"  Cost (USD):         {swarm.cost_usd:.3f}")
    print(f"  Agents per query:   5")
    print(f"  Latency per query:  ~6.5s (sum of chain)")
    print(f"  Coordination cost:  5 prompts x 12 queries = 60 prompts to maintain")
    print()

    print("Three failures, one root cause:")
    print("  1. Collapsed responsibility: four jobs in one prompt -> no seam to intervene at.")
    print("  2. Implicit state: conversation log is the state -> cannot hand off, cannot replay.")
    print("  3. Premature swarm: five agents -> five times the cost for work a graph would do.")
    print()
    print("What is missing in all three: a real orchestrator. A typed state schema. Named")
    print("nodes with named writes. A critic whose verdict drives an edge that code can read.")
    print()
    print("Compare to run-eval.py:")
    print("  Four roles, one graph, typed state, bounded iterations, every step replayable.")


if __name__ == "__main__":
    main()
