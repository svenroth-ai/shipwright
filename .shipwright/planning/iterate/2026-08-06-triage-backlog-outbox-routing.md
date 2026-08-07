# Iterate Spec: triage-backlog-outbox-routing

- **Run ID:** iterate-2026-08-06-triage-backlog-outbox-routing
- **Type:** bug
- **Complexity:** medium (escalated mid-flight from small — see Mid-Flight Escalation below)
- **Status:** implemented

## Goal

Stop `ensure_current.py`'s pre-merge dirty-tree guard from aborting (exit 6,
"Your local changes would be overwritten by merge") when a background
producer — the compliance-backlog Stop hook, P2.43 — has left
`.shipwright/triage.jsonl` uncommitted at the moment F11 tries to integrate
fresh `origin/main`. Measured twice in one run
(iterate-2026-08-06-architecture-review-pass) and on PR #582 across two
consecutive integration attempts, which had to carry the appends onto the
branch as chore commits by hand to proceed.

## Acceptance Criteria

- [x] AC1: `ensure_current()` no longer fails with `merge_failed` when
  `.shipwright/triage.jsonl` is dirty (uncommitted) at the moment a merge
  with `origin/<default>` is attempted.
- [x] AC2: the dirty content is not discarded — it lands in a small commit
  on the iterate branch, so nothing a background producer wrote is lost.
- [x] AC3: when both the worktree's uncommitted content AND origin's
  committed content touch the same path, the existing churn resolver
  (`triage.jsonl` is a recognized churn file) still reconciles them — this
  fix removes the pre-merge refusal, it does not bypass conflict
  resolution.
- [x] AC4: a clean (non-dirty) `triage.jsonl` adds no new step and changes
  no existing behavior — this is a purely additive absorption, not a
  rewrite of the merge flow.

## Spec Impact

- **Classification:** none
- **NONE justification:** this is an internal defect in Shipwright's own
  finalization plumbing (`ensure_current.py`, an iterate-lifecycle
  mechanism), not a product-facing feature/requirement described by any
  project FR/spec. It restores intended behavior (a background producer's
  writes should never be able to block an iterate's own merge), it does
  not add or change a requirement.

## Out of Scope

- Changing where the compliance-backlog producer writes (`should_route_to_outbox`,
  `triage_bundle.py`). **Investigated and rejected** — see "Alternative
  Approach" in the mini-plan. The producer's existing branch-gated routing
  is unchanged by this fix.
- Any OTHER file that a background producer might dirty mid-run. Scoped
  strictly to `.shipwright/triage.jsonl`, the one path in the actual
  report and the one with an existing churn-merge resolver making a
  commit-before-merge safe.

## Design Notes

n/a — no UI, no design surface.

## Affected Boundaries

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| the compliance-backlog Stop hook (`triage_bundle.emit_compliance_backlog`, unchanged by this fix) | `ensure_current.py`'s new `_absorb_dirty_triage_log`, then `git merge` + the existing churn resolver (`churn_merge.py`/`resolve_churn_conflicts.py`) | JSONL (`.shipwright/triage.jsonl`) |

## Confidence Calibration

- **Boundaries touched:** the tracked `triage.jsonl` file, at the exact
  moment `ensure_current.py` is about to merge `origin/<default>` into an
  iterate branch.
- **Empirical probes run:**
  - Reproduced the EXACT reported git error verbatim (`error: Your local
    changes to the following files would be overwritten by merge:
    .shipwright/triage.jsonl`) against the unfixed code, by stashing the
    fix and re-running the new regression test — confirmed RED, then
    GREEN after restoring the fix.
  - Verified the fix does not just suppress the symptom: the test asserts
    BOTH sides' appends (`trg-main` from origin, `trg-worktree` from the
    uncommitted local write) survive in the merged file — proving the
    churn resolver still reconciles content rather than one side silently
    winning.
  - Verified a clean `triage.jsonl` adds no spurious `triage-absorbed`
    step (regression test), so the absorption is truly conditional.
- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | A dirty tracked `triage.jsonl` no longer blocks `ensure_current`'s merge | tested | `test_ensure_current_triage_absorb.py::test_ensure_current_absorbs_dirty_triage_log_before_merging` PASSED |
  | 2 | The absorbed content is committed, not discarded, and both sides of a genuine divergence survive the churn-resolved merge | tested | same test — asserts `trg-main` and `trg-worktree` both present in the merged file |
  | 3 | A clean, TRACKED `triage.jsonl` triggers no absorb step (no behavior change on the common path) | tested | `test_ensure_current_triage_absorb.py::test_ensure_current_clean_triage_log_adds_no_absorb_step` PASSED — seeds a real committed log, not merely an absent one (Stage-2 review, low) |
  | 4 | `cross_component` integration: the absorb step composes correctly with the REAL git merge + REAL churn resolver, not a mocked one | tested (`category: integration`) | same as #1/#2 — real `git_origin_repo`/`make_worktree` fixtures, no mocking of `integrate_main`/`churn_merge` |
  | 5 | An absorb commit that is the ONLY commit that lands (the underlying merge is a genuine no-op) is still reported `integrated=True`, so the caller re-pushes and the content isn't lost | tested | `test_ensure_current_triage_absorb.py::test_ensure_current_absorb_commit_alone_counts_as_integrated` PASSED — regression for a Stage-2-caught ordering bug (`head_before` was captured after the absorb) |
  | 6 | A dirty `triage.jsonl` while a merge is already wedged (`MERGE_HEAD` standing) is left untouched, not staged into a possibly-unmerged index | tested | `test_ensure_current_triage_absorb.py::test_absorb_skips_when_a_merge_is_already_in_progress` PASSED — regression for a Stage-2-caught unconditional-`git add` bug |
  | 7 | The pre-existing `ensure_current` regression tests (noop-when-current, integrates-when-behind, blocks-on-source-conflict, CLI, lost-ledger-exit-9) are unaffected | tested | `test_ensure_current.py`, 5/5 passed |
  | 8 | The absorb fires on the ALREADY-CURRENT path too (not only "behind, about to merge"), so background writes accumulating between the delivery ladder's repeat refresh calls are not silently lost at worktree teardown | tested | `test_ensure_current_triage_absorb.py::test_ensure_current_absorbs_on_the_already_current_path_too` PASSED — Stage-3 doubt review, high |
  | 9 | The op-in-progress guard now covers merge/rebase/cherry-pick/revert/bisect (reusing `lib.main_tree_guards.op_in_progress`, fail-closed), not just a bare `MERGE_HEAD` check | tested | same as #6, plus `lib.main_tree_guards`'s own test suite (`test_reconcile_triage_guards.py`, 10/10 passed) covers the primitive itself — Stage-3 doubt review, medium |
  | 10 | An untracked `triage.jsonl` is not silently promoted to tracked by this guard | tested | `test_ensure_current_triage_absorb_guards.py::test_absorb_skips_an_untracked_triage_log` PASSED — asserts the `??` state directly and that nothing was staged — Stage-3 doubt review, low |
  | 11 | Malformed/torn content is never committed by the absorb (validated via `lib.triage_validate.validate_triage_text` before staging) | tested | `test_ensure_current_triage_absorb_guards.py::test_absorb_refuses_to_commit_torn_content` PASSED — Stage-3 doubt review, low |
  | 12 | A failed `commit` resets the index, leaving it exactly as it was before the call rather than staged-and-uncommitted | tested | `test_ensure_current_triage_absorb_guards.py::test_absorb_resets_the_index_when_the_commit_fails` PASSED — asserts the unstage AND that the producer's content survives in the worktree |
  | 13 | A failed `add` leaves the index untouched and git's stderr reaches the operator | tested | `test_ensure_current_triage_absorb_guards.py::test_absorb_reports_a_failed_stage_and_leaves_the_index_alone` PASSED — Stage-3 doubt review, medium (the original code discarded git's stderr entirely) |
  | 14 | A deletion of the append-only log is never absorbed (the guard would otherwise propagate it to `main`) | tested | `test_ensure_current_triage_absorb_guards.py::test_absorb_skips_a_deleted_triage_log` PASSED — external review, openai low |
  | 15 | An unreadable log declines rather than staging bytes nothing validated | tested | `test_ensure_current_triage_absorb_guards.py::test_absorb_skips_when_the_log_cannot_be_read` PASSED |
  | 16 | A best-effort diagnostic that itself fails never propagates out of the merge guard | tested | `test_ensure_current_triage_absorb_guards.py::test_a_failed_diagnostic_never_crashes_the_guard` PASSED |

- **Confidence-pattern check:** asymptote — the FIRST fix attempt (routing
  the producer to the gitignored outbox unconditionally) looked complete
  and passed its own tests, but a Stage-2 code review found it half-applied
  (append fixed, dismiss path not) AND introduced a silent data-loss hazard
  (a worktree's own outbox is delivered by nothing and destroyed at F11) —
  a documented hazard from a fix landed the day before
  (`iterate-2026-08-05-wire-local-guard-scripts`). That "yes, confident"
  moment produced a real finding, so per the asymptote rule this spec
  documents the SECOND probe: reproducing the bug against the new fix's
  absence (RED) before claiming it fixed (GREEN). Coverage: all 16 ledger
  rows tested, 0 untested-testable, 0 untestable.

  A THIRD probe was then forced by measurement rather than by review. F0's
  diff-coverage gate measured the changed lines at **65%** and named them,
  falsifying two ledger claims that had survived every review pass: row 11
  was credited to `test_triage_validate.py` (which exercises the VALIDATOR,
  never this guard's decision to call it), and row 12 was declared
  `untestable` because forcing a real `git commit` to fail would destabilize
  the shared fixture — true of the fixture, but the module-object seam
  `integrate_main._git` (ADR-045) tests it without touching the repository at
  all. Seven tests in a new `test_ensure_current_triage_absorb_guards.py`
  took the changed lines to **100%**. This is why the gate is not advisory:
  "covered by an existing test" and "untestable" are both claims, and only a
  measurement tells them apart from the truth.

## Verification (medium+)

- **Surface:** none
- **Justification (only if surface=none):** pure backend/CLI plumbing
  (`ensure_current.py`, a script invoked by the iterate finalization
  pipeline) — no `dev_url`, no browser-reachable surface. Verified via the
  integration test suite instead (real git repos, real merges).

## Architecture Review

- **Brief:** `.shipwright/planning/iterate/iterate-2026-08-06-triage-backlog-outbox-routing/architecture_brief.md`
- **Verdicts:** deepseek=approve · openai=approve
- **Smallest thing that would do (per reviewers):** Option A, as proposed —
  a conditional pre-merge check in `ensure_current.py` that stages and
  commits only `.shipwright/triage.jsonl` when dirty, then uses the
  existing merge and churn-resolution path.
- **Findings:** none from either reviewer.
- **Reconciliation:** both reviewers independently confirmed the built
  approach (Option A in the brief) as the smallest thing that would do,
  without having seen this spec's own rejection rationale for Option B
  (the reverted outbox-routing attempt) — the brief listed options without
  reasons, per protocol. No divergence to reconcile: what was built is
  what both reviewers, reasoning from the problem statement alone, would
  also have built.

## Mid-Flight Escalation

Started at **small** (Stage-1 message-only classification: no risk-flag
keyword). Stage-2's diff-driven detector, run against the FIRST fix
attempt's file set, returned `cross_component: False` (that diff touched
only `shared/scripts/triage.py` + `plugins/shipwright-compliance/...` +
tests — none of the named cross-component patterns). After Stage-2
code review rejected that attempt and the fix was rearchitected to touch
`shared/scripts/tools/ensure_current.py` — named explicitly in the
`cross_component` risk-flag trigger list (`integrate_main`, `ensure_current`,
`churn_merge`, ...) — re-running the diff-driven detector against the NEW
file set returned `cross_component: True`. Per SKILL.md: `cross_component`
floors classification at **medium** and enforces integration-coverage
(a `category:"integration"` behavior in the ledger, ledger row #4 above).
Escalated accordingly; `--autonomous` mode proceeds without an approval
stop (the original task already bounded the decision space to "how to
fix this," per its own `AUTO` framing).
