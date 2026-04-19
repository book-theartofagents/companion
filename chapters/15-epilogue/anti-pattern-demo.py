"""
Chapter 15 anti-pattern: victory conditions nobody measures.

The book has been read. The slides have been copied into the team wiki.
Someone has labelled the roadmap with the four starter items. Nothing is
measured. The checklist is decoration.

Three shapes:
    1. Claims without measurements: every project says "we have a spec."
    2. Victory declared on day one: readiness assumed at launch, never audited.
    3. Scorecard written once, never re-run: the number is from Q2 last year.

Runs offline. Contrasts the decorative checklist with the real scorecard in
run-eval.py.

Usage:
    python anti-pattern-demo.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).parent


@dataclass
class DecorativeClaim:
    chapter: str
    team_says: str
    evidence: str | None = None
    last_audit_days_ago: int = 999
    tags: list[str] = field(default_factory=list)


# The checklist, decorated. Every team says yes. No one measured.
CLAIMS = [
    DecorativeClaim("01-laying-plans", "we have a spec", None, 999, ["wiki-copied"]),
    DecorativeClaim("02-waging-war", "we track tokens", None, 365, ["in a dashboard no one opens"]),
    DecorativeClaim("03-attack-by-stratagem", "we use gen-judge", None, 500, ["once, in a demo"]),
    DecorativeClaim("04-tactical-dispositions", "schemas are the defence", None, 240, ["in a slide"]),
    DecorativeClaim("05-energy", "we use MCP", None, 180, ["in the roadmap"]),
    DecorativeClaim("06-weak-points-and-strong", "we tool well", None, 365, ["nobody reviewed them"]),
    DecorativeClaim("07-manoeuvring", "we have traces", None, 365, ["traces exist, not reviewed"]),
    DecorativeClaim("08-variation-in-tactics", "we branch correctly", None, 300, []),
    DecorativeClaim("09-army-on-the-march", "multi-agent is planned", None, 999, ["never started"]),
    DecorativeClaim("10-terrain", "enterprise handled", None, 400, []),
    DecorativeClaim("11-nine-situations", "failures named", None, 500, []),
    DecorativeClaim("12-attack-by-fire", "ai is restrained", None, 400, []),
    DecorativeClaim("13-use-of-spies", "feedback loop exists", None, 999, ["meeting on Mondays"]),
]


def audit_claim(claim: DecorativeClaim) -> bool:
    """A claim counts only when evidence exists and the audit is recent."""
    if claim.evidence is None:
        return False
    return claim.last_audit_days_ago <= 90


def main() -> None:
    print("=== Chapter 15: Anti-Pattern (Decorative Checklist) ===")
    print(f"Chapters claiming readiness: {len(CLAIMS)}")
    print()

    failed = 0
    for c in CLAIMS:
        ok = audit_claim(c)
        tag = "OK" if ok else "FAIL"
        tags = ", ".join(c.tags) if c.tags else "-"
        print(
            f"  [{tag}] {c.chapter:<28s} claim=\"{c.team_says}\"  "
            f"evidence={c.evidence or 'none'}  "
            f"last_audit={c.last_audit_days_ago}d ago  "
            f"tags=[{tags}]"
        )
        if not ok:
            failed += 1

    total = len(CLAIMS)
    print()
    print(f"Claims that pass the audit: {total - failed}/{total}")
    print(f"Claims failing for lack of evidence or stale audit: {failed}/{total}")
    print()

    print("Three shapes (Ch. 15):")
    print("  1. Claims without measurements. Every team says yes, nobody can prove it.")
    print("  2. Victory declared on day one. The audit would have said no on day thirty.")
    print("  3. A scorecard that never re-runs. The number on the slide is from last year.")
    print()
    print("The fix is procedural, not cultural. run-eval.py runs the real scorecard:")
    print("  - reads the files on disk,")
    print("  - counts the four starter items per chapter,")
    print("  - prints a number that moves when the work moves.")
    print()
    print("'Victorious warriors win first and then go to war.' The temple is the repo.")
    print("The calculations are the specs. The scorecard is the check that they were made.")


if __name__ == "__main__":
    main()
