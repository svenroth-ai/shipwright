# Sub-iterate A — B-churn: stabilize SBOM cluster identity

- **Campaign:** 2026-06-05-track-triage-jsonl (sub-iterate A of A→E)
- **run_id:** `iterate-2026-06-05-sbom-cluster-stable-identity`
- **Type:** change (producer-side) · **Complexity:** small ·
  **Risk flags:** `touches_io_boundary` (triage.jsonl write-contract)
- **Branch:** `iterate/sbom-cluster-stable-id`
- **Anchor:** `expands_triage: trg-2fb7d3bc`

## Problem

`_cluster_dedup_key(signature, member_paths)` hashes **both** the undeclared-set
signature **and** the member list (a decision made under external-review OpenAI
#2/#3). Membership drifts run-to-run (uv.lock / license resolvability varies
between worktrees), so the same logical cluster gets a **fresh id every run** →
old item auto-dismisses + new emits → `chore(churn)` noise and a dismissed pile
that has grown to **161** items. Tracking that log as-is (sub-iterate C) would
bake the churn engine into permanent git history.

## Decision

Decouple cluster **identity** from cluster **content**:
`_cluster_dedup_key(signature, manifest_type)` hashes the **(signature,
manifest_type) pair only**. Membership lives in the body, not the id.

- Membership drift while ≥2 members keep the signature → **same id** (no churn).
- `manifest_type` folded into the hash so an npm cluster and a python cluster
  that share an undeclared-name signature do **not** collide (they need
  different install commands — AC-8).
- Last member of a signature resolves → bucket disappears → item auto-dismisses
  (correct, not churn). 2→1 shrink crosses the cluster→per-workspace boundary
  (legitimate dismiss + per-workspace re-emit) — unchanged.

**Supersedes** the membership-encoding behavior of
`proposed-sbom-triage-cluster-collapse.md` (its AC-9 "grows → old-dismiss +
new-emit").

## Acceptance criteria (sub-iterate)

- [x] **A-AC1.** `_cluster_dedup_key` is a function of `(signature,
      manifest_type)` only; identical across member sets, distinct across
      manifest types sharing a signature.
- [x] **A-AC2.** Membership grow ({a,c}→{a,c,d}) and shrink-within-range
      ({a,b,c}→{a,b}) keep the SAME open cluster id — `dismissed==0`,
      `appended==0`.
- [x] **A-AC3.** 2→1 shrink still crosses to per-workspace (existing behavior
      preserved).
- [x] **A-AC4.** Full compliance suite green (no downstream audit-detector / RTM
      regression keyed off the cluster prefix).

## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| `emit_undeclared_triage` writes cluster items with a signature-only dedup key | webui Triage-Inbox + RTM + audit detectors (ADR-052 source="sbom" resolve) | `.shipwright/triage.jsonl` lines |

The cluster-key **prefix** (`sbom:undeclared-cluster:`) is unchanged, so the
ADR-052 auto-resolve contract is unaffected; only the hash *input* narrows.

## Confidence Calibration

- **Boundaries touched:** the `.shipwright/triage.jsonl` write-contract via
  `emit_undeclared_triage` → `_cluster_dedup_key`. The triage event model
  (`append`/`status`) and the cluster-prefix contract are unchanged.
- **Empirical probes run:**
  1. *Red probe* — inverted `test_cluster_membership_grows_keeps_stable_id` +
     new shrink-within-range test failed against the membership-encoding code
     with `result={'appended':1,'dismissed':1,'clusters':1}` (proves the churn
     was real and the tests bind it).
  2. *Green probe* — after the change both stability tests pass; id is byte-equal
     across grow/shrink (`dedupKey == first_key`).
  3. *Collision probe* — `_cluster_dedup_key(("react","shared"),"npm") !=
     _cluster_dedup_key(("react","shared"),"python")` (manifest_type fold works).
  4. *Downstream probe* — full compliance suite **617 passed, 10 skipped**; no
     audit-detector / RTM / dashboard regression.
  5. *Body-staleness probe* — after grow to 3 members the open item's body still
     reads `Workspaces (2)` (append-only store never re-renders) — pinned as
     by-design.
- **Test Completeness Ledger:**

  | Behavior (introduced/changed) | Disposition | Evidence |
  |---|---|---|
  | dedup key = f(signature, manifest_type) only | `tested` | `test_cluster_dedup_key_independent_of_membership`, `test_cluster_dedup_key_shape_is_sha256_12` |
  | grow {a,c}→{a,c,d} keeps stable id | `tested` | `test_cluster_membership_grows_keeps_stable_id` |
  | shrink-in-range {a,b,c}→{a,b} keeps stable id | `tested` | `test_cluster_membership_shrinks_within_range_keeps_stable_id` |
  | 2→1 shrink crosses to per-workspace (preserved) | `tested` | `test_cluster_dismisses_then_reemits_when_membership_shrinks` |
  | npm vs python same signature stay distinct | `tested` | `test_npm_and_python_signatures_emit_separate_clusters` + unit test |
  | idempotent same-sig-same-members | `tested` | `test_cluster_idempotent_across_runs` |
  | auto-resolve when all members clean | `tested` | `test_cluster_auto_resolves_when_all_members_clean` |
  | body shows membership-at-first-emit (stale by-design) | `tested` | `test_cluster_membership_grows_keeps_stable_id` (asserts `Workspaces (2)`) |

  0 testable-but-untested behaviors. Faithful body **re-render** is *not* a
  behavior this diff introduces — it is explicitly deferred (see follow-up).
- **Confidence-pattern check:**
  - *Asymptote (depth):* the change is one hash-input narrowing + one call-site
    arg; the Red/Green probes bracket the exact behavior change; downstream
    suite confirms no second-order breakage. No deeper probe would move
    confidence.
  - *Coverage (breadth):* grow, shrink-in-range, shrink-to-boundary,
    cross-manifest, idempotent, auto-resolve, and body-staleness all covered.

## Deferred (tracked follow-up)

Faithful **body re-render** on membership change (workspace list + launch
payload) needs a triage-store `amend` event (overlay title/detail/launchPayload
in `read_all_items`) **plus** the WebUI consumer — a separable shared-contract +
cross-repo change, out of A's producer-only scope. Filed as a `kind:improvement`
triage item.
