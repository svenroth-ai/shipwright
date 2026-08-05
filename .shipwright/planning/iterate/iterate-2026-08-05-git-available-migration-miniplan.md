# Mini-Plan: Migrate the remaining `_git_available` callers onto `git_context`

- **run_id:** `iterate-2026-08-05-git-available-migration`
- **complexity:** medium (scope keyword match — multi-file F11 gate semantics
  change; no risk-taxonomy flag actually applies to the diff)

## Files

- Edit `shared/scripts/tools/verifiers/git_helpers.py` — delete `_git_available`.
- Edit `shared/scripts/tools/verifiers/iterate_checks.py` — migrate
  `check_spec_impact_recorded`'s git-availability branch (line 949) to
  `git_context`, SKIP on `not_git`, refuse otherwise.
- Edit `shared/scripts/tools/verifiers/spec_checks.py` — migrate S4/S9/S10
  (lines 336, 611, 704) to `git_context`; keep SKIP for both non-work-tree
  states (Tier-2 WARN ceiling); update the `_git_available` import.
- Edit `shared/scripts/tools/verifiers/_layer_coverage_regen.py` — migrate
  `regenerate_base_head`'s check (line 275) to `git_context`.
- Edit `shared/scripts/tools/verifiers/test_results_evidence_check.py` and
  `test_results_backfill_check.py` — split "no commit supplied" from "git
  faulted", migrate the fault branch to `git_context` with a refuse outcome.
- Edit `shared/tests/test_git_helpers.py` — remove the now-obsolete
  `test_git_available_true_on_repo_false_off_repo` test and its docstring
  bullet.
- Edit `shared/scripts/tools/verifiers/ci_supplychain.py` and
  `integration_coverage.py` — docstring-only: both named this card as the
  still-outstanding remainder; update to say it is closed.
- Add `shared/tests/test_check_spec_impact_recorded_infra.py` and
  `shared/tests/test_check_test_results_infra.py`, mirroring
  `test_check_ci_supplychain_infra.py`'s shape.
- Extend `shared/tests/test_spec_checks.py` for the S4/S9/S10 probe swap
  (message no longer claims unconditional "git unavailable" on a real fault).

## Work Breakdown

1. Delete `_git_available` from `git_helpers.py` first (TDD red: every caller's
   import now breaks) — confirms via import error that the caller list drawn up
   in the spec is complete and nothing was missed.
2. Migrate `iterate_checks.py:check_spec_impact_recorded` — the named F11 ERROR
   gate — to the exact `ci_supplychain.py` pattern. Add its infra test file.
3. Migrate `spec_checks.py` S4/S9/S10 together (same file, same import line).
   Update existing S4/S9/S10 "git unavailable" assertions in `test_spec_checks.py`
   to match the new message wording; the SKIP outcome itself is unchanged so
   most existing assertions should not need to move.
4. Migrate `_layer_coverage_regen.py:regenerate_base_head`. Run the full
   `test_layer_coverage_*` suite as a regression gate — behavior must be
   byte-identical since both real callers already pre-gate via `git_context`.
5. Migrate `test_results_evidence_check.py` and `test_results_backfill_check.py`
   together (same shape, same fix). Add the shared infra test file covering
   both.
6. Full-repo grep for `_git_available` — zero hits outside git history/this
   spec's own prose. Run `shared/tests`, lint, `verify_local.py`.

## Test Strategy

- New infra test files follow `test_check_ci_supplychain_infra.py`'s pattern:
  not-a-repo SKIPs, a parametrized-by-tier git-fault-inside-a-repo case,
  unrecognised-`git_context`-value fails closed, localized non-repo message
  still SKIPs (inside and outside a real repo), and the message text no longer
  claims "not a git repository" / "git unavailable" about a directory that
  answered with a real fault.
- `regenerate_base_head` gets no new test — its two real callers are already
  covered end-to-end by the existing `test_layer_coverage_hardening.py` /
  `test_layer_coverage_gate_integration.py` suites, which pin the exact
  ERROR-not-SKIP behavior this migration must preserve byte-for-byte.
- `shared/tests` full root run is the completeness gate (one pytest root, per
  the repo's hard rule).

## Alternative Rejected

Doing only the 5 call sites the finding named, and filing the 2 undocumented
`test_results_*_check.py` sites (added by PR #540, 2026-08-03) as a *new*
follow-up card, was considered and rejected: they are the identical shape
(`if not commit_hash or not _git_available(root): SKIP`) on the identical
severity class (F11 `Severity.ERROR` default), so leaving them would both ship
an incomplete migration under this run's own AC-5 ("no remaining reference to
`_git_available` anywhere in the repo") and reintroduce, in a fresh location,
the exact defect this card exists to close. Fixing them now costs two extra
near-identical call sites in one already-open diff instead of two additional
review/PR/CI cycles for a bug that is already fully diagnosed.

Escalating S4/S9/S10 from SKIP to a stronger severity on a git fault was
considered and rejected: `spec_checks.py`'s own module docstring caps these at
Tier-2/WARN, and `test_spec_checks.py` already pins that S10 can never return
`STATUS_FAIL`. Inventing an escalation path for a tier that structurally has no
FAIL state would be a larger, uninvited redesign of the Tier-1/Tier-2 contract,
not a `_git_available` migration.
