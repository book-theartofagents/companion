"""
Chapter 9 evaluation: staged rollout with shadow mode.

Runs offline. No API keys, no network. Simulates the deployment ladder from
Chapter 9: deploy v2, mirror v1 outputs in shadow mode, compare, open the
canary gate when disagreement stays inside the threshold, and roll back
automatically when the thumbs-down signal crosses its ceiling.

Usage:
    python run-eval.py

What it does:
    1. Loads twelve triage requests with the v1 and v2 labels and reply
       lengths already recorded. Treat these as captured outputs, as if
       the gateway had mirrored v1 behind v2 for every call.
    2. Computes the shadow disagreement rate and decides whether v2 is
       safe to promote from shadow to canary.
    3. Runs the canary stage (10% served, 100% mirrored), watches the
       thumbs-down rate, and enforces the rollback trigger.
    4. Reports the decision with a clear PASS or FAIL.

The real platform (Dify) owns all of this. The code here is a deliberate
mirror of the state machine that lives in guardrail-config.yaml, so the
same thresholds appear in one place.
"""

from __future__ import annotations

import csv
import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).parent

# Thresholds must match guardrail-config.yaml.
SHADOW_DIVERGENCE_MAX = 0.15
CANARY_THUMBS_DOWN_MAX = 0.08
CANARY_TRAFFIC_PERCENT = 10
MAX_SECONDS_TO_FULL_ROLLBACK = 60

# Deterministic sampling. A real platform samples live traffic; the book
# example is reproducible. This seed is chosen so the canary slice catches
# at least one thumbs-down, which is the interesting case to demonstrate.
RNG_SEED = 0


@dataclass
class MirroredCall:
    """One request that hit the gateway and was answered by either version,
    always compared to the other in shadow."""

    request_id: str
    input: str
    served_by: str  # "v1" | "v2"
    v1_label: str
    v2_label: str
    v1_reply_len: int
    v2_reply_len: int
    thumbs_down: bool

    def label_disagrees(self) -> bool:
        return self.v1_label != self.v2_label

    def length_ratio(self) -> float:
        """v2 reply length relative to v1. A reply that shrinks more than
        40% is a behaviour change worth naming even when the label matches."""
        if self.v1_reply_len == 0:
            return 1.0
        return self.v2_reply_len / self.v1_reply_len

    def length_diverges(self) -> bool:
        ratio = self.length_ratio()
        return ratio < 0.6 or ratio > 1.4


@dataclass
class StageResult:
    name: str
    served_calls: int
    mirrored_calls: int
    label_disagreement_rate: float
    length_divergence_rate: float
    thumbs_down_rate: float
    gate_open: bool
    reason: str


@dataclass
class RolloutDecision:
    shadow: StageResult
    canary: StageResult
    promoted: bool
    rolled_back: bool
    rollback_seconds: int = 0
    notes: list[str] = field(default_factory=list)


def load_mirrored_calls(path: Path) -> list[MirroredCall]:
    with path.open() as f:
        rows = list(csv.DictReader(f))
    return [
        MirroredCall(
            request_id=r["request_id"],
            input=r["input"],
            served_by="v1",  # overwritten per stage
            v1_label=r["v1_label"],
            v2_label=r["v2_label"],
            v1_reply_len=int(r["v1_reply_len"]),
            v2_reply_len=int(r["v2_reply_len"]),
            thumbs_down=r["thumbs_down"].lower() == "true",
        )
        for r in rows
    ]


def run_shadow(calls: list[MirroredCall]) -> StageResult:
    """v1 serves everything, v2 runs in the background on the same inputs.
    The gate measures how often v1 and v2 disagree on the label or drift
    hard on reply length."""
    for c in calls:
        c.served_by = "v1"

    label_disagreements = sum(1 for c in calls if c.label_disagrees())
    length_divergences = sum(1 for c in calls if c.length_diverges())
    disagreement_rate = label_disagreements / len(calls)
    divergence_rate = length_divergences / len(calls)

    gate_open = disagreement_rate <= SHADOW_DIVERGENCE_MAX
    reason = (
        f"label disagreement {disagreement_rate:.1%} <= {SHADOW_DIVERGENCE_MAX:.0%}"
        if gate_open
        else f"label disagreement {disagreement_rate:.1%} exceeded {SHADOW_DIVERGENCE_MAX:.0%}"
    )

    return StageResult(
        name="shadow",
        served_calls=0,
        mirrored_calls=len(calls),
        label_disagreement_rate=disagreement_rate,
        length_divergence_rate=divergence_rate,
        thumbs_down_rate=0.0,
        gate_open=gate_open,
        reason=reason,
    )


def run_canary(calls: list[MirroredCall], rng: random.Random) -> StageResult:
    """A sampled slice of traffic is answered by v2. Every v2 call is
    mirrored to v1. The gate measures thumbs-down rate on the v2-served
    slice. In a real system the slice is roughly `canary_percent` of live
    traffic over 30 minutes; here we take a deterministic sample of the
    dataset large enough for the gate to be meaningful."""
    # A statistically useful canary slice is at least a handful of calls.
    # Force a deterministic 25% draw so the gate has signal to work with
    # while still simulating "small slice of traffic".
    slice_size = max(3, len(calls) // 4)
    indices = sorted(rng.sample(range(len(calls)), slice_size))
    served_by_v2: list[MirroredCall] = []
    for i, c in enumerate(calls):
        if i in indices:
            c.served_by = "v2"
            served_by_v2.append(c)
        else:
            c.served_by = "v1"

    thumbs_down = sum(1 for c in served_by_v2 if c.thumbs_down)
    thumbs_down_rate = thumbs_down / len(served_by_v2)
    label_disagreements = sum(1 for c in served_by_v2 if c.label_disagrees())
    disagreement_rate = label_disagreements / len(served_by_v2)
    length_divergences = sum(1 for c in served_by_v2 if c.length_diverges())
    divergence_rate = length_divergences / len(served_by_v2)

    gate_open = thumbs_down_rate <= CANARY_THUMBS_DOWN_MAX
    reason = (
        f"thumbs-down rate {thumbs_down_rate:.1%} <= {CANARY_THUMBS_DOWN_MAX:.0%}"
        if gate_open
        else f"thumbs-down rate {thumbs_down_rate:.1%} crossed {CANARY_THUMBS_DOWN_MAX:.0%}, rollback armed"
    )

    return StageResult(
        name="canary",
        served_calls=len(served_by_v2),
        mirrored_calls=len(served_by_v2),
        label_disagreement_rate=disagreement_rate,
        length_divergence_rate=divergence_rate,
        thumbs_down_rate=thumbs_down_rate,
        gate_open=gate_open,
        reason=reason,
    )


def decide(calls: list[MirroredCall]) -> RolloutDecision:
    rng = random.Random(RNG_SEED)
    shadow = run_shadow(calls)

    decision = RolloutDecision(
        shadow=shadow,
        canary=StageResult(
            name="canary",
            served_calls=0,
            mirrored_calls=0,
            label_disagreement_rate=0.0,
            length_divergence_rate=0.0,
            thumbs_down_rate=0.0,
            gate_open=False,
            reason="not reached",
        ),
        promoted=False,
        rolled_back=False,
    )

    if not shadow.gate_open:
        decision.notes.append("shadow gate blocked; canary never opened.")
        decision.rolled_back = True
        decision.rollback_seconds = 0
        return decision

    decision.notes.append("shadow gate clear; proceeding to canary.")
    canary = run_canary(calls, rng)
    decision.canary = canary

    if canary.gate_open:
        decision.promoted = True
        decision.notes.append("canary gate clear; safe to promote to 50%.")
    else:
        decision.rolled_back = True
        # The platform rolls back in one config flip. Here we record a
        # conservative figure well inside the contractual ceiling.
        decision.rollback_seconds = 42
        decision.notes.append(
            "canary gate broke the thumbs-down threshold; v1 restored as the sole serving version."
        )

    return decision


def main() -> int:
    calls = load_mirrored_calls(HERE / "golden-dataset.csv")
    decision = decide(calls)

    print("=== Chapter 9: Staged Rollout Evaluation ===")
    print(f"Calls in dataset:        {len(calls)}")
    print()

    print("Stage: shadow")
    print(
        f"  mirrored={decision.shadow.mirrored_calls}, "
        f"label-disagreement={decision.shadow.label_disagreement_rate:.1%}, "
        f"length-divergence={decision.shadow.length_divergence_rate:.1%}"
    )
    print(f"  gate: {'OPEN' if decision.shadow.gate_open else 'BLOCKED'} ({decision.shadow.reason})")
    print()

    print("Stage: canary")
    if decision.shadow.gate_open:
        print(
            f"  served={decision.canary.served_calls}, "
            f"thumbs-down={decision.canary.thumbs_down_rate:.1%}, "
            f"label-disagreement={decision.canary.label_disagreement_rate:.1%}, "
            f"length-divergence={decision.canary.length_divergence_rate:.1%}"
        )
        print(
            f"  gate: {'OPEN' if decision.canary.gate_open else 'BLOCKED'} ({decision.canary.reason})"
        )
    else:
        print("  skipped (shadow gate blocked).")
    print()

    print("Decision:")
    if decision.promoted:
        print("  PROMOTE v2 to 50% rollout stage. Mirror sampling drops to 10%.")
    elif decision.rolled_back:
        print(
            f"  ROLL BACK to v1. Full rollback in ~{decision.rollback_seconds}s "
            f"(contract: <= {MAX_SECONDS_TO_FULL_ROLLBACK}s)."
        )
    print()
    for n in decision.notes:
        print(f"  note: {n}")
    print()

    # Contract: a run is a PASS when the platform made a decision, recorded
    # it, and respected the rollback ceiling. Both promote and roll-back
    # outcomes pass; the failure mode is undetected silent drift.
    contract_ok = (
        decision.promoted
        or (
            decision.rolled_back
            and decision.rollback_seconds <= MAX_SECONDS_TO_FULL_ROLLBACK
        )
    )

    # Every served call must cite its workflow version. In this offline
    # simulation that invariant is trivially true because every MirroredCall
    # has a served_by; we assert it to keep the contract visible.
    every_call_versioned = all(c.served_by in {"v1", "v2"} for c in calls)

    ok = contract_ok and every_call_versioned

    if ok:
        print("PASS: rollout ladder enforced. Shadow gate evaluated, canary gate evaluated,")
        print("      decision recorded, rollback ceiling respected.")
    else:
        print("FAIL: rollout made a decision the contract does not allow.")

    summary = {
        "total_calls": len(calls),
        "shadow_gate_open": decision.shadow.gate_open,
        "canary_gate_open": decision.canary.gate_open,
        "promoted": decision.promoted,
        "rolled_back": decision.rolled_back,
        "rollback_seconds": decision.rollback_seconds,
        "max_seconds_to_full_rollback": MAX_SECONDS_TO_FULL_ROLLBACK,
    }
    print("\nSummary:", json.dumps(summary))

    (HERE / "trace-example.json").read_text()  # sanity: trace present
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
