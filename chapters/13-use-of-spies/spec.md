# Spec: The Spec Loop in miniature

Paired with Chapter 13, "The Use of Spies". Demonstrates the feedback loop that closes the thirteen chapters: run the agent on a golden dataset, measure, find the failures, propose spec deltas, re-run, record the delta.

## Intent

Prove, in one script, that an agent can be measured, that the measurements surface failures, that the failures produce a structured delta, and that the delta measurably improves the agent on the next run. No external API calls. A deterministic heuristic stands in for Ragas metrics and for the DSPy optimiser.

## The three signals

| Signal | Source | Scope in this example |
|---|---|---|
| Human feedback | Thumbs up/down, free text | Baked into the golden dataset as reference answers and acceptance notes. |
| Automated feedback | Metrics on a fixed set | Faithfulness and answer-correctness heuristics compute per item. |
| Self-reflection | Agent reviews its trace | A judge signature reruns the question against the spec, flags the failing scenario. |

## Invariants

- Every run evaluates against a versioned golden dataset. No running blind.
- Metrics are deterministic in the test path. LLM-as-judge appears in commented real-call examples only.
- When a metric drops below threshold, the loop produces a spec delta, not a fix-the-prompt note.
- The delta is a first-class artefact: structured, reviewable, mergeable.
- The optimiser's "improvement" is measured on the same dataset before and after.

## Success criteria

- Baseline run produces a number. A real number, not a vibe.
- At least two failures detected on a 10-item dataset.
- A delta proposal is generated for each failure, keyed by scenario id.
- Post-optimisation run shows measurable improvement against the baseline.
- Drift guardrail fires when the post-run score drops below the rolling average.

## Failure modes covered

- The vibes-driven release: shipped without a measurement (Ch. 13).
- The one-off evaluation: a photograph of a river (Ch. 13).
- The judge with no calibration: confident stranger returning numbers (Ch. 13).
- The outdated golden dataset: six months since last update (Ch. 13).

## Composition with DSPy and Ragas

The notebook example composes the real libraries:

- Ragas supplies the metric (faithfulness, answer_correctness).
- DSPy wraps the agent as a program with signatures.
- The optimiser tunes the program against the Ragas score.

Here the metric is a small deterministic heuristic. The shape is the same.

## Test dataset

See `golden-dataset.csv`. Ten questions from a fictional Proefballon support agent, with reference answers, retrieved context (for faithfulness), and acceptance notes (for correctness).
