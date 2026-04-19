# Spec: Schema as the defence layer

Paired with Chapter 4, "Tactical Dispositions". Demonstrates the Instructor pattern: typed output via Pydantic, validation after the model call, structured retry with the validation error as prompting feedback.

## Intent

Every model output that crosses into application code must pass a Pydantic schema. Failures loop back to the model with the exact validation error as feedback, not a generic "try again". When the retry budget is exhausted, the boundary raises; the caller never sees malformed data.

## The three layers of defence

| Layer | What it guards | How this spec realises it |
|---|---|---|
| Input validation | Prompt variables | Sanitise and cap ticket body to 2000 chars before send. |
| Output parsing | Model response | Pydantic model with regex patterns, length caps, bounded integer ranges. |
| Tool-call whitelist | Action surface | Triage has no tools. Downstream router dispatches on `category`, a sealed enum. |

## Invariants

- Every output is a valid `Triage` instance or a structured `ValidationFailure`. Nothing in between.
- `category` is one of `bug | feature | question | noise`. Anything else is rejected.
- `priority` is an integer in `[1, 5]`. Out-of-range is rejected.
- `summary` is <= 140 characters. Longer is rejected.
- Retry budget is 3. After budget exhausted, the boundary raises. The caller handles it.
- No regex parsing of model output. No `json.loads` inside a bare try/except. The schema is the parser.

## Success criteria

- Schema-valid rate on retry: >= 95% after up to 3 attempts.
- First-attempt pass rate: recorded, but not a pass criterion (model variance is tolerated).
- Retry budget exceeded: surfaces as an exception to the caller with the last validation error attached.
- Tool-call injection: structurally impossible. The schema has no free-form command field.
- Shape drift: detected at the boundary, not three weeks later in a dashboard.

## Failure modes covered

- The string-as-contract: regex parsing of free-form text (Ch. 4).
- The optimistic JSON: `json.loads` in a try/except returning an empty dict (Ch. 4).
- The hallucinated tool call: unwhitelisted tool dispatch (Ch. 4).
- Silent shape drift: field types change; downstream code silently absorbs nulls (Ch. 4).
- The missed severity (field note): regex "Severity: critical" fails on a reworded response; default routes to informational (Ch. 4).

## Test dataset

See `golden-dataset.csv`. Each row is a ticket body, the expected `Triage` result, and the kind of malformed output the mock model emits on the first attempt. The eval shows how the retry loop corrects malformed outputs and where it refuses.
