# Spec: Enterprise terrain agent with auth, audit, RLS, and PII redaction

Paired with Chapter 10, "Terrain". Demonstrates the non-negotiables a production agent has to satisfy before anyone lets it near real data: authentication, data governance, auditability, and PII handling. LlamaIndex is the exemplar in the chapter; the pattern here mirrors the retrieval-as-a-tool model with a policy envelope around every call.

## Intent

Before retrieving a document, confirm the calling user has the scope for it and the document's classification matches their role. Write an audit record before the response returns. Redact PII from every output unless the caller holds a `pii.read` scope. Refuse on missing scope with a structured response the caller can trust.

## The four terrain pieces

| Terrain | Realised in this chapter |
|---|---|
| Authentication | Caller presents a scoped token: user id, tenant, scopes, expiry. Tokens near expiry are rejected. |
| Data governance | Tenant isolation and document classification checked against the caller's role. Row-level security, not application-level filtering. |
| Compliance | PII detected and redacted in the output path; classifications above the caller's clearance are refused. |
| Audit | Every retrieval and every response writes a trace before the response returns. The trace names the user, tenant, document id, classification, decision, and reasoning. |

## Invariants

- No document is retrieved without a scope check. The check happens before the content is read, not after.
- No response leaves the agent without an audit record written first. Order matters.
- No PII appears in a response to a caller without `pii.read`. Names, emails, phone numbers, national ids, account numbers, all redacted.
- A refusal is a structured object. Not prose. The caller can decide whether to escalate or surface the refusal to the user.
- Every decision is reproducible. Given the trace, a compliance officer can explain why the agent did what it did three months later.

## Success criteria

- Scope-check coverage: 100%. Every retrieval branches on a scope.
- Audit coverage: 100%. No response path bypasses the audit writer.
- PII leakage rate: 0. On a seeded corpus with known PII, redaction removes every marked instance.
- Refusal rate on scoped dataset: measured, recorded, reasoned.
- RLS enforced at the data layer, not the application layer. Retrieval fails closed when the calling user lacks the row-level grant.

## Failure modes covered

- The demo agent: hardcoded token, full access, no session lifecycle (Ch. 10).
- The cross-tenant leak: tenant id as application-level filter, forgotten in a refactor (Ch. 10).
- The audit surprise: logs rotate before the auditor asks the question (Ch. 10).
- Silent wrong answer over restricted data (Ch. 11).

## Test dataset

See `golden-dataset.csv`. Each row describes a user, a document, and the expected decision. Rows exercise every combination of tenant mismatch, classification mismatch, missing scope, expired token, and PII in payload.
