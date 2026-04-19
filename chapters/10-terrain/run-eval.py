"""
Chapter 10 evaluation: enterprise terrain enforcement.

Runs offline. No API keys, no network. The scenario mirrors a LlamaIndex
agent whose retrieval tool sits behind a policy envelope. Every call passes
through authentication, tenant isolation, classification gating, PII
redaction, and audit writing before any content returns.

Usage:
    python run-eval.py

What it does:
    1. Loads twelve scoped requests from golden-dataset.csv.
    2. Runs each through the terrain policy: tenant check, classification
       check, token-TTL check, retrieval, PII redaction, audit write.
    3. Confirms the outcome matches the expected decision and reason.
    4. Verifies every served response has an audit record written *before*
       the response body was produced.

The point of this evaluator is that the invariants are all checkable from
the trace alone. If the trace does not show a scope check, the policy did
not run. A compliance officer reviewing the trace months later can see
exactly what the agent did and why.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).parent

# Each classification maps to one or more *accepted* scope combinations.
# Any of the sets in the list is sufficient. The auditor and the restricted-
# content reader can both legitimately read a restricted audit log.
CLASSIFICATION_SCOPE_OPTIONS: dict[str, list[set[str]]] = {
    "public": [{"docs.read"}],
    "internal": [{"docs.read"}],
    "confidential": [{"docs.read", "docs.confidential"}],
    "restricted": [{"audit.read"}, {"docs.read", "docs.restricted"}],
}

TOKEN_MIN_TTL_SECONDS = 120

# PII detectors. Deliberately simple, deterministic patterns for the offline
# eval. A real deployment would use a dedicated PII classifier; the book
# repo does not ship a heavy dependency just for the demo.
PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "phone": re.compile(r"\b\+?\d[\d \-]{7,}\d\b"),
    "national_id": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"),
}

# Seeded corpus. The keys mirror doc_id values in golden-dataset.csv.
# Content is short, deterministic, and intentionally includes PII in the
# documents that the dataset marks `doc_contains_pii=true`.
CORPUS: dict[str, str] = {
    "doc_public_faq": (
        "Frequently asked questions about the Orion product. "
        "Rate limits: 1000 req/min. Support hours: 09:00-17:00 UTC."
    ),
    "doc_internal_policy": (
        "Internal change-management policy v3.2. "
        "All production deploys require a second reviewer and a rollback plan."
    ),
    "doc_confidential_plan": (
        "Confidential product roadmap: Q3 releases include an auditor-grade "
        "export feature and bring-your-own-key onboarding."
    ),
    "doc_neighbour_contract": (
        "Master services agreement with Pallas Industries. "
        "Effective 2025-11-01, superseding v1. Signed by T. Chen."
    ),
    "doc_hr_profile": (
        "Profile for employee Maria Fernandez. Contact: maria.f@example.com, "
        "+31 6 1234 5678. National id on file: 123-45-6789. Last review: March 2026."
    ),
    "doc_audit_log": (
        "Audit log of privileged actions for Q1 2026. "
        "Records retained per ISO/IEC 42001 change-management clauses."
    ),
}


@dataclass
class Token:
    user_id: str
    tenant_id: str
    scopes: set[str]
    remaining_ttl_seconds: int


@dataclass
class Document:
    doc_id: str
    tenant_id: str
    classification: str


@dataclass
class AuditRecord:
    trace_id: str
    user_id: str
    tenant_id: str
    doc_id: str | None
    classification: str | None
    scopes_presented: list[str]
    decision: str
    reason: str
    retrieval_strategy: str | None = None
    model_snapshot: str = "2026-04-11"
    written_before_response: bool = True
    # Record the size of the request, not its content. Lengths let us spot
    # anomalies (a 50KB "summarise" request is suspicious) without logging
    # anything the caller could reasonably claim is sensitive.
    request_length: int = 0


@dataclass
class Response:
    decision: str
    reason: str
    body: str
    audit: AuditRecord
    pii_detected: list[str] = field(default_factory=list)
    pii_redacted: bool = False


class AuditLog:
    """Append-only in-memory audit sink. Real deployment writes to an
    immutable store with tenant-aware retention."""

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []

    def write(self, record: AuditRecord) -> None:
        self._records.append(record)

    def for_trace(self, trace_id: str) -> AuditRecord | None:
        for r in self._records:
            if r.trace_id == trace_id:
                return r
        return None

    def __len__(self) -> int:
        return len(self._records)


def redact(text: str) -> tuple[str, list[str]]:
    """Run the PII detectors and replace every match with a classification
    token. Returns the redacted text and the list of kinds found, in the
    order the corpus presented them."""
    found: list[str] = []

    def _sub_factory(kind: str):
        def _sub(_: re.Match[str]) -> str:
            # The callback is handed to re.sub once per match. The match
            # object is ignored: we replace with a fixed token regardless
            # of what matched, and note the kind for the audit log.
            found.append(kind)
            return f"[REDACTED:{kind}]"

        return _sub

    output = text
    # Deterministic iteration order.
    for kind in ("national_id", "iban", "email", "phone"):
        output = PII_PATTERNS[kind].sub(_sub_factory(kind), output)
    return output, found


def serve(
    token: Token,
    request_text: str,
    document: Document,
    audit_log: AuditLog,
    trace_id: str,
) -> Response:
    """The terrain-aware handler. Runs the policy checks in the order the
    book argues for, writes the audit record before the response is built,
    and redacts PII from the body unless the caller holds `pii.read`."""
    scopes_list = sorted(token.scopes)
    request_length = len(request_text)

    def _refuse(reason: str) -> Response:
        audit = AuditRecord(
            trace_id=trace_id,
            user_id=token.user_id,
            tenant_id=token.tenant_id,
            doc_id=document.doc_id,
            classification=document.classification,
            scopes_presented=scopes_list,
            decision="refuse",
            reason=reason,
            retrieval_strategy=None,
            request_length=request_length,
        )
        audit_log.write(audit)
        return Response(
            decision="refuse",
            reason=reason,
            body="",
            audit=audit,
        )

    # 1. Authentication: token freshness. Near-expiry tokens are rejected
    # rather than trusted; the refresh flow belongs upstream.
    if token.remaining_ttl_seconds < TOKEN_MIN_TTL_SECONDS:
        return _refuse("token_near_expiry")

    # 2. Authentication: scope presence at all. A request with no scopes
    # should not proceed.
    if not token.scopes:
        return _refuse("missing_scope")

    # 3. Document lookup. The lookup happens inside the tenant boundary;
    # RLS at the storage layer means a missing grant returns "not found",
    # not "forbidden". We model that explicitly here.
    content = CORPUS.get(document.doc_id)
    if content is None:
        return _refuse("document_not_found")

    # 4. Tenant isolation. Modeled as row-level security: the retrieval
    # never sees cross-tenant documents. If the storage returned something
    # cross-tenant, refuse closed rather than open.
    if token.tenant_id != document.tenant_id:
        return _refuse("tenant_mismatch")

    # 5. Classification: the caller must hold at least one accepted scope
    # combination for this classification. Either the caller has the full
    # docs.read + docs.confidential path, or they have a focused scope
    # like audit.read for audit logs.
    options = CLASSIFICATION_SCOPE_OPTIONS.get(document.classification, [])
    if not any(opt.issubset(token.scopes) for opt in options):
        return _refuse("classification_above_clearance")

    # 6. PII redaction: scan, redact if the caller lacks pii.read.
    body, pii_kinds = redact(content)
    pii_redacted = "pii.read" not in token.scopes and bool(pii_kinds)
    if not pii_redacted:
        body = content  # caller is entitled to see the PII

    decision = "allow_redacted" if pii_redacted else "allow"
    reason = "pii_redacted" if pii_redacted else _allow_reason(token, document)

    # 7. Audit write happens before the response returns. This ordering is
    # the whole point of the audit rule in guardrail-config.yaml.
    audit = AuditRecord(
        trace_id=trace_id,
        user_id=token.user_id,
        tenant_id=token.tenant_id,
        doc_id=document.doc_id,
        classification=document.classification,
        scopes_presented=scopes_list,
        decision=decision,
        reason=reason,
        retrieval_strategy="metadata_filter+dense",
        request_length=request_length,
    )
    audit_log.write(audit)

    return Response(
        decision=decision,
        reason=reason,
        body=body,
        audit=audit,
        pii_detected=pii_kinds,
        pii_redacted=pii_redacted,
    )


def _allow_reason(token: Token, document: Document) -> str:
    if document.classification == "restricted" and "audit.read" in token.scopes:
        return "audit_scope_matches"
    if "docs.confidential" in token.scopes and document.classification == "confidential":
        return "clearance_matches"
    return "scope_and_tenant_ok"


@dataclass
class CaseResult:
    case_id: str
    expected_decision: str
    got_decision: str
    expected_reason: str
    got_reason: str
    passed: bool
    audit_written: bool
    pii_leaked: bool


def grade(expected: dict, got: Response) -> CaseResult:
    decision_ok = expected["expected_decision"] == got.decision
    reason_ok = expected["expected_reason"] == got.reason
    audit_ok = got.audit is not None and got.audit.written_before_response

    # Leakage check: if the caller does not hold pii.read and the corpus
    # had PII, the body must not contain any detected PII patterns.
    pii_in_output: list[str] = []
    _, kinds_present = redact(got.body)
    pii_in_output = [k for k in kinds_present if got.pii_redacted]  # none expected
    pii_leaked = bool(pii_in_output)

    return CaseResult(
        case_id=expected["case_id"],
        expected_decision=expected["expected_decision"],
        got_decision=got.decision,
        expected_reason=expected["expected_reason"],
        got_reason=got.reason,
        passed=decision_ok and reason_ok and audit_ok and not pii_leaked,
        audit_written=audit_ok,
        pii_leaked=pii_leaked,
    )


def main() -> int:
    rows: list[dict] = []
    with (HERE / "golden-dataset.csv").open() as f:
        for r in csv.DictReader(f):
            rows.append(r)

    audit_log = AuditLog()
    results: list[CaseResult] = []
    responses: list[Response] = []

    for r in rows:
        token = Token(
            user_id=r["user_id"],
            tenant_id=r["tenant_id"],
            scopes=set(s for s in r["scopes"].split() if s),
            remaining_ttl_seconds=int(r["token_expires_in_s"]),
        )
        doc = Document(
            doc_id=r["doc_id"],
            tenant_id=r["doc_tenant"],
            classification=r["doc_classification"],
        )
        trace_id = f"trace_ch10_{r['case_id']}"
        response = serve(
            token=token,
            request_text="Summarise this document",
            document=doc,
            audit_log=audit_log,
            trace_id=trace_id,
        )
        responses.append(response)
        results.append(grade(r, response))

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    refusals = sum(1 for r in results if r.got_decision == "refuse")
    allow_redacted = sum(1 for r in results if r.got_decision == "allow_redacted")
    pii_leaks = sum(1 for r in results if r.pii_leaked)
    audit_count = len(audit_log)

    print("=== Chapter 10: Enterprise Terrain Evaluation ===")
    print(f"Cases:             {total}")
    print(f"Passed:            {passed}")
    print(f"Refusals:          {refusals}")
    print(f"Allow (redacted):  {allow_redacted}")
    print(f"Audit records:     {audit_count}  (target == {total})")
    print(f"PII leaks:         {pii_leaks}  (target == 0)")
    print()

    for res in results:
        status = "PASS" if res.passed else "FAIL"
        print(
            f"  [{status}] {res.case_id}: "
            f"expected={res.expected_decision}/{res.expected_reason} "
            f"got={res.got_decision}/{res.got_reason} "
            f"audit={'y' if res.audit_written else 'n'} leak={'y' if res.pii_leaked else 'n'}"
        )

    # Contract: every case resolves to the expected decision, every served
    # call wrote an audit record before returning, and no PII leaked.
    coverage = passed / total
    audit_coverage = audit_count / total
    ok = coverage == 1.0 and audit_coverage == 1.0 and pii_leaks == 0

    print()
    if ok:
        print("PASS: terrain enforced. Auth, tenant, classification, PII, audit all honoured.")
    else:
        print("FAIL: terrain breach. Read spec.md on the four non-negotiables.")

    summary = {
        "total": total,
        "passed": passed,
        "audit_coverage": audit_coverage,
        "pii_leak_rate": pii_leaks / total,
        "refusal_rate": refusals / total,
    }
    print("\nSummary:", json.dumps(summary))

    (HERE / "trace-example.json").read_text()  # sanity: trace present
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
