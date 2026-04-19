"""
Chapter 10 anti-pattern: the demo agent on flat terrain.

Three composites from the book:
    1. The demo agent: hardcoded token, full read access, tokens that never expire.
    2. The cross-tenant leak: tenant id as metadata filter in application code.
    3. The audit surprise: logs rotate before anyone asks for a replay.

Runs offline. The code here is intentionally short. That is the point. The
working-on-the-laptop agent is small because every non-negotiable piece of
terrain was skipped.

Usage:
    python anti-pattern-demo.py
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).parent


# The demo agent's identity. A service-account key, committed to .env,
# shared across the team, full read access to every tenant's documents.
# Nobody revoked it when the original author left.
HARDCODED_SERVICE_TOKEN = {
    "type": "service_account",
    "scopes": ["*"],
    "tenant": "*",
    "expires_at": None,  # never
}


# The entire "corpus". One dict, no tenant separation, no classification,
# PII sitting in plain text alongside public docs.
CORPUS = {
    "doc_public_faq": {
        "tenant": "t_orion",
        "content": "FAQ. Rate limits: 1000/min. Support hours 09:00-17:00.",
    },
    "doc_internal_policy": {
        "tenant": "t_orion",
        "content": "Change-management policy v3.2. Two reviewers on prod deploys.",
    },
    "doc_confidential_plan": {
        "tenant": "t_orion",
        "content": "Q3 roadmap: BYOK, auditor export.",
    },
    "doc_neighbour_contract": {
        "tenant": "t_pallas",
        "content": "MSA with Pallas Industries, signed by T. Chen 2025-11-01.",
    },
    "doc_hr_profile": {
        "tenant": "t_orion",
        "content": (
            "Profile for Maria Fernandez. Contact: maria.f@example.com, "
            "+31 6 1234 5678. National id 123-45-6789. Last review March 2026."
        ),
    },
}


@dataclass
class DemoResult:
    case_id: str
    user_id: str
    user_tenant: str
    doc_id: str
    doc_tenant: str
    allowed: bool
    body: str
    pii_in_output: bool
    audit_written: bool
    problems: list[str] = field(default_factory=list)


def demo_agent(user_id: str, user_tenant: str, doc_id: str, case_id: str) -> DemoResult:
    """The demo agent. Takes any user, any doc id, returns the content.
    The filter below is what the original author wrote on the laptop. It
    used to include a tenant check. A refactor last sprint moved the check
    into a helper function; the helper is called in one of the two call
    sites. This is that other call site.
    """
    problems: list[str] = []

    # Failure 1: service account for a user-scoped request. The call does
    # not carry the user's permissions to the storage layer.
    if HARDCODED_SERVICE_TOKEN["type"] == "service_account":
        problems.append(
            "service-account-for-user-data: the agent authenticates as a service, "
            "not as the calling user; the storage layer sees service permissions only."
        )

    # Failure 2: no classification check. No scope check. Anyone who reaches
    # this handler gets to read anything that is not explicitly walled off.

    # Failure 3: tenant filter forgotten at this call site. The refactor put
    # the check in a helper; the helper is not called here. The retriever
    # returns the document regardless of whose tenant it belongs to.
    doc = CORPUS.get(doc_id)
    if doc is None:
        return DemoResult(
            case_id=case_id,
            user_id=user_id,
            user_tenant=user_tenant,
            doc_id=doc_id,
            doc_tenant="?",
            allowed=False,
            body="",
            pii_in_output=False,
            audit_written=False,
            problems=problems + ["doc not found"],
        )

    if doc["tenant"] != user_tenant:
        problems.append(
            "cross-tenant leak: document belongs to another tenant; no storage-layer RLS stopped it."
        )

    # Failure 4: raw content returned, no PII redaction, no review.
    body = doc["content"]
    pii_in_output = any(
        marker in body for marker in ("@", "123-45-", "+31 6")
    )

    # Failure 5: no audit record. The incident review three months from
    # now will find nothing to reconstruct.
    audit_written = False

    return DemoResult(
        case_id=case_id,
        user_id=user_id,
        user_tenant=user_tenant,
        doc_id=doc_id,
        doc_tenant=doc["tenant"],
        allowed=True,
        body=body,
        pii_in_output=pii_in_output,
        audit_written=audit_written,
        problems=problems,
    )


def main() -> None:
    with (HERE / "golden-dataset.csv").open() as f:
        rows = list(csv.DictReader(f))

    results: list[DemoResult] = []
    for r in rows:
        results.append(
            demo_agent(
                user_id=r["user_id"],
                user_tenant=r["tenant_id"],
                doc_id=r["doc_id"],
                case_id=r["case_id"],
            )
        )

    allowed = sum(1 for r in results if r.allowed)
    pii_leaks = sum(1 for r in results if r.pii_in_output)
    cross_tenant = sum(
        1 for r in results if r.allowed and r.user_tenant != r.doc_tenant and r.doc_tenant != "?"
    )
    audit_written = sum(1 for r in results if r.audit_written)

    print("=== Chapter 10: Anti-Pattern (Demo Agent on Flat Terrain) ===")
    print(f"Cases:               {len(results)}")
    print(f"Allowed:             {allowed}  (every request that found a doc got content back)")
    print(f"Cross-tenant reads:  {cross_tenant}")
    print(f"Responses with PII:  {pii_leaks}")
    print(f"Audit records:       {audit_written}  (should be {len(results)})")
    print()

    for r in results:
        marker = "LEAK" if r.user_tenant != r.doc_tenant and r.doc_tenant not in {"?", ""} else "SERVE"
        print(
            f"  [{marker}] {r.case_id}: user={r.user_id}@{r.user_tenant} "
            f"doc={r.doc_id}@{r.doc_tenant} "
            f"pii={'y' if r.pii_in_output else 'n'} audit={'y' if r.audit_written else 'n'}"
        )

    print()
    print("Five failures in one file:")
    print("  1. Hardcoded service token; user permissions never reach the storage layer.")
    print("  2. Tenant filter forgotten at a second call site; RLS was never the contract.")
    print("  3. No classification; confidential and public sit in the same dict.")
    print("  4. No PII redaction; names, emails, phone numbers, national ids all shipped.")
    print("  5. No audit write; the question 'what did the agent do on 17 March?' has no answer.")
    print()
    print("Compare run-eval.py:")
    print("  - Token: scoped, delegated, TTL checked before every retrieval.")
    print("  - Tenant: row-level security at the storage boundary, not application metadata.")
    print("  - Classification: scope map enforces clearance before content is loaded.")
    print("  - PII: detectors run on every output; pii.read is a separate scope.")
    print("  - Audit: append-only log written before the response returns.")
    print()
    print("Field note from the book: ten days of prototype, six weeks of terrain.")
    print("That six weeks was not wasted effort. It was the work the prototype skipped.")


if __name__ == "__main__":
    main()
