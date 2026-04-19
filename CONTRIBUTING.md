# Contributing

This companion is the executable half of *The Art of Agents*. Every chapter ships six files and a notebook, and each one demonstrates a principle from the book in code you can run.

## Ground rules

- **No live API keys required.** Every `run-eval.py` and `anti-pattern-demo.py` runs offline against canned traces. Real API calls go in commented examples, never in the happy path.
- **One principle per chapter.** If an example drifts into adjacent territory, split it out. Readers pair each chapter with its folder; don't make them hunt.
- **Versions pinned to April 2026 releases.** See `requirements.txt`. When you bump a version, re-run every chapter's eval.
- **Book terminology.** Proefballon, Commons, BYOK, OpenSpec, the five constants (Contract, Context, Terrain, Model, Protocol). Use these, not synonyms.

## File layout per chapter

```
chapters/NN-name/
├── spec.md                # Intent, invariants, success criteria
├── golden-dataset.csv     # Test cases with expected outcomes
├── trace-example.json     # One exemplar agent trace
├── guardrail-config.yaml  # Rules enforcing constraints
├── run-eval.py            # Runnable evaluation script (offline)
└── anti-pattern-demo.py   # Contrasting broken implementation
playground/chN-demo.ipynb  # Interactive notebook
```

## Adding a chapter

1. Copy the structure from `chapters/01-laying-plans/` as a template.
2. Write the spec against the principle the chapter teaches.
3. Build the golden dataset from scenarios in the book's field note.
4. Write `run-eval.py` that passes and `anti-pattern-demo.py` that fails loudly.
5. Update the root `README.md` chapter index.

## Running the suite

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# Run one chapter
python chapters/01-laying-plans/run-eval.py

# Run them all
for f in chapters/*/run-eval.py; do python "$f"; done
```

## Style

British English. No em dashes. Short sentences land the point. Longer ones explain the mechanism.
