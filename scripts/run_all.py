"""
Run every chapter's eval and anti-pattern demo. Cross-platform. No shell.

Usage:
    python scripts/run_all.py              # run everything
    python scripts/run_all.py --eval-only  # skip anti-pattern demos
    python scripts/run_all.py --chapter 3  # one chapter only
    python scripts/run_all.py --quiet      # summary output only

Exit code is 0 iff every run-eval.py exited 0. Anti-pattern demos are
informational and do not affect the exit code (they are meant to show
failure, so their exit codes are ignored).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAPTERS_DIR = ROOT / "chapters"


def chapter_dirs() -> list[Path]:
    return sorted(d for d in CHAPTERS_DIR.iterdir() if d.is_dir() and d.name[0].isdigit())


def run_script(script: Path, *, timeout: int = 60) -> tuple[int, str, float]:
    start = time.monotonic()
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=script.parent,
        )
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {timeout}s", time.monotonic() - start
    elapsed = time.monotonic() - start
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output, elapsed


def summarise(label: str, exit_code: int, output: str, elapsed: float, *, quiet: bool) -> None:
    status = "PASS" if exit_code == 0 else "FAIL"
    print(f"  [{status}] {label:<40s} ({elapsed:5.2f}s)")
    if not quiet and exit_code != 0:
        print("    --- output ---")
        for line in output.splitlines()[-20:]:
            print(f"    {line}")
        print("    --------------")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run every chapter's evaluation")
    parser.add_argument("--eval-only", action="store_true", help="Skip anti-pattern demos")
    parser.add_argument("--chapter", type=int, help="Run only this chapter (1-15)")
    parser.add_argument("--quiet", action="store_true", help="Print less output")
    args = parser.parse_args()

    if not CHAPTERS_DIR.exists():
        print(f"No chapters directory at {CHAPTERS_DIR}")
        return 2

    chapters = chapter_dirs()
    if args.chapter is not None:
        chapters = [c for c in chapters if c.name.startswith(f"{args.chapter:02d}-")]
        if not chapters:
            print(f"No chapter matching --chapter {args.chapter}")
            return 2

    print(f"Running {len(chapters)} chapter(s) from {CHAPTERS_DIR}\n")
    print("=" * 72)
    print("EVALUATIONS")
    print("=" * 72)

    eval_failures: list[str] = []
    for ch in chapters:
        script = ch / "run-eval.py"
        if not script.exists() or script.stat().st_size == 0:
            print(f"  [SKIP] {ch.name:<40s} (no run-eval.py)")
            continue
        code, output, elapsed = run_script(script)
        summarise(ch.name, code, output, elapsed, quiet=args.quiet)
        if code != 0:
            eval_failures.append(ch.name)

    if not args.eval_only:
        print()
        print("=" * 72)
        print("ANTI-PATTERN DEMOS (informational, failures expected)")
        print("=" * 72)
        for ch in chapters:
            script = ch / "anti-pattern-demo.py"
            if not script.exists() or script.stat().st_size == 0:
                print(f"  [SKIP] {ch.name:<40s} (no anti-pattern-demo.py)")
                continue
            code, output, elapsed = run_script(script)
            # For anti-pattern demos, a crash is a failure. Non-zero exit is OK.
            crashed = "Traceback" in output
            status = "CRASH" if crashed else "RAN"
            print(f"  [{status}] {ch.name:<40s} ({elapsed:5.2f}s)")
            if crashed and not args.quiet:
                for line in output.splitlines()[-10:]:
                    print(f"    {line}")

    print()
    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)
    total = len(chapters)
    passed = total - len(eval_failures)
    print(f"Evaluations: {passed}/{total} passed")
    if eval_failures:
        print(f"Failures:    {', '.join(eval_failures)}")
        return 1
    print("All chapter evaluations passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
