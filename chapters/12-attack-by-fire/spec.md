# Spec: Cookbook-first router with AI as last resort

Paired with Chapter 12, "The Attack by Fire". Demonstrates the restraint pattern: cookbook queries run first, narrow text-to-SQL (Vanna.ai-shaped) runs second, a full agent runs only when the input shape demands it.

## Intent

Route every incoming question down the cheapest path that can answer it correctly. Count calls to the model. Count calls to the deterministic path. Prove, on real traffic, that most questions do not need AI.

## The three routes

| Route | When it wins | Cost per call |
|---|---|---|
| Cookbook | The question matches a named, parameterised query | USD 0.00 (CPU only) |
| Text-to-SQL | The schema is stable but the phrasing is new each time | USD 0.01 (bounded template lookup) |
| Agent | Multi-step reasoning the SQL grammar cannot express | USD 0.03 (LLM call) |

## Invariants

- Cookbook hits never call the model. A keyword or intent match is sufficient.
- Text-to-SQL emits SQL as an inspectable artefact before any row is read.
- Full agent calls are counted, tagged, and capped per feature flag.
- At least 70% of a representative question stream must route to cookbook or text-to-SQL. If the split tilts toward the agent, the cookbook is missing entries, not the model.

## Success criteria

- Cookbook hit rate >= 40%.
- Text-to-SQL rate >= 30%.
- Agent rate <= 30%.
- Aggregate cost on the golden dataset: under USD 0.15 for 10 questions.
- Every question logs its route, its cost, and the shape that won.

## Failure modes covered

- The LLM Hammer: every request treated as a reasoning problem (Ch. 12).
- The LLM as calculator: aggregation pushed to the model, not the database (Ch. 12).
- The agent over the rules engine: pure functions wrapped in a prompt (Ch. 12).
- The AI status meeting: model choice displacing the user-value conversation (Ch. 12).

## Test dataset

See `golden-dataset.csv`. Each row is a realistic question from a conversational analytics audience, tagged with the route that should win. The field note in Chapter 12 describes the eighty-two percent collapse this spec makes operational.
