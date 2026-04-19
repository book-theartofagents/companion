# Spec: Role-divided agent graph

Paired with Chapter 3, "Attack by Stratagem". Demonstrates the LangGraph pattern: one prompt per role, typed state as contract, conditional edges for control flow, a Gen/Judge loop at the centre.

## Intent

An incoming research query is handled by four named roles instead of one prompt. Router classifies intent. Specialist drafts the answer. Critic checks the draft against the sources it cites. Orchestrator moves state between roles and decides when to halt.

## The four roles

| Role | Reads | Writes | Edge condition |
|---|---|---|---|
| Router | `query` | `category`, `next` | always exits to a named specialist |
| Specialist | `query`, `category`, `critique` | `draft`, `citations` | always exits to the critic |
| Critic | `draft`, `citations` | `approved`, `critique` | approved -> END; else -> Specialist |
| Orchestrator | graph itself | nothing at runtime | caps at `max_iterations` |

The smallest interesting composition is the Gen/Judge loop: Specialist writes, Critic reviews, a conditional edge loops back on failure or exits on success.

## Invariants

- State is a typed dictionary with a fixed schema. Nodes return partial updates only.
- Each node has one responsibility. No node both drafts and critiques.
- The Critic's verdict drives the edge, not a paragraph in the draft.
- The Orchestrator caps iterations. A runaway loop is a failure mode, not a feature.
- Every transition logs the node that ran, the fields it wrote, and the reason for the edge taken.

## Success criteria

- Routing accuracy: 100% on the golden dataset. Each query reaches the expected specialist.
- Critic rejection resolves within `max_iterations = 3`. No unbounded loops.
- No node writes a field outside the state schema. Schema drift is caught at the boundary.
- Monolithic prompts do not appear in any node. Each node's instruction fits on a screen.
- Every trace can be replayed from a checkpoint. State at every step is inspectable.

## Failure modes covered

- The collapsed-responsibility agent: one prompt doing four jobs (Ch. 3).
- The implicit state machine: conversation history as state (Ch. 3).
- The premature swarm: five agents where three nodes would do (Ch. 3).
- Routing on stale state: the router fires before the previous critic ran (Ch. 3).
- Critic calibrated against the wrong metric: reviews tone, not faithfulness (Ch. 3).

## Test dataset

See `golden-dataset.csv`. Each row is a query, the specialist it should route to, the critic verdict on the first draft, and the number of iterations before approval.
