# Mini-Plan: deterministic-render-timestamps

- **Run ID:** iterate-2026-05-22-deterministic-render-timestamps
- **Complexity:** medium

## Files to change

### New

1. `shared/tests/test_render_determinism.py` — parametrized determinism
   tests for all 4 renderer-groups + the helper + the "different input
   → different output" sanity check.

### Modify (shared)

2. `shared/scripts/lib/events_log.py`
   - Add `latest_event_dt(project_root: Path | str) -> datetime | None`.
   - Helper iterates raw events.jsonl line-by-line (no full collect),
     parses just the `ts` field, returns the max as a UTC datetime.
   - Returns `None` if log missing / empty / all-corrupt.
   - Tolerant of corrupt lines (skip silently with warnings.warn,
     matching `_read_event_log` precedent).

3. `shared/scripts/tools/update_build_dashboard.py`
   - Import the helper.
   - Replace both `datetime.now(...)` calls (lines 167, 308) with:
     `dt = latest_event_dt(project_root); now = dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "(no events)"`.

4. `shared/scripts/tools/aggregate_triage.py`
   - The `args.now or datetime.now(...)` fallback (lines 336-337) becomes
     `args.now or _resolve_now(project_root)` where `_resolve_now` calls
     the helper.
   - `--now` CLI override is preserved (used by tests + scaffold scripts).

5. `shared/scripts/tools/generate_session_handoff.py`
   - Line 370: replace the `datetime.now(...)` for the banner with the
     helper. Other internal `datetime.now()` calls (lines 136, 629 — they
     write into event-body JSON, not the rendered markdown) stay
     UNCHANGED — those are audit-relevant timestamps.

### Modify (compliance plugin — separate sys.path, can't import shared/lib)

6. `plugins/shipwright-compliance/scripts/lib/data_collector.py`
   - In `collect_all()` line 1380, replace
     `datetime.now(timezone.utc).strftime(...)` with a new local helper
     `_latest_event_ts(work_events) -> str` that returns
     `max(e.timestamp for e in work_events)` (events are already
     collected via `_read_event_log` higher up in `collect_all`).
   - When `work_events` is empty: return literal `"(no events)"`.
   - Local helper, NOT imported from `shared/scripts/lib` (per the
     existing parity pattern — see events_log.py docstring).

## Approach (Step-by-step)

1. **RED first.** Write the parametrized test
   `test_render_determinism.py` against the existing impl. Expectation:
   *fails* for every renderer because two calls separated by even
   microseconds produce different banners. Confirm RED state for all
   4 + sanity test.

2. **GREEN — helper.** Add `latest_event_dt` to `events_log.py`
   + targeted unit tests (`test_events_log.py` likely already exists;
   extend it). Independent of the renderer changes.

3. **GREEN — shared/scripts/tools (3 files).** Wire helper into each
   of the 3 renderers; each preserves its own strftime format.

4. **GREEN — compliance/data_collector.py.** Switch `collect_all()`
   timestamp source. Keep the local pattern consistent with
   `_resolve_events_path` / `_read_event_log`.

5. **Empirical end-to-end probe.** Run `finalize_iterate.py` twice in
   the worktree, separated by a real `time.sleep(2)`, diff the
   resulting 8 markdown files. Expected: zero diff. If any diff →
   missed insertion point.

## Test strategy

- **Helper unit tests** (`shared/tests/test_events_log.py` extension):
  - Empty events.jsonl → None
  - Missing events.jsonl → None
  - Single event → its ts
  - Multiple events → max ts (ISO8601 lex-max)
  - Mixed `Z`/`+00:00` suffixes → still chronologically correct max
  - Corrupt line in middle → skipped, max from valid lines
  - All-corrupt → None

- **Parametrized determinism test**
  (`shared/tests/test_render_determinism.py`):
  - For each of 4 renderer-groups: build tmp_path with synthetic
    events.jsonl, render twice with real `time.sleep(1)` between,
    assert byte-identical output.
  - Sanity test: add a new event between the two runs, assert outputs
    DIFFER (proves the determinism comes from input-dependence, not
    from the helper being broken/constant).

- **Full suite (medium safety floor):** shared/tests + compliance
  plugin tests + integration-tests.

## Alternative considered

**Sidecar JSON (Option B)** — move the timestamp out of the rendered
markdown into `*.meta.json`. Cleaner SRP but bigger diff and the
sidecar files would need their own gitignore decisions. Defer if
Option A works.

**Truncate banner to date-only** — `Updated: 2026-05-22` instead of
`Updated: 2026-05-22 18:33 UTC`. Reduces drift granularity (would
only re-render on day rollover) but loses minute-resolution info.
Rejected — full-precision determinism via event-ts is strictly better.

## Risk

- **Renderer order sensitivity:** if the helper is called BEFORE the
  iterate's F7 writes its event, the banner reflects the previous
  iterate's last event, not the current run's. That's actually correct
  — the rendered files belong to the iterate's F6 commit which is
  pre-F7. They report "data as of last committed event".

- **Worktree-vs-main events.jsonl resolution:** the helper uses
  `resolve_events_path` (worktree-aware → main repo log). Tests use
  `tmp_path` (not a git repo); the resolver falls back to
  `project_root` per its own docstring. Verified safe.

- **First-render-no-events case:** brand-new project (or test fixture
  with empty events.jsonl) renders as `"(no events)"` literal. Need
  to verify this doesn't break any F11 verifier that grep's the
  banner. `check_build_dashboard_has_run_id` keys on `run_id`, not
  on the timestamp — safe.
