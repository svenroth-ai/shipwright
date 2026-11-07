# Mini-plan S8: full integration, benchmark, rollback rehearsals (issue 978)

1. `integration-tests/test_events_drops_full_system.py`: bare origin + worktrees, real record_event / ensure_current / fold_events / integrity and layout CI checks, flip by config only. Scenarios: campaign wave + retried unit + squash sequence, old writer / PR in flight at the flip / mid-run flip, mid-run rollback (emergency then full fold), quarantine of a torn drop, mixed versions through the CLI, fault injection, two run ids in one shared worktree, stacked base.
2. `test_events_drops_benchmark.py`: real legacy log + 300 drops; run-scoped read, whole-log read, per-write cost; generous CI bounds, strict with SHIPWRIGHT_BENCH_STRICT=1, numbers to GITHUB_STEP_SUMMARY.
3. `test_events_drops_rollback_rehearsal.py`: copy of the real log split into drops; emergency fold and full fold through the CLI; equality of the event multiset, finalized_run_ids, latest_event_dt; real log hashed before/after.
4. Fixes the rehearsals force: `fold_events --stage` in chunks (WinError 206 at ~1000 drops); `check_layout_ci` judges a head on drops per commit (layout at first parent) so a PR that merged main in is not blamed for pre-flip appends; `\Z` in three name regexes.
5. Flip-readiness note with preconditions and the follow-up list.

Risks: tests that read the live tracked log; benchmark timing on shared runners (10x bounds).
