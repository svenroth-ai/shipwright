# Mini-Plan: smoke unit 2 (campaign smoke-860-20261009, sub-iterate 2.0)

Run ID: iterate-2026-10-09-2-0-smoke-unit-two
Type: FEATURE, complexity medium (Stage-1 classifier; Step 3.4 re-check: medium, diff_loc 117, no risk flags)

## Files to create/modify
- new: `scripts/_smoke_check.py` — stdlib-only CLI; `check(project_root) -> (ok, message)`; exit 0/1.
- new: `docs/_smoke/unit-2.md` — one line of text.
- new: `shared/tests/test_smoke_unit2.py` — placed in the existing `shared/tests` root instead of a
  repo-root `tests/` (none exists; the root `conftest.py` one-test-root rule would make a new root
  unregistered). Subject loaded by path (ADR-045 register-before-exec).

## Work breakdown
1. Tests: missing file, whitespace-only file, non-empty file, directory at target path, CLI exit 1 on
   missing, CLI round-trip on the committed doc (exit 0).
2. Implement `scripts/_smoke_check.py`.
3. Create the doc.

## Test strategy
Unit tests via in-process load + two subprocess CLI tests. No E2E surface (no UI, no hook wiring).

## Alternative approach
Put the check inside `shared/scripts/checks/` as a registered gate wired into `verify_local.py`.
Rejected: the unit is a throwaway smoke for PR #860; wiring a gate would add a standing mechanism.
