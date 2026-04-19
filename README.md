# The Art of Agents — Companion

Executable implementations of the principles from *The Art of Agents* by Jacob Verhoeks. One folder per chapter. Every example runs offline, no API keys required. Every library pinned to April 2026 releases.

If a chapter in the book teaches a pattern, the folder with the same number gives you the code. Run it, read the trace, compare the broken version next door. The book is the theory. This repo is the receipt.

## Quick start

**macOS / Linux (bash):**

```bash
cd book/companion
bash scripts/setup.sh
python scripts/run_all.py
```

**Windows (PowerShell):**

```powershell
cd book\companion
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
python scripts\run_all.py
```

**Any platform with Docker:**

```bash
cd book/companion
docker build -t aoa-companion .
docker run --rm aoa-companion
```

All three paths produce the same output. Docker is the reference environment. If something works there and not on your laptop, the bug is on your laptop.

## What you need

- **uv** 0.11.7 or newer. Single binary, installs Python for you if needed, identical on all three platforms. The setup scripts install it if missing.
- **Python** 3.12, 3.13, or 3.14. The Docker image uses 3.14 (the version pinned for April 2026). Older 3.12 works for the majority of examples; chapters using newer features say so in their spec.
- **Docker** 20.10+ (optional, recommended for reproducibility and CI).

No API keys. No cloud account. No Redis. No Temporal server. Every example is self-contained. Commented real-provider calls appear in each chapter's notebook for when you want to swap in a real LLM.

## Repository layout

```
book/companion/
├── README.md                    This file
├── CONTRIBUTING.md              How to add chapters, style rules
├── LICENSE                      MIT
├── Dockerfile                   Reference CI environment (Python 3.14)
├── Makefile                     Common tasks (macOS/Linux)
├── pyproject.toml               uv-compatible project definition
├── requirements.txt             Pinned versions (same list as pyproject)
├── chapters/
│   ├── 01-laying-plans/         Spec-driven agent
│   ├── 02-waging-war/           Gateway cost discipline
│   ├── 03-attack-by-stratagem/  Composition (LangGraph)
│   ├── 04-tactical-dispositions/Schema defence (Instructor, Outlines, BAML)
│   ├── 05-energy/               Tool design (MCP)
│   ├── 06-weak-points-and-strong/ Observability (Langfuse, Phoenix)
│   ├── 07-manoeuvring/          Durable workflows (Temporal)
│   ├── 08-variation-in-tactics/ Four formations (AWS Strands)
│   ├── 09-army-on-the-march/    Staged rollout (Dify)
│   ├── 10-terrain/              Enterprise terrain (LlamaIndex)
│   ├── 11-nine-situations/      Failure modes (Guardrails AI, NeMo)
│   ├── 12-attack-by-fire/       When NOT to use AI (Vanna, DuckDB)
│   ├── 13-use-of-spies/         Feedback loops (DSPy, Ragas)
│   ├── 14-interlude-terrain-shifts/ Framework ecology, MCP as protocol
│   └── 15-epilogue/             The Spec Loop, readiness checklist
├── playground/
│   ├── ch1-demo.ipynb           Interactive tour of chapter 1
│   └── ch2-demo.ipynb           Interactive tour of chapter 2
├── challenges/                  Exercises, one per chapter
└── scripts/
    ├── setup.sh                 macOS/Linux setup
    ├── setup.ps1                Windows PowerShell setup
    ├── run_all.py               Cross-platform test runner
    └── validate_structure.py    CI-friendly structural check
```

## What each chapter contains

Every chapter folder ships the same six files. The shape is deliberate. The book's Spec Loop (Chapter 13) moves between them in order.

| File | What it captures |
|---|---|
| `spec.md` | The contract. Intent, invariants, success criteria. This is the thing under version control in production. |
| `golden-dataset.csv` | Test cases with expected outcomes. Eight to twelve rows. Runs before every deploy. |
| `guardrail-config.yaml` | Rules that enforce the contract at I/O boundaries. |
| `trace-example.json` | One sample agent trace. Demonstrates the structured observability shape. |
| `run-eval.py` | Offline runnable that demonstrates the pattern and passes. Exit 0 on pass. |
| `anti-pattern-demo.py` | The broken version from the book's anti-pattern section. Runs, shows why it fails. |

## Running specific things

```bash
# One chapter
python scripts/run_all.py --chapter 3

# Skip anti-pattern demos
python scripts/run_all.py --eval-only

# Quiet summary
python scripts/run_all.py --quiet

# Structural check only (fast, under a second)
python scripts/validate_structure.py

# Interactive notebook
jupyter lab playground/
```

The Makefile wraps these for convenience on macOS and Linux:

```bash
make validate         # structural check
make test             # run every chapter
make test-one CH=3    # run one chapter
make docker-test      # reproduce CI locally
```

## Platform notes

### macOS

Tested on macOS 14+ (arm64 and x86_64). Install uv via the setup script or `brew install uv`. If you hit `python3.14: No such file`, uv will download and manage 3.14 for you.

### Linux

Tested on Debian 12 and Ubuntu 22.04/24.04 in the CI image. Python 3.12+ available on most distros. For older distros, use the Docker path.

### Windows

Tested on Windows 11 with PowerShell 7 and Git Bash. Run `scripts\setup.ps1` under PowerShell, not cmd. File paths use forward slashes inside Python, so no manual conversion needed. Long-path support enabled by default on Windows 11.

WSL2 works the same as Linux. On Windows 10 without WSL, use Docker Desktop.

### Docker

The `Dockerfile` builds a Python 3.14 image with uv and every pinned dependency. Build time on a warm cache is under 30 seconds. The image is the reference environment for CI. If your local setup produces different output, diff against Docker first.

## Provider integrations

The default runs are deterministic and offline. Real provider calls appear in two places:

1. The `playground/*.ipynb` notebooks, in commented-out cells at the end.
2. A `README.md` inside each chapter's folder (where provided), showing how to swap in LiteLLM, Anthropic, OpenAI, or Bedrock.

Set the keys you need and only the keys you need:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
export LANGFUSE_PUBLIC_KEY=pk-...
export LANGFUSE_SECRET_KEY=sk-...
```

The Docker image deliberately does not forward environment variables from the host. If you want a real provider call inside the image, pass the key explicitly: `docker run --env ANTHROPIC_API_KEY=... --rm aoa-companion`.

## Versions (April 2026)

| Package | Version | Purpose |
|---|---|---|
| Python | 3.14 | Target; 3.12 and 3.13 also supported |
| uv | 0.11.7 | Package and venv manager |
| ragas | 0.4.3 | Evaluation metrics |
| dspy-ai | 3.1.3 | Feedback loops (chapter 13) |
| langfuse | 4.2.0 | Observability (chapter 6) |
| litellm | 1.83.0 | Gateway (chapter 2) |
| anthropic | 0.60+ | Direct SDK for real calls |
| openai | 2.31.0 | Direct SDK for real calls |
| pydantic | 2.12.5 | Schema validation (chapter 4) |
| instructor | 1.12+ | Structured outputs (chapter 4) |
| pandas | 3.0.2 | Dataset handling |
| duckdb | 1.3+ | SQL terrain (chapters 2, 12) |
| langgraph | 0.6+ | Composition (chapter 3) |
| pyyaml | 6.0.3 | Guardrail configs |

See `requirements.txt` and `pyproject.toml` for the full pinned list.

## Troubleshooting

**`uv: command not found` after setup.** The installer puts uv in `~/.local/bin`. Add that to your `PATH` or start a new shell.

**`No module named 'litellm'` inside a chapter.** The chapter imports the module inside a `try/except` because the examples run offline. If you see this, either you ran the script outside the venv, or `pip install` failed silently. `make validate` catches the former.

**Docker build fails on `apt-get update`.** Usually a corporate network proxy. Set `HTTP_PROXY` and `HTTPS_PROXY` and rebuild, or use the host Python path.

**Notebook cells produce stale output.** Notebooks ship empty-output. Re-execute with `Run All` after opening. Jupyter writes output back into the `.ipynb` file. Don't commit that.

**Python 3.14 not available on your distro.** Let uv handle it: `uv venv --python 3.14 .venv` downloads a managed 3.14 interpreter. Works without root.

## Contribution

To add a chapter:

1. Copy the structure from `chapters/01-laying-plans/` as a template.
2. Write the spec against the principle the chapter teaches.
3. Build the golden dataset from scenarios in the book's field note.
4. Write `run-eval.py` that passes and `anti-pattern-demo.py` that fails loudly.
5. Update the chapter index above.

See `CONTRIBUTING.md` for the full style rules.

## License

MIT. See `LICENSE`.

## Credits

Written by Jacob Verhoeks. Book available at theartofagents.com. Anti-patterns drawn from field notes in the book. Library choices reflect the April 2026 ecology, which the interlude (Chapter 14) makes clear is moving faster than anything else in software.

> "The best agent doesn't use the most powerful model. It uses the right tool at the right time."
>
> — The Art of Agents, Chapter 2
