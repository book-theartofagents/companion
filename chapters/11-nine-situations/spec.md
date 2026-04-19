# Spec: Nine failure modes with named recovery strategies

Paired with Chapter 11, "The Nine Situations". Demonstrates that a generic try/except covers none of the nine. Each mode needs a named recovery strategy and a guardrail that fires on the shape of that specific failure.

## Intent

For every request the agent handles, classify the failure shape when it fails, fire the guardrail that matches, and apply the recovery strategy that shape demands. Retry. Fall back. Escalate. Abort. The caller always sees which recovery ran, never a generic "I cannot help with that."

## The nine modes

| # | Mode | Recovery family | Guardrail that fires |
|---|---|---|---|
| 1 | Ambiguous input | Escalate (clarify) | NeMo dialogue rail: clarifying turn |
| 2 | Conflicting tools | Abort + arbitrate | Precedence rule in tool registry |
| 3 | Context overflow | Abort + summarise | Token-count guard, summarisation checkpoint |
| 4 | Cascading failure | Abort (circuit) | Circuit breaker per tool |
| 5 | Hallucinated action | Abort | Tool schema whitelist |
| 6 | Infinite loop | Abort | Progress detector on plan hash |
| 7 | Partial success | Compensate | Transaction rollback + compensating action |
| 8 | Adversarial input | Abort | Guardrails AI prompt-injection validator |
| 9 | Silent wrong answer | Escalate (human) | Output validator + evaluator |

## Invariants

- Every failure is classified to exactly one mode. No "unknown" bucket.
- Every served response names the guardrail that fired, or declares none fired.
- Every escalation has a reviewer-visible reason string, not a generic apology.
- Cost budget per request is enforced. A looping agent aborts when the budget hits.
- Silent wrong answer is a specific classification, triggered by output-validator disagreement, not by exception status.

## Success criteria

- Nine modes, nine guardrails, nine traces. Each mode in the dataset routes to exactly one.
- No mode falls through to a generic exception handler.
- Recovery strategy recorded alongside the mode on every trace.
- The evaluator can reproduce the mode classification from the trace. Past-tense debuggability.

## Failure modes covered

- The optimistic architect: happy-path spec, no mode enumeration (Ch. 11).
- The fail-open handler: broad exception swallow returning empty string (Ch. 11).
- The retry-to-infinity: every failure treated as transient (Ch. 11).
- The silent wrong answer: fluent, confident, wrong (Ch. 11).

## Test dataset

See `golden-dataset.csv`. Each row is a request designed to trigger one specific mode, paired with the expected guardrail and recovery. The evaluator runs a mock agent, injects the fault, and confirms the right guardrail fires.
