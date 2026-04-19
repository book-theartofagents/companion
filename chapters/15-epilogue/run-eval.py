"""
Chapter 15 evaluation: the readiness scorecard.

Two outputs, one script:
    1. Validates the classifier against a synthetic golden dataset.
    2. Runs the classifier against the real chapters directory (01..13) and
       prints a readiness report.

The script exits 0 if the classifier is correct on the golden dataset. The
real scorecard is informational: its job is to surface gaps, not to fail
the build. Ch. 15 frames the checklist as a practice, not a gate.

Usage:
    python run-eval.py
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent
CHAPTERS_DIR = HERE.parent  # companion/chapters/

# The four starter practices from the epilogue.
STARTER_FILES = {
    "spec": "spec.md",
    "dataset": "golden-dataset.csv",
    "guardrail": "guardrail-config.yaml",
    "trace": "trace-example.json",
}

# Classification boundaries from spec.md.
READY_THRESHOLD = 4
IN_PROGRESS_THRESHOLD = 2


@dataclass
class ChapterState:
    chapter: str
    spec: bool
    dataset: bool
    guardrail: bool
    trace: bool

    @property
    def score(self) -> int:
        return int(self.spec) + int(self.dataset) + int(self.guardrail) + int(self.trace)

    @property
    def state(self) -> str:
        if self.score >= READY_THRESHOLD:
            return "READY"
        if self.score >= IN_PROGRESS_THRESHOLD:
            return "IN_PROGRESS"
        return "NOT_STARTED"


def classify(spec: bool, dataset: bool, guardrail: bool, trace: bool) -> tuple[int, str]:
    state = ChapterState(
        chapter="_",
        spec=spec,
        dataset=dataset,
        guardrail=guardrail,
        trace=trace,
    )
    return state.score, state.state


# --- Real scan ------------------------------------------------------------

def file_has_content(path: Path, min_bytes: int = 1) -> bool:
    """A file counts when it exists and has real content. Empty placeholders
    do not pass the check. This is the whole point of the scorecard: the
    scaffolding is not the practice.
    """
    try:
        return path.is_file() and path.stat().st_size >= min_bytes
    except OSError:
        return False


def dataset_has_rows(path: Path) -> bool:
    """Golden dataset needs a header and at least one data row."""
    if not file_has_content(path):
        return False
    try:
        with path.open() as f:
            reader = csv.reader(f)
            rows = list(reader)
        return len(rows) >= 2
    except OSError:
        return False


def guardrail_has_rules(path: Path) -> bool:
    """Guardrail config is a YAML with at least one rule. A regex is enough;
    parsing the YAML with pyyaml would be stricter but is not needed here.
    """
    if not file_has_content(path):
        return False
    try:
        text = path.read_text()
    except OSError:
        return False
    # A `rules:` top-level key plus at least one `- name:` entry.
    return "rules:" in text and "- name:" in text


def trace_has_fields(path: Path) -> bool:
    """Trace example is JSON with at least a trace_id and a metadata block."""
    if not file_has_content(path):
        return False
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return (
        isinstance(data, dict)
        and "trace_id" in data
        and "metadata" in data
    )


def spec_has_invariants(path: Path) -> bool:
    """Spec needs at least an invariants section. The heading shape varies,
    so accept a few common phrasings.
    """
    if not file_has_content(path):
        return False
    try:
        text = path.read_text().lower()
    except OSError:
        return False
    return "## invariants" in text or "invariants" in text and "success" in text


def scan_chapter(chapter_dir: Path) -> ChapterState:
    return ChapterState(
        chapter=chapter_dir.name,
        spec=spec_has_invariants(chapter_dir / STARTER_FILES["spec"]),
        dataset=dataset_has_rows(chapter_dir / STARTER_FILES["dataset"]),
        guardrail=guardrail_has_rules(chapter_dir / STARTER_FILES["guardrail"]),
        trace=trace_has_fields(chapter_dir / STARTER_FILES["trace"]),
    )


def scan_all(chapters_root: Path) -> list[ChapterState]:
    """Scan chapters 01 through 13. The epilogue looks back at the book's
    thirteen chapters; 14 and 15 are themselves the interlude and epilogue.
    """
    states: list[ChapterState] = []
    for entry in sorted(chapters_root.iterdir()):
        if not entry.is_dir():
            continue
        prefix = entry.name.split("-", 1)[0]
        if not prefix.isdigit():
            continue
        n = int(prefix)
        if n < 1 or n > 13:
            continue
        states.append(scan_chapter(entry))
    return states


# --- Classifier check against the golden dataset --------------------------

def run_classifier_tests() -> tuple[int, int]:
    with (HERE / "golden-dataset.csv").open() as f:
        rows = list(csv.DictReader(f))

    passed = 0
    print("-- Classifier tests --")
    for row in rows:
        spec = row["has_spec"] == "true"
        dataset = row["has_dataset"] == "true"
        guardrail = row["has_guardrail"] == "true"
        trace = row["has_trace"] == "true"
        score, state = classify(spec, dataset, guardrail, trace)
        expected_score = int(row["expected_score"])
        expected_state = row["expected_state"]
        ok = score == expected_score and state == expected_state
        passed += int(ok)
        tag = "PASS" if ok else "FAIL"
        print(
            f"  [{tag}] {row['scenario_id']} chapter={row['chapter']:<25s} "
            f"score={score}/{expected_score} state={state}/{expected_state}"
        )
    return passed, len(rows)


def main() -> int:
    print("=== Chapter 15: Readiness Scorecard ===")
    print(f"Chapters dir:       {CHAPTERS_DIR}")
    print()

    passed, total = run_classifier_tests()
    print(f"Classifier: {passed}/{total} passed")
    print()

    # Real scan. This is informational. It exits non-zero only if the
    # classifier itself is broken, not if individual chapters lag.
    print("-- Repository scan (chapters 01..13) --")
    states = scan_all(CHAPTERS_DIR)
    by_state: dict[str, int] = {}
    for s in states:
        by_state[s.state] = by_state.get(s.state, 0) + 1
        tag = "READY" if s.state == "READY" else ("WIP  " if s.state == "IN_PROGRESS" else "TODO ")
        print(
            f"  [{tag}] {s.chapter:<30s} spec={'Y' if s.spec else '.'} "
            f"dataset={'Y' if s.dataset else '.'} guardrail={'Y' if s.guardrail else '.'} "
            f"trace={'Y' if s.trace else '.'}  ({s.score}/4)"
        )

    print()
    ready = by_state.get("READY", 0)
    in_progress = by_state.get("IN_PROGRESS", 0)
    not_started = by_state.get("NOT_STARTED", 0)
    overall = (ready * 4 + in_progress * 2 + not_started * 0) / (max(len(states), 1) * 4)

    print(f"Chapters:           {len(states)}")
    print(f"READY:              {ready}")
    print(f"IN PROGRESS:        {in_progress}")
    print(f"NOT STARTED:        {not_started}")
    print(f"Overall readiness:  {overall:.1%}")
    print()

    ok = passed == total
    if ok:
        print("PASS: scorecard classifier is correct on the golden dataset.")
        print("      The repository scan is informational; use it to plan the next week.")
    else:
        print("FAIL: classifier is broken. Fix before relying on the scorecard.")

    summary = {
        "classifier_passed": passed,
        "classifier_total": total,
        "chapters_scanned": len(states),
        "ready": ready,
        "in_progress": in_progress,
        "not_started": not_started,
        "overall_readiness": round(overall, 3),
    }
    print("\nSummary:", json.dumps(summary))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
