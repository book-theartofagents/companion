"""
Chapter 13 anti-pattern: the vibes-driven loop.

Three shapes from the book, all on one team:
    1. Vibes-driven release: shipped because "it feels better".
    2. One-off evaluation: a score taken at launch, never re-run.
    3. Judge with no calibration: a number with no grounding in human grades.

Runs offline. Makes the cost of skipping the harness visible.

Usage:
    python anti-pattern-demo.py
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent

# Seed so the "vibes" are reproducible. In real life vibes are not.
random.seed(13)


@dataclass
class VibeRun:
    version: str
    days_since_launch: int
    engineer_feeling: str   # "better", "same", "worse"
    pm_feeling: str
    demo_screenshot_count: int
    customer_thumbs_down_rate: float  # ground truth, never measured
    dataset_size: int       # zero in the anti-pattern
    score_recorded: float | None  # a single photograph of a river


def release_on_vibes(version: str, days_since_launch: int, thumbs_down_truth: float) -> VibeRun:
    """The team agrees the release feels better. No dataset. No score.
    The truth about customer thumbs-down sits behind a dashboard nobody opens.
    """
    return VibeRun(
        version=version,
        days_since_launch=days_since_launch,
        engineer_feeling=random.choice(["better", "better", "same", "worse"]),
        pm_feeling=random.choice(["better", "better", "better", "same"]),
        demo_screenshot_count=random.randint(1, 4),
        customer_thumbs_down_rate=thumbs_down_truth,
        dataset_size=0,
        score_recorded=None,
    )


def one_off_evaluation(dataset_size: int) -> float:
    """The team ran a single evaluation at launch. Everyone applauded.
    Nothing re-ran. Six months later the number is still on the slide.
    """
    return 0.87  # the score from launch week, which nobody revisits


def uncalibrated_judge(answer_length: int) -> float:
    """A model judging another model. Rewards verbosity. Rewards echoes of
    the question. Never compared against human grades.
    """
    # Longer answer -> higher score. The judge "prefers detail".
    return min(0.55 + answer_length / 200, 0.99)


def main() -> None:
    with (HERE / "golden-dataset.csv").open() as f:
        rows = list(csv.DictReader(f))

    # Six months of releases. Ground truth drifts. Team does not notice.
    true_thumbs_down = [0.08, 0.10, 0.12, 0.15, 0.19, 0.24]
    runs = [
        release_on_vibes(f"v1.{i}", 30 * i, td)
        for i, td in enumerate(true_thumbs_down, start=1)
    ]

    launch_score = one_off_evaluation(len(rows))
    verbose_scores = [uncalibrated_judge(len(r["reference_answer"]) * k) for k, r in enumerate(rows, 1)]

    print("=== Chapter 13: Anti-Pattern (Vibes-Driven Loop) ===")
    print(f"Dataset size used for regression: {runs[0].dataset_size}  (should be >= 20)")
    print(f"Launch score (never refreshed):   {launch_score:.2f}  (stuck on the slide)")
    print("Judge calibrated against humans:  no")
    print()

    print("-- Releases (six months, no regression) --")
    for run in runs:
        print(
            f"  {run.version}  eng={run.engineer_feeling:<6s} "
            f"pm={run.pm_feeling:<6s}  screenshots={run.demo_screenshot_count}  "
            f"ground-truth thumbs-down={run.customer_thumbs_down_rate:.0%}  "
            f"measured={run.score_recorded}"
        )
    print()

    final = runs[-1].customer_thumbs_down_rate
    launch = runs[0].customer_thumbs_down_rate
    drift = final - launch
    print(f"Actual quality drift (never measured): {launch:.0%} -> {final:.0%} ({drift:+.0%})")
    print()

    print("-- Uncalibrated judge scores --")
    for row, score in zip(rows, verbose_scores, strict=False):
        print(f"  {row['scenario_id']}  judge_score={score:.2f}  ({len(row['reference_answer']):>3d} char reference)")
    print()
    print(f"Judge rewards length. Longest answers get {max(verbose_scores):.2f}.")
    print("User satisfaction does not move. The team optimises for the judge.")
    print()

    print("Three shapes in one team (Ch. 13):")
    print("  1. Vibes-driven release: every decision sits on 'feels better'.")
    print("  2. One-off evaluation: 0.87 at launch, nothing since, no comparable number today.")
    print("  3. Uncalibrated judge: confident stranger dressed as a metric.")
    print()
    print("Compare run-eval.py: real dataset, deterministic metrics, structured deltas, number that moves.")


if __name__ == "__main__":
    main()
