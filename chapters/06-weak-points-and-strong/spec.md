# Spec: Trace-first observability for agents

Paired with Chapter 6, "Weak Points and Strong". Demonstrates the trace-first pattern from Langfuse and Phoenix: every agent step is a span with token, cost, and metadata attached, so operational questions are queries instead of grep archaeology.

## Intent

Every agent invocation emits a structured trace. Every span on the trace carries the fields that operators and evaluators actually ask about: feature, user, model, prompt version, token counts, latency, cost, cache hit, fallback fired. The trace store answers questions about production by filter and group-by, not by text search.

## The two audiences

| Audience | Tool they reach for | What this spec supplies |
|---|---|---|
| Production engineer | Langfuse | Trace tree per request, filterable by user, feature, model, cost. |
| Evaluator | Phoenix | Same traces, exported as a dataframe, gradable by scenario id. |

## Invariants

- Every agent invocation produces exactly one trace with a stable `trace_id`.
- Every span declares `name`, `start`, `end`, `parent_span_id`, and `metadata`.
- Every generation span carries `model`, `prompt_version`, token counts, and `cost_usd`.
- No span records a timestamp in its prompt prefix. Cache keys stay stable.
- No log line carries information that is missing from the trace.

## Success criteria

- p95 latency per feature: queryable directly from the trace store.
- Cost per feature per day: a group-by, not a spreadsheet.
- Cache hit rate at steady state: >= 70%.
- Fallback firing rate: visible per feature, per model, per hour.
- Silent wrong answer detection: every trace joins with an evaluator result by `trace_id`.

## Failure modes covered

- The print-statement tracer: prose logs, no hierarchy, no attribution (Ch. 6).
- The dashboard that shows volume: aggregates that cannot answer "which step" (Ch. 6).
- The silent wrong answer: 200 OK, grammatical, wrong, never evaluated (Ch. 6, Ch. 11).
- Prompt drift without provenance: trace cannot name the prompt version that produced the output (Ch. 6).

## Test dataset

See `golden-dataset.csv`. Each row is a synthesised trace outcome for a real operational question: p95 latency on the `support.answer` feature, cost attribution to `user_42`, which calls fell back to `claude-sonnet-4-7`, which ran against the wrong prompt version.
