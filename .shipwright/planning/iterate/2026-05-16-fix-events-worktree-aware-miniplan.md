# Mini-Plan: events.jsonl worktree-awareness + dashboard timing WARN

- **Run ID:** iterate-2026-05-16-fix-events-worktree-aware
- **Complexity:** medium · **Type:** bug

## Approach

Extract the worktree-aware path resolver into one shared helper, wire the
event-log producer + the two iterate consumers to it, exempt the event log
from the leak-guard (a designed write, not a leak), and teach the dashboard
verifier about the F5b/F6/F7 timing window.

### Work breakdown (files)

1. **NEW `shared/scripts/lib/events_log.py`** — `resolve_events_path(project_root)
   -> Path`. SSoT for event-log resolution, modelled on
   `data_collector.py::_resolve_events_path` but hardened per external review:
   - plain `git rev-parse --git-common-dir` (NO `--path-format=absolute` —
     that flag needs Git 2.31+; older git → silent fallback). Relative output
     is resolved to absolute in Python against `project_root`.
   - subprocess hygiene: `cwd=project_root`, `timeout`, `shell=False`,
     strict single-line parse.
   - on the git-failure fallback branch, emit `warnings.warn(...)` so a
     worktree run whose git unexpectedly failed is visible, not silent
     data loss (review openai#4, HIGH).
   - fall back to `project_root / EVENT_FILE` on git failure / non-`.git`
     common dir (identity in a plain single-repo checkout).

2. **`shared/scripts/tools/record_event.py`** — add a `shared/scripts`
   sys.path bootstrap; `read_events()` and `append_event()` resolve via
   `resolve_events_path()`. `lock_path` derives from the resolved path
   (`path.with_name(path.name + ".lock")`) so the mutex sits next to the
   real log, not in the worktree.

3. **`shared/scripts/tools/verifiers/iterate_checks.py`** —
   - `check_events_has_commit`: resolve via `resolve_events_path()`.
   - `check_build_dashboard_has_run_id`: **no logic change.** Its existing
     condition 1 (`run_id in content`) becomes the deterministic pass path
     once the dashboard embeds the run_id (item 3b). Docstring updated to
     note the dashboard now carries the run_id and the F5b/F6/F7 window.

3b. **Dashboard run_id embed** (`finalize_iterate.py` + `update_build_dashboard.py`)
   — replaces the rejected mtime heuristic (review openai#7, gemini#4).
   `generate_dashboard` / `_generate_from_events` gain an optional `run_id`
   param; when set, the header emits `> Run: {run_id}`. `finalize_iterate.py`
   threads its `run_id` into `_update_dashboard`. `update_build_dashboard.py`
   `main()` gains an optional `--run-id`. When `run_id` is None (Stop hook,
   other phases) nothing changes — backward compatible. The F5b dashboard
   then deterministically contains the run_id; the F11 verifier passes via
   the existing check. No timing heuristic, no false positives.

4. **`shared/scripts/lib/worktree_isolation.py`** — leak-guard exemption.
   Add `_MAIN_TREE_WRITE_EXEMPT = ("shipwright_events.jsonl",
   "shipwright_events.jsonl.lock")`; `_scan_porcelain` skips exact matches.
   Rationale: the event log is a repo-scoped append-only journal — F7
   records into the main log post-commit by design (mirrors the existing
   `_RUN_INFRA_PREFIXES` precedent). Tracked-events repos (this monorepo)
   would otherwise fail their own F11 leak-guard.

5. **`shared/scripts/lib/config.py`** — `read_events()` resolves via
   `resolve_events_path()` (relative import — `lib` is a real package).
   In scope (approved). Without it the F5b dashboard in a gitignored-events
   worktree reads an absent log and renders with zero history. No-op
   outside a worktree.

### Test strategy

- NEW `shared/tests/test_events_log.py` — `resolve_events_path`: main repo
  (identity), inside worktree (→ main root), git-unavailable fallback.
- `test_record_event.py` — RED reproduction: event recorded with
  `--project-root <worktree>` lands in `<main>/shipwright_events.jsonl`,
  not the worktree copy; `.lock` likewise.
- `test_verify_iterate_finalization.py` — `check_events_has_commit` from a
  worktree finds a main-log commit; `check_build_dashboard_has_run_id`
  passes on a fresh dashboard lacking the commit, still WARNs when stale.
- `test_worktree_isolation_lib.py` — `detect_leak` stays clean when only
  `shipwright_events.jsonl(.lock)` changed in the main tree.
- **Boundary round-trip (AC-6):** producer (`record_event` from worktree)
  → main log on disk → consumer (`check_events_has_commit` from worktree)
  finds it. Pins producer+consumer to one resolved path.

## Alternatives considered

**Dashboard WARN — re-render between F7 and F11** (the other option in the
brief). Rejected: re-rendering after F6 leaves `build_dashboard.md` dirty
in the worktree post-commit; the change is never in the PR (F6 already
committed) and is discarded — pure churn fighting the single-atomic-F6 design.

**Dashboard WARN — mtime ≤600s freshness heuristic in the verifier**
(original plan). Rejected after external review (openai#7, gemini#4):
brittle to clock skew, coarse mtime resolution, slow CI, and unrelated
touches. Replaced by the deterministic run_id embed (item 3b) — the
verifier's existing `run_id in content` check then passes with no heuristic.

**Stale-lock bypass for the centralized `.lock`** (gemini#3). Rejected:
`_FileLock` uses OS advisory locks (`fcntl.flock` / `msvcrt.locking`),
released by the OS on process exit/crash — no persistent deadlock is
possible. Adding PID/age logic to a working crash-safe lock is gold-plating.
Covered instead by a two-worktree concurrent-append test + ADR note.

## Out of scope
See iterate spec "Out of Scope". The other ~20 event-log read sites are a
separate sweep; `data_collector.py` is the reference, left as-is.
