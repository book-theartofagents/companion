#!/usr/bin/env bash
# Unix setup script. Mac and Linux. Use scripts/setup.ps1 on Windows.
#
# Installs uv if missing, creates a venv, installs dependencies, runs
# chapters 1 and 2 as a smoke test.
#
# Usage: bash scripts/setup.sh

set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

echo "=== Art of Agents Companion: setup ==="

if ! command -v uv >/dev/null 2>&1; then
    echo "uv not found. Installing from https://astral.sh/uv/install.sh ..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # shellcheck disable=SC1091
    source "${HOME}/.local/bin/env" 2>/dev/null || export PATH="${HOME}/.local/bin:${PATH}"
fi

echo "uv version: $(uv --version)"

if [ ! -d .venv ]; then
    echo "Creating virtual environment at .venv ..."
    uv venv --python 3.14 .venv || uv venv .venv
fi

echo "Installing dependencies ..."
uv pip install --python .venv/bin/python -r requirements.txt

echo ""
echo "=== Smoke test: chapters 1 and 2 ==="
./.venv/bin/python chapters/01-laying-plans/run-eval.py
echo ""
./.venv/bin/python chapters/02-waging-war/run-eval.py

echo ""
echo "=== Setup complete ==="
echo "Activate with:  source .venv/bin/activate"
echo "Run all:        python scripts/run_all.py"
echo "Run in Docker:  docker build -t aoa-companion . && docker run --rm aoa-companion"
