# Spec: Starter checklist and readiness scorecard

Paired with Chapter 15, "Epilogue: The Victorious Agent". Turns the book's closing starter list into an executable audit: does the repository embody the four practices the chapter names?

## The four starter practices

From the epilogue, unchanged:

1. **Write the spec.** Even a page.
2. **Instrument one pipeline.** Langfuse self-host is an afternoon.
3. **Build one golden dataset.** Twenty cases minimum.
4. **Add one guardrail** at a boundary that currently trusts the model.

The spec here checks these four conditions across every chapter companion folder (chapters 01 through 13) and produces a readiness scorecard.

## Intent

Given the companion directory structure, answer four questions per chapter:

- Is there a `spec.md` with at least the invariants and success-criteria headings?
- Is there a `trace-example.json` that names a model and a protocol?
- Is there a `golden-dataset.csv` with at least a header row and one data row?
- Is there a `guardrail-config.yaml` with at least one rule?

A chapter scoring four out of four is READY. Three out of four is IN PROGRESS. Two or below is NOT STARTED.

## Invariants

- The audit is read-only. It never writes into chapter folders.
- Missing files are not errors. They are a finding the report names.
- The score is a number, not a grade. Teams read the number, then the gaps.
- The four checks apply uniformly. No chapter gets special treatment.

## Success criteria

- Every chapter folder from 01 to 13 is scanned exactly once.
- Each chapter has a line in the report with its four bits and a state.
- The overall readiness number is published.
- The script exits 0 regardless of individual chapter readiness. The scorecard's job is to surface the gap, not to fail the build.

## Failure modes covered

- The checklist nobody measures (Ch. 15). Books read, nothing changed.
- Partial adoption (Ch. 15). Three of four boxes ticked is not the same as four.
- Invisible drift (Ch. 15). Specs present, datasets absent, claims unverified.

## Test dataset

See `golden-dataset.csv`. Ten readiness scenarios. Each row is a synthetic chapter state with expected classification. Tests the classifier directly, independent of the real filesystem scan.
