# Spec: Four formations, one task

Paired with Chapter 8, "Variation in Tactics". Demonstrates the four shapes AWS Strands ships as named primitives: Solo, Pipeline (Workflow), Swarm, Hierarchy (Graph). Applies each to the same task and records the tradeoffs.

## Intent

Take one task, "answer a customer question about recent activity", and implement it as Solo, Pipeline, Swarm, and Hierarchy. Record the latency, cost, and answer quality of each. Expose the tradeoffs at the call site so the formation choice is a decision, not an accident.

## The four formations

| Formation | Strands API | Shape | Fits when |
|---|---|---|---|
| Solo | `Agent(tools=[...])` | One agent, one loop, several tools | The work fits one model with the right tools |
| Pipeline | `Workflow(stages=[...])` | Sequential stages, fixed order | Each stage has a narrow contract and depends on the previous |
| Swarm | `Swarm(agents=[...])` | Parallel agents, merged results | Sub-problems are genuinely independent |
| Hierarchy | `Graph(planner=..., workers=[...])` | Planner decomposes, workers execute | The work decomposes cleanly and a strong planner exists |

## Invariants

- The formation is a named primitive at the call site. No hidden orchestration in the agent body.
- Solo is the default. Multi-agent must be justified by the work, not by the diagram.
- Every formation emits traces to the same OTel backend. Tradeoffs are measurable, not felt.
- Coordination overhead is attributed. Inter-agent handoffs count against the formation that caused them.
- The task is identical across formations. Only the shape differs.

## Success criteria

- Solo beats Swarm on the shared task on cost and latency. The book's claim, verified in code.
- Pipeline beats Swarm on sequential sub-tasks where each stage depends on the previous.
- Hierarchy only wins when decomposition is real. Synthetic decomposition pays the overhead without the benefit.
- Quality scores stay within a tight band across formations. The shape changes cost and latency more than it changes correctness.
- The decision-at-call-site test: a reader can name the formation from the first line of each variant.

## Failure modes covered

- The premature swarm: five agents doing sequential work (Ch. 8).
- The wrong-formation fit: pipeline implemented as swarm, swarm implemented as pipeline (Ch. 8).
- The undifferentiated multi-agent soup: agents that chat without a termination condition (Ch. 8).
- Architecture-diagram thinking: five boxes with arrows beats one box with tools on the slide, loses on the bill (Ch. 8).

## Test dataset

See `golden-dataset.csv`. Each row is a task plus its expected best-fit formation. Running all four formations against each task demonstrates the tradeoffs without hiding them.
