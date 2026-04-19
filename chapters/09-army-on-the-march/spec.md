# Spec: Versioned agent with staged rollout and shadow mode

Paired with Chapter 9, "The Army on the March". Demonstrates the deployment pattern from Dify: every behaviour-changing artefact is versioned, new versions go through shadow and canary stages before full rollout, and rollback is a config flip rather than a code deploy.

## Intent

Ship v2 of an agent without displacing v1. Route a small slice of live traffic to v2, replay the same inputs through v1 in shadow mode, compare the two outputs, promote v2 when the divergence stays inside a declared threshold, roll back automatically otherwise.

## Invariants

- Every behaviour-changing artefact is pinned to a dated version. Model ids, prompts, tool schemas, workflow ids. No aliases on the hot path.
- v2 traffic share starts at 10% and only grows after the rollout gate clears.
- Every v2 call is mirrored through v1 in shadow mode. Both outputs are stored with the same trace id.
- Rollback triggers are declared in config: disagreement rate, thumbs-down rate, error rate. No hand-written scripts.
- Rollback is atomic: one config change, all traffic back to v1, no code deploy.

## The staged rollout ladder

| Stage | Traffic to v2 | Gate to next stage |
|---|---|---|
| Shadow | 0% served, 100% mirrored | Shadow disagreement rate <= 15% over 200 calls |
| Canary | 10% served, 100% mirrored | Canary thumbs-down rate <= 8% over 30 minutes |
| Rollout | 50% served, sampled mirror | Canary gate holds for 24 hours |
| Full | 100% served, v1 retained as rollback target | Manual promote after a clean week |

## Success criteria

- Shadow divergence rate: measured, below 15% before canary starts.
- Canary disagreement rate: logged per call, trendlines visible, threshold enforced.
- Time from rollback trigger to 100% v1: under 60 seconds.
- Every trace cites the workflow version that produced it. No "unknown" entries.
- Rollback rehearsed before release, not during.

## Failure modes covered

- The unversioned agent: prompt tweaks overwrite each other in place (Ch. 9).
- The notebook-to-prod promotion: prototype ships without staging or rollback (Ch. 9).
- The silent model update: alias moves, behaviour changes, nobody notices (Ch. 9).
- Silent degradation: output quality shifts below the error-rate signal (Ch. 9, Ch. 11).

## Test dataset

See `golden-dataset.csv`. Each row is a triage request with the v1 label the team already trusts and a v2 label produced by the new workflow. The evaluator measures disagreement and decides whether the rollout gate opens.
