# Iterate: Durable atomic writes (fsync) for all atomic writers

- **Run ID:** `iterate-2026-06-13-atomic-write-fsync-durability`
- **Intent:** CHANGE (cross-cutting durability hardening)
- **Complexity:** medium (keyword-sourced, confidence 0.7)
- **Source:** External review of `iterate-2026-06-13-runconfig-atomic-writes` (WP2,
  concurrency). Out of WP2 scope — WP2 closed *torn reads* (concurrency); this
  closes *lost writes* (durability).

## Problem

`run_config_store.atomic_write_json` and ~20 sibling atomic-write helpers do
`tmp + os.replace` **without `fsync`**. `os.replace` prevents a reader from
seeing a half-written file (torn read), but it does **not** make the bytes
durable: a crash or power-loss after `replace` returns — but before the OS
flushes the page cache — can leave the file empty or stale (lost write). Two
writers (`phase_quality/_findings`, `record_event` commit-patch,
`triage_gc` compaction) already `fsync`; the rest diverge. The fix is a
cross-cutting durability decision applied consistently.

## Decision

Introduce **one shared durable-write primitive** and route every atomic-write
helper through it, instead of duplicating `fsync` across ~20 copies:

`shared/scripts/lib/atomic_write.py::durable_atomic_write(path, data: str|bytes)`
1. write `data` (str → UTF-8, verbatim — no newline translation) to a
   same-directory temp file,
2. `flush()` + `os.fsync(fd)` — temp bytes are on disk **before** the rename,
3. `os.replace(tmp, path)` — atomic on POSIX and Windows,
4. best-effort `os.fsync` of the **parent directory** (POSIX only; Windows has
   no directory fsync and its replace is durable on its own) so the rename
   itself survives a crash,
5. on any failure, unlink the temp file and re-raise.

`str|bytes` (not a JSON variant): each caller keeps its own `json.dumps(...)`
line, preserving its exact serialization kwargs and trailing-newline choice, so
the migration is **byte-identical** to today's output — `fsync` is the only
behavioral addition. Orthogonal to `file_lock`/`run_config_store` (which
serialize *concurrent* writers); this makes a *single* writer's bytes durable.

## Scope

**New:** `shared/scripts/lib/atomic_write.py` (+ unit tests, boundary probe,
cross_component integration test).

**Migrated (20 named helpers → delegate the write to the primitive; signatures
unchanged → blast radius = the primitive's correctness):**
`run_config_store.atomic_write_json`; shared/lib: `gitattributes_selfheal`,
`gitignore_selfheal`, `sweep_outbox`, `reconcile_triage`, `worktree_isolation`,
`bloat_baseline.write_baseline`, `phase_quality/_findings`; shared/tools:
`append_changelog_entry`, `aggregate_changelog`, `append_iterate_entry`,
`append_phase_history`, `finalize_iterate`; shared/hooks: `check_file_size`,
`audit_compliance_on_stop`, `mark_plugin_edit`; `dev_server/state`; plugin-local:
`shipwright-project/config`, `shipwright-build/update_section_state`,
`shipwright-security/run_scan_and_report`.

**Left as-is (already `fsync`-durable, embedded inline with surrounding
backup/patch logic — restructuring earns no durability and adds risk):**
`record_event.py` commit-patch path; `triage_gc.py` compaction.

**Excluded (not a tmp-write):** `phase_quality/_aggregates.py` GC archive move.

## Acceptance Criteria

1. `durable_atomic_write` writes `str` and `bytes` verbatim and round-trips
   byte-identically (incl. embedded `\n`, no `\r\n` translation, no spurious
   trailing newline).
2. `os.fsync` of the temp file fd is called **before** `os.replace` (durability
   ordering — the contract the review asked for).
3. Parent-directory fsync is best-effort: a failing dir-fsync (or Windows, where
   it is skipped) does not fail the write.
4. On `os.replace` failure the temp file is cleaned up and the error propagates;
   no `.tmp` leftovers on success.
5. Parent dirs are created if missing; overwrite is wholesale (no stale tail).
6. Every migrated helper keeps its public signature and byte-identical output,
   and now routes its write through the primitive (verified by the integration
   test spying `os.fsync`).
7. Full suite green; `run_config_store` + concurrency tests still pass.

## Affected Boundaries

`touches_io_boundary` (writers of `*_config.json`/`*_state.json`/`*.jsonl` +
`json.dump` producers) and `cross_component` (touches `gitattributes_selfheal`,
`sweep_outbox`, `reconcile_triage`, churn/event-log + hook writers) — both
recomputed from the diff at their gates; planned for accordingly.

## Confidence Calibration
- **Boundaries touched:** `touches_io_boundary` (config/state/jsonl writers) and
  `cross_component` (gitattributes/gitignore self-heal, hook + event-log-adjacent
  writers) — both recomputed from the diff at their gates.
- **Empirical probes run:**
  - fsync-precedes-replace ordering, spying `os.fsync`/`os.replace` → `fsync`
    index < `replace` index (`test_file_is_fsynced_before_replace`). **Finding:** durable.
  - str/bytes/unicode/embedded-`\n` verbatim round-trip → bytes identical, no
    CRLF, no invented trailing newline (`test_roundtrip_*`, `test_str_written_verbatim…`).
  - error path: `os.replace` raises → tmp unlinked, error propagates, target
    never created (`test_replace_failure_cleans_tmp_and_raises`). **Finding:** clean.
  - dir-fsync best-effort: OSError swallowed (`test_fsync_parent_dir_swallows_oserror`,
    `test_full_write_survives_dir_fsync_failure`); Windows skips `os.open`
    (`test_windows_skips_directory_fsync`). **Finding:** never fails the write.
  - cross-writer composition: 5 writers across `shared/{lib, lib/phase_quality, tools}`
    each fsync-before-replace under one spy + byte-correct round-trip
    (`test_atomic_write_durability_integration`). **Finding:** the whole family composes.
- **Test Completeness Ledger:**

  | Behavior (AC) | Status | Evidence |
  |---|---|---|
  | AC1 str/bytes verbatim round-trip | `tested` | `test_roundtrip_str/_bytes`, `…_verbatim_no_newline_translation`, `…_unicode_roundtrip` (green) |
  | AC2 fsync precedes os.replace | `tested` | `test_file_is_fsynced_before_replace` + integration ordering (green) |
  | AC3 dir-fsync best-effort (POSIX swallow + Windows skip) | `tested` | `test_fsync_parent_dir_swallows_oserror`, `test_full_write_survives_dir_fsync_failure`, `test_windows_skips_directory_fsync` (green) |
  | AC4 error cleanup + propagation | `tested` | `test_replace_failure_cleans_tmp_and_raises` (green) |
  | AC5 parent-dir create + wholesale overwrite + no tmp leftover | `tested` | `test_creates_parent_dirs`, `test_overwrite_is_wholesale`, `test_no_tmp_leftover_on_success` (green) |
  | AC6 every migrated helper byte-identical + routed through primitive | `tested` | integration test (5 writers, fsync spy + round-trip) + existing per-module suites (651 passed unchanged) + `test_run_config_store` round-trip |
  | AC7 full suite green | `tested` | F0 full suite (recorded in test results) |
  | integration: writers compose on one durable primitive | `tested` (`category:"integration"`) | `test_atomic_write_durability_integration` |

  0 testable-but-untested behaviors; no `untestable` rows (true power-loss isn't
  simulated — the fsync-ordering spy is the accepted proxy for the durability contract).
- **Confidence-pattern check:** asymptote (depth) — the primitive has dedicated
  unit tests for ordering, error path, and both dir-fsync branches; coverage
  (breadth) — 20 migrated helpers, each retaining its existing per-module suite,
  plus a 5-writer cross-subsystem composition test; integration composition —
  satisfied by the `category:"integration"` test that proves `shared/lib`,
  `phase_quality`, and `shared/tools` writers all funnel through the durable path.
