# Mini-Plan: iterate-2026-06-13-shc-file-lock

Campaign: 2026-06-13-shared-helper-consolidation (sub-iterate A)

## Problem

Reducibility-catalog D-finding (duplication). The cross-platform
block-until-acquired `_FileLock` class is copied near-identically in
`shared/scripts/tools/record_event.py` (~line 55) and
`shared/scripts/triage.py` (~line 187). Two copies drift over time; the
triage copy already diverged (its `__enter__` does
`self._lock_path.parent.mkdir(parents=True, exist_ok=True)` — a strict
superset the record_event copy lacks).

## Approach (pure behavior-preserving refactor — Spec Impact NONE)

1. Extract ONE class `FileLock` into the EXISTING module
   `shared/scripts/lib/file_lock.py`. That module already hosts a
   *different* primitive — a `file_lock()` timeout context-manager function
   used by `append_changelog_entry.py` / `append_phase_history.py`. The new
   block-until-acquired class lives ALONGSIDE it; the existing function and
   its `LockTimeout` are untouched (no behaviour change for those callers).
2. Unify on the triage variant (the superset with parent-dir mkdir) so
   neither call site regresses.
3. Both call sites import it aliased to the historical private name:
   `from lib.file_lock import FileLock as _FileLock`. This is load-bearing:
   - `record_event._FileLock` is monkeypatched by
     `test_record_event_lifecycle_integrity.py` (F14 scan-under-lock proof);
   - `triage._FileLock` is imported by `sweep_outbox.py`, `triage_gc.py`,
     `reconcile_triage.py`, and `test_triage_wp9_sanitize_outbox.py`.
   Keeping the module attribute `_FileLock` on both modules preserves all
   those external references with zero edits to the consumers.
4. Delete both local class definitions.
5. Add a focused `test_file_lock.py` (mutual-exclusion + parent-dir creation
   + reusability).

## Risk

Low. No new third-party dependency (catalog P). No I/O-boundary, auth, RLS,
migration, billing, or public-API change. The classifier keyword-estimate is
`medium` (prose mentions "module/class/extract" across multiple files) but
the diff-driven reality is a behavior-preserving move with `risk_floor:
trivial` and zero risk flags. Existing tests for both call sites stay green
with NO assertion changes (G3).

## Acceptance Criteria

- New `FileLock` in `lib/file_lock.py`; both local copies deleted.
- `__enter__` creates the lock parent dir (superset; no regression).
- `record_event._FileLock` and `triage._FileLock` remain resolvable.
- test_record_event.py + test_triage_storage.py + all triage/sweep/gc
  consumers stay green, no assertion changes.
- ruff clean; full `shared/tests/` suite green.
