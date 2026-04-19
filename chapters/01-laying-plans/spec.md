# Spec: Spec-driven coding agent

Paired with Chapter 1, "Laying Plans". Demonstrates the OpenSpec pattern: a delta captures intent before code moves, and the agent's output is graded against the contract, not the prompt.

## Intent

Given an OpenSpec delta (ADDED/MODIFIED/REMOVED requirements with GIVEN/WHEN/THEN scenarios), the agent must produce a patch that satisfies every scenario. Nothing more. Nothing less.

## The five constants

| Constant | Realised in this chapter |
|---|---|
| Contract | `delta.md` with scenarios (see `golden-dataset.csv`) |
| Context | The delta itself. No repo map, no prompt folklore. |
| Terrain | Offline evaluator. No model call, no network. |
| Model | Swappable. Default is a stub that replays canned outputs. |
| Protocol | JSON trace per attempt, graded by scenario coverage. |

## Invariants

- Every scenario in the delta must map to at least one test in the agent's output.
- The agent must refuse when the delta omits a required acceptance criterion.
- The agent must cite the scenario id it is satisfying, not the prompt.
- Output patches must be reviewable in under five minutes.

## Success criteria

- Scenario coverage: 100%. Every `#### Scenario:` in the delta has a matching assertion.
- Spec drift: 0. The agent does not invent requirements the delta did not state.
- Silent failure rate: 0. When the delta is ambiguous, the agent returns a structured refusal, not a best guess.

## Failure modes covered

- The unanchored agent: prompts without a spec above them (Ch. 1).
- The God Prompt: accumulated instructions drifting from any contract (Ch. 1).
- Prompt-as-code without spec-as-source: intent trapped in application code (Ch. 1).
- Silent wrong answer: output passes schema checks but violates intent (Ch. 11).

## Test dataset

See `golden-dataset.csv`. Each row is a delta scenario paired with the expected agent behaviour.
