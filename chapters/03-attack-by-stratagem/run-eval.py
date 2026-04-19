"""
Chapter 3 evaluation: role-divided agent graph.

Runs offline. No API keys, no network. Models the four roles from the book as
plain Python classes so the shape is visible without the LangGraph runtime.
The real build uses LangGraph; the contracts are the same.

Usage:
    python run-eval.py

What it does:
    1. Loads queries from golden-dataset.csv.
    2. Runs each query through Router -> Specialist -> Critic, looping on
       critic rejection up to max_iterations.
    3. Grades: routing correctness, iteration count bounded, state schema
       respected at every node boundary.

Why this shape:
    The book argues monolithic agents fail because four responsibilities
    share one prompt. This evaluator does the opposite: one prompt per role,
    typed state as the contract, the critic's verdict drives the edge.

For the wired-up version with real models and checkpoints, see:
    # from langgraph.graph import StateGraph, END
    # from litellm import completion
    # model = "claude-opus-4-7"      # specialist
    # judge = "claude-sonnet-4-7"    # router and critic
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

HERE = Path(__file__).parent

MAX_ITERATIONS = 3
ALLOWED_CATEGORIES = {"retrieval", "synthesis", "clarification"}
ALLOWED_NEXT = {
    "retrieval_specialist",
    "synthesis_specialist",
    "clarification_specialist",
    "critic",
    "END",
}


class State(TypedDict, total=False):
    """Typed state. The contract every node reads and writes through.

    LangGraph uses a TypedDict or a Pydantic model here. The point is the
    shape is declared, not inferred from a conversation log.
    """

    query: str
    category: str
    next: str
    draft: str
    citations: list[str]
    approved: bool
    critique: str
    iterations: int


# -- Router ------------------------------------------------------------------
# Classifies the query. Does not draft, does not review. Returns the next
# node to dispatch to.

RETRIEVAL_TRIGGERS = ("find", "pull", "get", "schema", "list", "rfc", "design doc")
CLARIFICATION_TRIGGERS = ("what", "something about", "the thing", "stuff")
SYNTHESIS_TRIGGERS = (
    "summarise",
    "summarize",
    "explain",
    "why",
    "compare",
    "what did we learn",
    "what did we decide",
)


class Router:
    """One job: inspect the query, pick the next node.

    In production this runs on claude-sonnet-4-7 with a short prompt. Here we
    use rule-based classification so the test is deterministic.
    """

    name = "router"

    def __call__(self, state: State) -> dict:
        query = state["query"].lower().strip()

        if len(query.split()) <= 2 or query == "what":
            return {"category": "clarification", "next": "clarification_specialist"}

        for trig in SYNTHESIS_TRIGGERS:
            if trig in query:
                return {"category": "synthesis", "next": "synthesis_specialist"}

        for trig in RETRIEVAL_TRIGGERS:
            if trig in query:
                return {"category": "retrieval", "next": "retrieval_specialist"}

        for trig in CLARIFICATION_TRIGGERS:
            if trig in query:
                return {"category": "clarification", "next": "clarification_specialist"}

        return {"category": "clarification", "next": "clarification_specialist"}


# -- Specialists -------------------------------------------------------------
# Each one does one kind of work. Reads its slice of state, writes a draft,
# hands control back to the graph. No specialist decides whether its own
# output is good enough.


class RetrievalSpecialist:
    name = "retrieval_specialist"

    def __call__(self, state: State) -> dict:
        query = state["query"]
        # Deterministic stand-in for a vector search call.
        citations = [
            f"spec://openspec/{slug(query)}.md",
            f"rfc://commons/{slug(query)}.md",
        ]
        draft = f"Found 2 sources for: {query}."
        return {"draft": draft, "citations": citations}


class SynthesisSpecialist:
    """Writes a summary. Improves draft when the critic rejects it.

    The `critique` field is how the critic's verdict reaches the next draft.
    If critique is present, treat this as a revision, not a first draft.
    """

    name = "synthesis_specialist"

    def __call__(self, state: State) -> dict:
        query = state["query"]
        critique = state.get("critique")
        prior_citations = state.get("citations", [])

        if not critique:
            # First draft. Thin on citations by design, so the critic has
            # something to push back on in a subset of queries.
            draft = f"Short answer to `{query}`. One cited source."
            citations = [f"learning://commons/{slug(query)}.md"]
        else:
            # Revision. Expand citations in response to the critique.
            draft = (
                f"Revised answer to `{query}`. "
                f"Cited two grounded sources in response to: {critique[:60]}"
            )
            citations = prior_citations + [f"spec://commons/{slug(query)}-v2.md"]

        return {"draft": draft, "citations": citations}


class ClarificationSpecialist:
    name = "clarification_specialist"

    def __call__(self, state: State) -> dict:
        query = state["query"]
        draft = (
            "I cannot answer this without more detail. "
            f"Can you say what `{query}` is about, when it happened, or what you expect back?"
        )
        return {"draft": draft, "citations": []}


# -- Critic ------------------------------------------------------------------
# Reviews the specialist's draft against its citations. Verdict drives the
# conditional edge. Pass -> END. Fail -> back to the specialist with a
# specific correction request.


QUERIES_NEEDING_REVISION = {
    "Q-003": 1,  # first draft too thin, one revision needed
    "Q-005": 1,
    "Q-009": 2,  # needs two revisions
    "Q-011": 1,
}


class Critic:
    """One job: verdict on the draft. Pass or a specific correction request.

    In the build, this runs on claude-sonnet-4-7 with a faithfulness rubric.
    Here we simulate deterministic rejection of the known-weak drafts, then
    approval once they have been revised enough times.
    """

    name = "critic"

    def __call__(self, state: State, query_id: str) -> dict:
        iterations = state.get("iterations", 0)
        needed = QUERIES_NEEDING_REVISION.get(query_id, 0)

        if iterations >= needed:
            return {"approved": True, "critique": "Citations support each assertion. Approved."}

        citations = state.get("citations", [])
        critique = (
            f"Draft asserts more than the {len(citations)} citation(s) support. "
            "Add a grounding source for each claim. Tighten the causal chain."
        )
        return {"approved": False, "critique": critique}


# -- Orchestrator ------------------------------------------------------------
# Not an agent. The map of how the roles connect. Runs the graph, caps
# iterations, records every transition so a trace can be replayed.


@dataclass
class Transition:
    step: int
    node: str
    writes: dict
    reason: str


@dataclass
class RunResult:
    query_id: str
    query: str
    final_state: State
    transitions: list[Transition] = field(default_factory=list)
    halted_by: str = ""


class Orchestrator:
    def __init__(self) -> None:
        self.router = Router()
        self.specialists = {
            "retrieval_specialist": RetrievalSpecialist(),
            "synthesis_specialist": SynthesisSpecialist(),
            "clarification_specialist": ClarificationSpecialist(),
        }
        self.critic = Critic()

    def run(self, query_id: str, query: str) -> RunResult:
        state: State = {"query": query, "iterations": 0, "citations": []}
        transitions: list[Transition] = []
        step = 0

        # Router step (runs once; stale-routing is an anti-pattern).
        step += 1
        update = self.router(state)
        state.update(update)
        transitions.append(
            Transition(step, "router", update, f"classified as {update['category']}")
        )

        specialist_name = state["next"]
        specialist = self.specialists[specialist_name]

        # Clarification is a terminal leaf. No critic, no loop.
        if specialist_name == "clarification_specialist":
            step += 1
            update = specialist(state)
            state.update(update)
            state["approved"] = True  # leaf node; trivially approved
            transitions.append(
                Transition(step, specialist_name, update, "clarification is terminal")
            )
            return RunResult(query_id, query, state, transitions, halted_by="clarification_leaf")

        # Gen/Judge loop. Specialist writes, Critic verdicts, edge decides.
        while state.get("iterations", 0) < MAX_ITERATIONS:
            step += 1
            update = specialist(state)
            state.update(update)
            transitions.append(
                Transition(step, specialist_name, update, f"iteration {state['iterations']}")
            )

            step += 1
            verdict = self.critic(state, query_id)
            state.update(verdict)
            transitions.append(
                Transition(
                    step,
                    "critic",
                    verdict,
                    "approved -> END" if verdict["approved"] else "rejected -> loop",
                )
            )

            if verdict["approved"]:
                return RunResult(query_id, query, state, transitions, halted_by="approved")

            state["iterations"] = state.get("iterations", 0) + 1
            state["citations"] = state.get("citations", [])
            # critique stays on state; specialist reads it on revision

        return RunResult(query_id, query, state, transitions, halted_by="max_iterations")


# -- Utilities ---------------------------------------------------------------


def slug(text: str) -> str:
    keep = "".join(c if c.isalnum() or c == " " else " " for c in text.lower())
    return "-".join(keep.split())[:40] or "unknown"


def load_dataset(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def grade(expected: dict, result: RunResult) -> dict:
    routed = result.transitions[0].writes
    route_ok = routed["next"] == expected["expected_specialist"]
    category_ok = routed["category"] == expected["expected_category"]

    iterations = result.final_state.get("iterations", 0)
    # clarification leaf: iteration is 0 and that is correct.
    if expected["expected_specialist"] == "clarification_specialist":
        iter_ok = iterations == 0
    else:
        iter_ok = iterations == int(expected["expected_iterations"]) - 1

    end_ok = (
        result.halted_by in ("approved", "clarification_leaf")
        and result.final_state.get("approved") is True
    )

    schema_ok = all(
        t.writes.get("next") in ALLOWED_NEXT or "next" not in t.writes
        for t in result.transitions
    ) and all(
        t.writes.get("category") in ALLOWED_CATEGORIES or "category" not in t.writes
        for t in result.transitions
    )

    passed = route_ok and category_ok and iter_ok and end_ok and schema_ok
    return {
        "query_id": expected["query_id"],
        "route_ok": route_ok,
        "category_ok": category_ok,
        "iter_ok": iter_ok,
        "end_ok": end_ok,
        "schema_ok": schema_ok,
        "iterations": iterations,
        "passed": passed,
    }


def main() -> int:
    rows = load_dataset(HERE / "golden-dataset.csv")
    orch = Orchestrator()

    results = []
    for row in rows:
        run = orch.run(row["query_id"], row["query"])
        results.append((row, run, grade(row, run)))

    total = len(results)
    passed = sum(1 for _, _, g in results if g["passed"])
    routing_ok = sum(1 for _, _, g in results if g["route_ok"])
    iter_ok = sum(1 for _, _, g in results if g["iter_ok"])
    schema_ok = sum(1 for _, _, g in results if g["schema_ok"])

    print("=== Chapter 3: Role-Divided Graph Evaluation ===")
    print(f"Queries:            {total}")
    print(f"Routing accuracy:   {routing_ok}/{total} ({routing_ok / total:.0%})")
    print(f"Iterations bounded: {iter_ok}/{total} ({iter_ok / total:.0%})")
    print(f"Schema respected:   {schema_ok}/{total} ({schema_ok / total:.0%})")
    print(f"End state approved: {sum(1 for _, _, g in results if g['end_ok'])}/{total}")
    print()

    for row, run, g in results:
        status = "PASS" if g["passed"] else "FAIL"
        route_chain = " -> ".join(t.node for t in run.transitions)
        print(
            f"  [{status}] {g['query_id']:<5} iters={g['iterations']}  "
            f"{route_chain}  :: {row['query'][:56]}"
        )

    ok = passed == total
    print()
    if ok:
        print("PASS: graph respects the contract.")
        print("      Router picks. Specialist writes. Critic verdicts. Orchestrator halts.")
    else:
        print("FAIL: graph violates the contract. Read the spec, then the trace.")

    # Sanity-check the example trace ships alongside this run.
    trace_path = HERE / "trace-example.json"
    trace_path.read_text()

    summary = {
        "total": total,
        "passed": passed,
        "routing_accuracy": routing_ok / total,
        "iteration_bounded_rate": iter_ok / total,
        "schema_compliance_rate": schema_ok / total,
        "max_iterations": MAX_ITERATIONS,
    }
    print("\nSummary:", json.dumps(summary))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
