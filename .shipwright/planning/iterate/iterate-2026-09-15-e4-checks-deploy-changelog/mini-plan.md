# Mini-Plan — e4-checks-deploy-changelog

## Goal

Close the `prompt-only (mechanisable)` lines the REQ-3 AC-evidence ledger
names under FR-01.08 (`/shipwright-deploy`) and FR-01.09 (`/shipwright-changelog`).
The spec's own AC ("10 lines enforced or downgraded with a reason") undercounts
against the ledger's actual candidate set at start-of-run; every ledger row
touching these two FRs was worked (11 line-items across 5 FR-01.08 rows, one
split into two halves, and 4 FR-01.09 rows — the FR-01.09 count also folds in
two rows a prior campaign (req3-05, sub-iterate t5) had already covered, which
this sub-iterate confirmed rather than re-built). Per campaign decision D7, no
line may become a fake/weak gate — each either gets a deterministic check +
test, or is explicitly recorded as `judgement` with a documented reason.

## Approach

**FR-01.08 (`/shipwright-deploy`) — 5 rows, all built:**

- #1 "the failing-tests gate is real, not a suggestion": new `_test_gate`
  in `validate-deploy.py` reads `shipwright_test_results.json`
  (`unit.status`/`e2e.status`) and refuses on a `failing` state unless
  `--confirm-failing-tests` is passed; `no-results` is its own state so an
  absent ledger is distinguishable from a passing one.
- #5 / #7 (offer + record halves of the same override contract): unified
  `rollback_audit.py` JSONL trail (`rollback-history.jsonl`) — every
  `rollback.py` invocation is recorded unconditionally (`--invocation
  {auto,manual}`), and an override (`--ack-data-drift` against a
  drifted/unknown state) is refused outright unless `--override-reason` is a
  non-empty string, so "an override happened without a written reason" is
  now structurally impossible rather than a documentation ask.
- #4 / #8 (failed-liveness-recorded + manual-rollback-proves-alive): reused
  the same two artifacts as oracles rather than inventing new ones —
  `smoke_test.py --output` persists a stamped `smoke-test-result.json`, and
  the two new checks in `shared/scripts/tools/verifiers/deploy_checks.py`
  (`check_failed_liveness_recorded_as_failed`,
  `check_manual_rollback_proves_alive`) reconcile that file and the rollback
  history against `phase_history`'s recorded release outcome. The SKILL.md
  "Smoke Test Failed -> Rollback" flow was rewritten to call
  `append_phase_history.py` with `"outcome":"failed"` BEFORE attempting
  rollback, closing the gap the new checks would otherwise flag.

**FR-01.09 (`/shipwright-changelog`) — 4 rows, 2 built + 2 confirmed already covered:**

- #3 "a release with an empty Unreleased section is refused, not silently
  tagged": new `--fail-if-empty` flag on `aggregate_changelog.py`'s
  `aggregate()`, using the existing `section_starts` helper to detect a
  version section that was never populated.
- #7 "old-style entries reported loudly — each one named back to the
  operator, not just a count" (the ledger's actual wording; this is visibility,
  not a refusal — legacy bullets are deliberately NOT force-migrated, per the
  operator-choice note already on this row): `_warn_if_legacy_unreleased_has_bullets()`
  renamed to `_legacy_unreleased_bullets() -> list[str]`, returned list
  surfaced in both the result dict (`legacy_unreleased_bullet_texts`) and the
  warning message.
- #8 / #9 and the marking-half of #1: confirmed already covered by the prior
  campaign (req3-05, sub-iterate t5, PR #747) rather than re-built — verified
  against that sub-iterate's own AC-binding mini-plan and the tests it left
  behind before touching the ledger row, per the "verify the claim, not its
  neighbourhood" rule. No new code for these; the ledger status/citation was
  corrected to point at the existing coverage.

## Risk / boundaries

`touches_io_boundary`-adjacent: every new check reads already-produced
project-tree JSON/JSONL by path (`shipwright_test_results.json`,
`smoke-test-result.json`, `rollback-history.jsonl`, `phase_history`) — no
check performs a network call, executes an external command, or mutates
deploy/release state itself. `rollback_audit.record()` is the one new
*write* path (JSONL append), and it is unconditional so no invocation of
`rollback.py` — successful, refused, or halted — goes unrecorded. Constants
(`_SMOKE_RESULT_RELATIVE`, `_ROLLBACK_HISTORY_RELATIVE`,
`_FAILED_RELEASE_OUTCOMES`) are deliberately duplicated into
`shared/scripts/tools/verifiers/deploy_checks.py` rather than imported from
the plugin-local `scripts/lib/` modules, per ADR-045 (no cross-plugin `lib/`
imports). No frontend surface touched.

## Out of scope (recorded on the ledger, not built)

- Any line whose only possible oracle would be an LLM judging quality
  (e.g. interactive `AskUserQuestion` confirmation steps, best-effort `gh pr
  create` calls) — downgraded to `prompt-only (judgement)` with the specific
  reason recorded in the ledger row rather than wrapped in a fake gate.
