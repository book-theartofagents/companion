"""
Validate that every chapter has the six required files and a playground
notebook. Lint-level check, runs in under a second. Use in CI before the
longer `run_all.py` so structural breaks fail fast.

Usage:
    python scripts/validate_structure.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAPTERS_DIR = ROOT / "chapters"
PLAYGROUND_DIR = ROOT / "playground"

REQUIRED_FILES = [
    "spec.md",
    "golden-dataset.csv",
    "guardrail-config.yaml",
    "trace-example.json",
    "run-eval.py",
    "anti-pattern-demo.py",
]


def check_chapter(chapter_dir: Path) -> list[str]:
    errors: list[str] = []
    for name in REQUIRED_FILES:
        path = chapter_dir / name
        if not path.exists():
            errors.append(f"missing: {name}")
        elif path.stat().st_size == 0:
            errors.append(f"empty: {name}")
    trace = chapter_dir / "trace-example.json"
    if trace.exists() and trace.stat().st_size > 0:
        try:
            json.loads(trace.read_text())
        except json.JSONDecodeError as e:
            errors.append(f"invalid trace JSON: {e}")
    return errors


def check_notebook(chapter_num: int) -> list[str]:
    nb = PLAYGROUND_DIR / f"ch{chapter_num}-demo.ipynb"
    if not nb.exists():
        return [f"missing notebook: {nb.name}"]
    if nb.stat().st_size == 0:
        return [f"empty notebook: {nb.name}"]
    try:
        data = json.loads(nb.read_text())
        if "cells" not in data:
            return [f"malformed notebook: {nb.name} (no cells)"]
    except json.JSONDecodeError as e:
        return [f"invalid notebook JSON: {nb.name} ({e})"]
    return []


def main() -> int:
    chapters = sorted(d for d in CHAPTERS_DIR.iterdir() if d.is_dir() and d.name[0].isdigit())
    total_errors = 0
    print(f"Validating {len(chapters)} chapters in {CHAPTERS_DIR}\n")
    for ch in chapters:
        errors = check_chapter(ch)
        chapter_num = int(ch.name.split("-")[0])
        # Notebooks only expected for chapters 1 and 2 as starting point;
        # others are optional but checked if present.
        nb_errors = check_notebook(chapter_num) if chapter_num <= 2 else []
        all_errors = errors + nb_errors
        if all_errors:
            print(f"  [FAIL] {ch.name}")
            for err in all_errors:
                print(f"         {err}")
            total_errors += len(all_errors)
        else:
            print(f"  [OK]   {ch.name}")
    print()
    if total_errors:
        print(f"FAIL: {total_errors} structural issue(s) across chapters")
        return 1
    print("All chapters structurally valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
