# Iterate Spec — Remove noisy timestamp-drift sub-check

- **Run ID:** iterate-2026-06-28-drop-timestamp-drift
- **Intent:** CHANGE (behaviour reduction — remove a noisy detector)
- **Complexity:** medium (diff-driven `cross_component`: `check_drift.py` matches
  `(^|/)hooks/.+\.py$`)
- **Spec Impact:** NONE — no product FR `spec.md` is touched; this is
  framework-internal dev-tooling (a SessionStart hook). FR-gate branch: No-FR,
  `change_type=tooling`. (Code-level, `check_drift.py` keeps content-drift and
  drops timestamp-drift.)
- **Risk flags:** `cross_component` → integration_coverage + full_test_suite

## Problem

The SessionStart hook `shared/scripts/hooks/check_drift.py` runs two independent
detectors. The **timestamp-drift** detector compares the filesystem **mtime** of
`CLAUDE.md` against a hard-coded `KEY_FILES`/`KEY_DIRS` list and warns
"CLAUDE.md may be outdated" when any is newer.

mtime is not a reliable signal for *content* staleness in a git repo:

- Git does not preserve mtimes — a fresh clone, `git checkout`, branch switch, or
  **worktree creation** stamps every file with the checkout time, so the
  CLAUDE.md-vs-config ordering is effectively random.
- Tooling touches config files routinely (`uv sync`, a release `version =` bump).
- Concrete proof: the warning that triggered this iterate fired because
  `pyproject.toml`'s last change was the v0.29.1 release one-liner
  `version = "0.29.0" → "0.29.1"` — nothing architectural.
- The `shipwright-iterate` worktree-per-run model guarantees fresh mtimes, so the
  timestamp detector fires on essentially every iterate regardless of real drift.

This is a **plugin-level** issue: the hook is shared (`shared/scripts/hooks/`,
registered in iterate/build/security) and fires for every Shipwright project.

The **content-drift** detector (Structure block + `npm run` references vs. the
real filesystem / `package.json`) is deterministic and content-based — genuine
signal. It stays.

## Acceptance Criteria

- **AC-1** `check_timestamp_drift`, `get_newest_in_dir`, `get_mtime`, `KEY_FILES`,
  `KEY_DIRS` are removed from `check_drift.py`; the timestamp warning block is
  removed from `main()`.
- **AC-2** `_emit_drift_to_triage` no longer accepts/emits `timestamp_drifted`;
  the producer never creates a new `:timestamp` triage item.
- **AC-3** The resolve pass still dismisses pre-existing open `:timestamp` drift
  items (migration: stale items clear on the next run) and still leaves
  `artifact_sync`'s `:artifact` items untouched.
- **AC-4** Content-drift detection (structure + command) is unchanged: same
  warnings, same `:content` triage items, same hook exit-0 semantics.
- **AC-5** The hook produces **no** "Timestamp drift" warning even when a former
  `KEY_FILE` (e.g. `pyproject.toml`) is newer than `CLAUDE.md`.
- **AC-6** `docs/hooks-and-pipeline.md` no longer describes a timestamp detector.

## Affected Boundaries

- SessionStart hook stdout contract (`hookSpecificOutput.additionalContext`).
- `.shipwright/triage.jsonl` producer surface (`source="drift"` items).
- Function signature `check_drift._emit_drift_to_triage` (internal; only `main()`
  and tests call it — `artifact_sync._emit_drift_to_triage` is a separate fn).

## Confidence Calibration

- **Boundaries touched:** hook stdout (drift warning text), `.shipwright/triage.jsonl`
  drift producer, `_emit_drift_to_triage` signature.
- **Empirical probes run:**
  - Subprocess hook run, CLAUDE.md (no Structure) + newer `pyproject.toml` → exit 0,
    **no** "Timestamp drift"/"DRIFT WARNING" in stdout, empty stdout
    (`test_no_timestamp_warning_when_keyfile_newer` PASSED).
  - Subprocess hook run, Structure block listing a missing dir → "Content drift" +
    "ghostdir" warned, **no** "Timestamp drift" (`test_content_drift_still_detected`
    PASSED).
  - End-to-end: Shipwright project + content drift + pre-seeded legacy `:timestamp`
    item → legacy item `dismissed`/`driftResolved`, one open `:content` item, exit 0
    (`test_integration_hook_composes_content_drift_and_retires_timestamp` PASSED).
  - Function-level: legacy `:timestamp` item retired on a no-findings run
    (`test_check_drift_hook.py::test_producer_retires_legacy_timestamp_item` PASSED).
  - Static: repo-wide grep → zero `.py` refs to removed symbols; `py_compile` OK;
    ruff 0.15.15 clean; full `shared/tests` (3596) + `shared/scripts/tests` (196) +
    `shared/scripts/tools/tests` (61) green.
- **Test Completeness Ledger:** see `shipwright_test_results.json`
  `iterate_latest.test_completeness` — AC-1…AC-6 each `tested` (AC-6 docs prose →
  `untestable`/`requires-manual-visual-judgment`), 0 untested-testable, plus one
  `category:"integration"` behavior.
- **Confidence-pattern check:** asymptote (depth) — removal proven by grep + compile
  + ruff + full suite, not by "looks right"; coverage (breadth) — function-level +
  subprocess + end-to-end; integration composition — `category:"integration"`
  subprocess test proves the hook composes with the triage store (`cross_component`
  gate satisfied).
