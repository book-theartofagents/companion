"""
Chapter 9 anti-pattern: the unversioned deploy.

Three composites from the book:
    1. `git pull && systemctl restart` as the release primitive.
    2. The notebook-to-prod promotion: prototype ships straight to live.
    3. The silent model update: alias moves, behaviour changes, nobody logs it.

Runs offline. Shows what happens when agent behaviour is not a versioned
artefact: "last Tuesday's behaviour" is not reproducible because the thing
that produced it no longer exists anywhere.

Usage:
    python anti-pattern-demo.py
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).parent


@dataclass
class UnversionedDeploy:
    """A single deploy that overwrote the previous behaviour in place.
    No snapshot, no diff, no way to restore. Just a timestamp and a regret."""

    at: dt.datetime
    who: str
    change: str  # what the commit message said
    actually_changed: str  # what the team discovered later
    rollback_possible: bool = False


# Six months of deploys to the same agent. Each one overwrites the last.
# The deploy pipeline has no concept of "agent version". It only knows
# "files on disk" and "restart".
HISTORY = [
    UnversionedDeploy(
        at=dt.datetime(2025, 11, 3, 14, 12),
        who="alice",
        change="initial release",
        actually_changed="baseline behaviour established, nobody captured it",
    ),
    UnversionedDeploy(
        at=dt.datetime(2025, 12, 9, 17, 40),
        who="bob",
        change="tweak prompt to be more concise",
        actually_changed="removed tone anchor sentence; answers got curt",
    ),
    UnversionedDeploy(
        at=dt.datetime(2026, 1, 15, 10, 3),
        who="alice",
        change="update tool schema to match new billing API",
        actually_changed="schema now rejects the three most common replies",
    ),
    UnversionedDeploy(
        at=dt.datetime(2026, 2, 2, 16, 55),
        who="carol",
        change="bump model alias",
        actually_changed="provider pushed a silent snapshot refresh; classifications shifted",
    ),
    UnversionedDeploy(
        at=dt.datetime(2026, 3, 11, 9, 18),
        who="bob",
        change="fix weird edge case",
        actually_changed="undid the December tweak; nobody noticed because the prompt file is 4000 words",
    ),
    UnversionedDeploy(
        at=dt.datetime(2026, 4, 14, 16, 2),
        who="dan",
        change="notebook promoted to prod",
        actually_changed="shipped the prototype behind the same deploy hook; zero canary, zero shadow",
    ),
]


@dataclass
class IncidentTicket:
    opened_at: dt.datetime
    complaint: str
    investigation_notes: list[str] = field(default_factory=list)
    resolved: bool = False


def investigate(ticket: IncidentTicket) -> IncidentTicket:
    """What the on-call engineer actually does when a customer says 'the
    agent felt different on Thursday afternoon'. No snapshots. No diffs.
    No way to replay last Tuesday's behaviour. Archaeology against commit
    logs and deploy timestamps, bounded by memory."""
    ticket.investigation_notes.append(
        "Day 1: check git log on the prompt file. Six commits in the last month. "
        "Each message says 'tweak'. No scenario ids, no version tag."
    )
    ticket.investigation_notes.append(
        "Day 2: ask team which model was live on Thursday. Three different answers. "
        "Alias points to latest snapshot, provider release notes mention a refresh."
    )
    ticket.investigation_notes.append(
        "Day 3: try to reproduce with the prompt from last week's commit. "
        "Tool schema has moved on, handler rejects the old prompt's shape."
    )
    ticket.investigation_notes.append(
        "Day 4: bisect by reverting suspected changes one at a time. "
        "Ship each revert to production because there is no staging. Wait a day for users to confirm."
    )
    ticket.investigation_notes.append(
        "Day 5: discover the December tone-anchor sentence was undone in March. "
        "Nobody remembers why."
    )
    ticket.resolved = False  # resolved in the sense of 'we stopped looking'
    return ticket


def restart_agent() -> str:
    """The release primitive. Not a version. Not an artefact. A side effect."""
    return "git pull && systemctl restart agent  # finished in 8s, no gate, no shadow, no mirror"


def main() -> None:
    print("=== Chapter 9: Anti-Pattern (Unversioned Deploy) ===")
    print()
    print("Release primitive:")
    print(f"  {restart_agent()}")
    print()

    print(f"Deploy history: {len(HISTORY)} changes, 0 versions recorded.")
    for d in HISTORY:
        print(
            f"  {d.at:%Y-%m-%d %H:%M}  {d.who:>6}  \"{d.change}\""
        )
        print(f"         reality: {d.actually_changed}")
    print()

    ticket = IncidentTicket(
        opened_at=dt.datetime(2026, 4, 17, 9, 30),
        complaint="Agent felt different on Thursday afternoon; answers curt, tone off.",
    )
    ticket = investigate(ticket)

    print("Incident investigation:")
    print(f"  opened: {ticket.opened_at:%Y-%m-%d %H:%M}")
    print(f"  complaint: {ticket.complaint}")
    for note in ticket.investigation_notes:
        print(f"    - {note}")
    print(f"  resolved: {ticket.resolved}")
    print()

    print("Three failures compound in one deploy pipeline:")
    print("  1. No agent version. Prompt, tools, model alias all overwrite in place.")
    print("  2. No shadow or canary. Every change is 100% full rollout the instant it ships.")
    print("  3. No rollback target. 'Roll back' means reverse the git commit and redeploy, hope no schema has drifted.")
    print()
    print("Compare run-eval.py:")
    print("  - v1 retained as rollback target for the lifetime of v2.")
    print("  - Shadow mirrors every call before a single user sees v2.")
    print("  - Canary serves 10% and watches thumbs-down for 30 minutes.")
    print("  - Rollback is a config flip, measured in seconds, not deploys.")
    print()
    print("Field note from the book: four days to diagnose vs forty minutes.")
    print("The difference is versioning. Everything else follows.")


if __name__ == "__main__":
    main()
