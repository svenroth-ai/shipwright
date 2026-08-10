# Iterate Spec: branch feedback and lifecycle authority

- **Run ID:** `iterate-2026-08-09-p2-59-branch-feedback-authority`
- **Status:** implemented
- **Intent:** change
- **Complexity:** medium (escalated from the initial small estimate because the change composes a Stop hook, delivery, release workflow, shared triage state, and cross-plugin tests).
- **Spec impact:** NONE — this changes framework lifecycle authority, not a user-facing product requirement.

## Decision

Use one lifecycle-aware audit runner with three explicit authority scopes:

1. `branch_feedback` runs detection on the resolved branch tree and reports its findings locally only. It never calls the global backlog writer.
2. `merge` is called only after `deliver_pr.py` has returned `DELIVERED`. It obtains the PR's `mergeCommit` from GitHub, audits a detached worktree at that exact SHA, writes to the default tree's global backlog only after complete applicable coverage, and excludes Group E.
3. `release` runs after the seven release-owned documents were staged, committed, and `refresh_compliance_docs.py --verify-commit` succeeded. It audits the verified release commit and may converge every group including E.

Coverage has two separate states. `not_applicable` is a declared scope exclusion (only E in merge scope); it is recorded separately from `missing`, which means an expected group did not run, crashed, or the import gate failed. Only the first is compatible with complete coverage.

## Acceptance Criteria

- [x] AC1 — An iterate/Stop audit on a resolved branch or worktree presents Group E pending-release drift locally and never appends, refreshes, or dismisses the global compliance backlog.
- [x] AC2 — An iterate/Stop audit with a real non-E failure also remains locally visible and never changes the global compliance backlog.
- [x] AC3 — After `deliver_pr.py` reports `DELIVERED`, merge authority reads the delivered PR's exact `mergeCommit`, audits that commit rather than branch HEAD or local main, and updates Groups A-D/F-I only when coverage is complete.
- [x] AC4 — Merge coverage records E as `not_applicable` and is complete; a genuinely absent, crashed, unavailable, or wrong-commit expected group is `missing`, is incomplete, and leaves the backlog untouched.
- [x] AC5 — A verified release commit runs full A-I authority and may refresh or dismiss Group E as well as all other groups, after the existing refresh/stage/verify contract.
- [x] AC6 — The 5 → 13 → 5 Group-E branch-noise regression cannot mutate the global backlog; branch diagnostics remain visible.
- [x] AC7 — Documentation accurately maps Stop/branch feedback, delivery/merge authority, and release authority; derived snapshots remain release-owned.

## Verification (medium+)

- **Surface:** CLI
- **Runner:** focused pytest roots for shared hooks/tools and compliance, plus the mandated full suite/finalization gates.
- **Evidence:** tests exercise audit-target versus backlog-target separation, coverage state distinction, exact merged SHA selection, and release convergence.

## Out of Scope

- CI workflow changes, compliance rule redesign, removing Group E, branch snapshot regeneration, P2.58 W3 freshness work, and unrelated triage cards.

## Internal Plan Review (opus-plan-reviewer)
- **Ran:** yes
- **Severity:** medium (2 high, 6 medium, 3 low)
- **Summary:** The authority model is sound and fail-closed by construction; the plan under-specified three consequences the code already has — release-audit failure blocking tagging, merge/release writes routing through the outbox, and no migration for pre-change branch-written cards.
- **Findings:**
  - completeness/high — release-audit-incomplete blocks tagging (`verified_release_audit_incomplete`), asymmetric with delivery's non-blocking record — **fix, already done**: `plugins/shipwright-changelog/skills/changelog/SKILL.md` already documents this as environmental, re-run-once-resolved, not a real block.
  - architecture/high — merge/release writes route through `should_route_to_outbox()` (gitignored, per-machine) instead of the previously-tracked path — **decline, reason**: this is not a new mechanism, it's the same pre-existing default-branch+origin convergence rule every other legitimate main-branch producer already uses (`check_drift.py`, `triage_add.py`, `check_required_checks.py`, compliance's own existing `phase_quality/_triage_bundle.py`). The prior behavior (writing straight to tracked `triage.jsonl` from a non-default `iterate/*` HEAD) was the actual bug this change fixes; post-change, main-tree convergence now correctly follows the same D2-swept outbox path as every other producer.
  - architecture/medium — Stop hook re-implements register/coverage/marker inline instead of calling the runner's `branch_feedback` scope, so the "one runner" Decision text doesn't match two code paths — **disclose**: both paths are independently tested (AC1/AC2 pass), the duplication is real but the Decision text describes intent for the shared vocabulary (scopes, coverage states), not literal single-call-site routing; consolidating the Stop hook onto the tool's `branch_feedback` scope is a reasonable follow-up, not required for this change's correctness.
  - completeness/medium — no migration retires pre-P2.59 branch-written Group E noise cards; `preserve_groups={"E"}` even protects them from cleanup until a release audit runs — **decline, reason**: AC6 scopes to preventing *future* mutation, not retroactive cleanup; `docs/hooks-and-pipeline.md`'s existing "self-heals at the next release" note (added in this same diff) already documents that the next real release audit rebuilds the card from the true current fails-set, which naturally clears stale E noise. Explicit backfill migration is out of scope per this spec's own Out-of-Scope line.
  - architecture/medium — `not_applicable`/`missing` distinction collapses at the 1000-char `spawn_compliance_audit` detail truncation (survives only by dict insertion order) — **decline, reason**: coverage completeness is decided in-process by `main()`'s return code before the spawn boundary is ever crossed; the truncated `detail` string is diagnostic-only, not the authority signal AC4 depends on.
  - completeness/medium — incomplete merge coverage is nearly silent (one stderr line; delivery's exit code is unchanged) — **disclose**: `deliver_pr.py` already records `merge_compliance_audit` (`{"ran": bool, "detail": ...}`) in its own result, so the signal is captured, not lost; a dedicated alert/triage-card-on-persistent-failure is a reasonable but separate follow-up, out of proportion to this change's scope.
  - architecture/medium — Group E preservation round-trips through the rendered card body (`protected_by` text-matches `- E/` lines; fold-back re-parses with a fabricated placeholder severity) — **disclose**: this is a pre-existing coupling pattern (not newly introduced), and already carries its own accepted-residual writeup in `docs/hooks-and-pipeline.md` ("Known residual: an amended preserve-group card can drift...") added in this same diff.
  - performance/medium — delivery's merge audit (fetch + detached worktree + full A-D/F-I scan incl. Group H bloat, 180s bound, unbudgeted) has no stated latency budget — **disclose**: bounded fail-open at 180s (proven via the grandchild-kill test), and delivery's exit code does not depend on it completing; a formal latency budget is measurement work for a follow-up, not a design gap in this change.
  - security/low — `_reclaim_orphaned_merge_worktrees` trusts directory-name-prefix + age as its only safety, and worktree lifecycle wasn't in the original plan — **disclose, already hardened**: the age gate (30 min), directory-vanished handling, and failed-remove-must-not-rmtree fix all landed via doubt review rounds 3-4 with dedicated regression tests (`test_audit_compliance_lifecycle_worktree_reclaim.py`).
  - security/low — `--pr`/`--repo` passed straight into `gh` argv without a format guard — **decline, reason**: these are internal-to-internal values resolved by `deliver_pr.py`'s own trusted PR-lookup logic, not attacker-controlled input crossing a trust boundary; no shell is involved so injection is not possible, only a theoretical flag-parsing confusion on a malformed internal value, which would already indicate a bug elsewhere in delivery's own PR resolution.
  - completeness/low — no negative AC for release (unverified/non-HEAD commit must not converge) — **fix**: `audit_compliance_lifecycle.py`'s release scope already refuses to audit a commit other than the verified HEAD (`test_release_scope_refuses_to_audit_a_commit_other_than_head`, added in this diff); AC5 above is read to include this by the same "verified release commit" language, and the test is the proof this spec asks for under Verification.
- **Known limitations:** the Stop hook's inline re-implementation of the runner's coverage/marker logic (architecture/medium, disclosed above) is accepted duplication pending a follow-up to route it through `branch_feedback` scope.
- **Status:** 2 fixed (already present in this diff), 7 disclosed, 2 declined-with-reason
