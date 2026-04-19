# Spec: Durable agent workflow

Paired with Chapter 7, "Manoeuvring". Demonstrates the Temporal pattern: the workflow is a durable program with a persisted event history. Activities run once, results are recorded, replay skips past the completed work.

## Intent

Model a long-running support-triage agent as a durable workflow. The workflow must survive a worker crash mid-flight, resume on a different worker from the last completed activity, retry transient failures, and wait for a human approver without pinning the worker process.

## The Temporal primitives realised here

| Primitive | How this spec honours it |
|---|---|
| Workflow | Deterministic function. No `datetime.now`, no HTTP, no randomness in the body. |
| Activity | Named side effect. Runs once per logical step. Result persisted. |
| Retry policy | `maximum_attempts=3`, exponential backoff, non-retryable errors short-circuit. |
| Signal | `approve` signal resumes the workflow from a wait. |
| Replay | Event history drives re-execution. Completed activities return cached results. |
| TTL | Workflow has a visible deadline. Unfinished work fails in the open. |

## Invariants

- The workflow function never calls a side effect directly. Only activities do.
- Every activity has a `start_to_close_timeout`. No unbounded awaits.
- A worker crash mid-workflow does not lose state. Replay from history resumes the work.
- Human-in-the-loop waits use signals, not polling loops.
- A workflow that exceeds its TTL fails loudly. It does not sit pending forever.

## Success criteria

- Three steps: classify, draft, review. Each runs as an activity.
- Transient failure on step 2: retried up to 3 times, then succeeds.
- Permanent failure on step 2: short-circuits without retrying.
- Worker crash after step 1: replay restarts the workflow, skips step 1, resumes from step 2.
- Human approval wait: workflow pauses, worker free, signal resumes.
- End-to-end: trace carries every attempt, every retry, every replay.

## Failure modes covered

- The compounding retry: retry-blind loop hammering a degraded service (Ch. 7).
- The rigid pipeline: no fallback, no conditional routing, every failure fatal (Ch. 7).
- The single-process agent: in-memory state, lost on restart (Ch. 7).
- The lost workflow: crash mid-flight with no persisted history (Ch. 7).

## Test dataset

See `golden-dataset.csv`. Each row is a workflow invocation with a designed failure injected, paired with the expected recovery behaviour.
