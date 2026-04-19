"""
Chapter 7 anti-pattern: the brittle plan.

Three failure shapes from the book:
    1. The compounding retry: a while loop that hammers a degraded service.
    2. The rigid pipeline: fixed steps, no fallback, every failure fatal.
    3. The single-process agent: in-memory state, lost on restart.

Runs offline. Simulates the kernel patch that rebooted the VM in the book's
field note and takes every in-flight run with it.

Usage:
    python anti-pattern-demo.py
"""

from __future__ import annotations

import csv
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).parent
random.seed(42)


# -- Anti-pattern #1: the compounding retry --------------------------------
class DegradedService:
    """Each call that reaches it makes the service slightly worse.
    A retry-blind loop does not account for this. The service is firmly
    degraded for the duration of the demo so the pattern is visible."""

    def __init__(self) -> None:
        self.load = 0
        self.base_fail_rate = 0.92

    def call(self) -> str:
        self.load += 1
        fail_rate = min(0.995, self.base_fail_rate + 0.002 * self.load)
        if random.random() < fail_rate:
            raise TimeoutError(f"service degraded (load={self.load})")
        return "ok"


def compounding_retry(service: DegradedService, max_attempts: int = 200) -> dict:
    """No backoff, no jitter, no circuit breaker. The book's example of
    a retry pattern that turns a bad minute into an outage."""
    attempts = 0
    errors = 0
    for _ in range(max_attempts):
        attempts += 1
        try:
            service.call()
            return {"attempts": attempts, "errors": errors, "status": "eventually_ok"}
        except TimeoutError:
            errors += 1
            # No sleep, no backoff, no jitter. Hammer.
            continue
    return {"attempts": attempts, "errors": errors, "status": "gave_up"}


# -- Anti-pattern #2: the rigid pipeline -----------------------------------
@dataclass
class RigidPipelineResult:
    completed_steps: list[str]
    failed_step: str | None
    final_status: str


def rigid_pipeline(model_a_degraded: bool, tool_b_down: bool) -> RigidPipelineResult:
    """Call model A, then tool B, then model C, then tool D. No fallback,
    no conditional routing, no retry policy that knows transient from
    permanent. If anything fails, everything fails."""
    completed: list[str] = []

    # Step A. Degraded still returns a response, just a weak one. The
    # pipeline has no detector, so it passes on.
    if model_a_degraded:
        completed.append("model_a (weak output, not detected)")
    else:
        completed.append("model_a")

    # Step B. Down means fatal. No fallback exists.
    if tool_b_down:
        return RigidPipelineResult(completed_steps=completed, failed_step="tool_b", final_status="failed")
    completed.append("tool_b")

    completed.append("model_c")
    completed.append("tool_d")
    return RigidPipelineResult(completed_steps=completed, failed_step=None, final_status="completed")


# -- Anti-pattern #3: the single-process agent -----------------------------
@dataclass
class InMemoryAgent:
    """The design from the book's field note. One Python process on a VM,
    conversation state in memory, long-running queries in flight. A
    kernel-patch reboot is a data loss event."""

    conversation: list[dict] = field(default_factory=list)
    in_flight: list[dict] = field(default_factory=list)

    def start(self, run_id: str, question: str) -> None:
        self.in_flight.append({"run_id": run_id, "question": question, "state": "planning"})

    def advance(self, run_id: str, state: str) -> None:
        for run in self.in_flight:
            if run["run_id"] == run_id:
                run["state"] = state

    def vm_reboot(self) -> list[dict]:
        """The process is gone. So is the state."""
        lost = list(self.in_flight)
        self.in_flight = []
        self.conversation = []
        return lost


def main() -> None:
    print("=== Chapter 7: Anti-Pattern Demo ===")
    print()

    # 1. Compounding retry. Load grows with attempts. The code is simple.
    # The happy path works. Production is not the happy path.
    print("-- 1. The compounding retry --")
    service = DegradedService()
    result = compounding_retry(service)
    print(f"Service final load:  {service.load}")
    print(f"Attempts taken:      {result['attempts']}")
    print(f"Errors on the way:   {result['errors']}")
    print(f"Outcome:             {result['status']}")
    print("Same code at scale: one stuck workflow, thousands of requests per hour,")
    print("the upstream service rate-limits, which fails other workflows, which retry.")
    print()

    # 2. Rigid pipeline. No fallback. Tool B is down for a deploy window.
    # Every request in that window fails visibly.
    print("-- 2. The rigid pipeline --")
    happy = rigid_pipeline(model_a_degraded=False, tool_b_down=False)
    degraded = rigid_pipeline(model_a_degraded=True, tool_b_down=False)
    fatal = rigid_pipeline(model_a_degraded=False, tool_b_down=True)
    print(f"Happy path:       status={happy.final_status}, steps={len(happy.completed_steps)}")
    print(f"Model A degraded: status={degraded.final_status}, weak output propagates silently.")
    print(f"Tool B down:      status={fatal.final_status}, no fallback path defined.")
    print("Adding more try/except makes the pipeline longer without making it more adaptive.")
    print()

    # 3. Single-process agent. The book's field note. Seventy-three runs lost.
    print("-- 3. The single-process agent --")
    agent = InMemoryAgent()
    for i in range(73):
        agent.start(f"run_{i:03d}", f"complex query {i}")
        agent.advance(f"run_{i:03d}", state="retrieving")
    in_flight_before = len(agent.in_flight)
    print(f"In-flight before reboot: {in_flight_before}")
    lost = agent.vm_reboot()
    print(f"Lost on reboot:          {len(lost)}")
    print(f"In-flight after reboot:  {len(agent.in_flight)}")
    print(f"Users saw:               long-running queries disappear with no error.")
    print(f"Process saw:             nothing. Process that would have raised the error is gone.")
    print()

    # Compare against the durable version in run-eval.py.
    print("-- Compare --")
    with (HERE / "golden-dataset.csv").open() as f:
        rows = list(csv.DictReader(f))
    crash_rows = [r for r in rows if r["failure_kind"] == "worker_crash"]
    print("Durable (run-eval.py):")
    print(f"  {len(rows)} scenarios, {len(crash_rows)} worker-crash cases, all recover via replay.")
    print("  Retries bounded by policy. Non-retryable errors short-circuit.")
    print("  Human approval via signal, worker free during the wait.")
    print()
    print("Brittle (this demo):")
    print("  Compounding retry hammers degraded service until it gives up.")
    print("  Rigid pipeline fails whole when any step fails.")
    print("  In-memory agent loses every in-flight run on VM reboot.")
    print()
    print("Fix: the workflow is a durable program. Side effects are activities.")
    print("     Retries and timeouts are declared. Humans wait on signals, not polls.")


if __name__ == "__main__":
    main()
    sys.exit(0)
