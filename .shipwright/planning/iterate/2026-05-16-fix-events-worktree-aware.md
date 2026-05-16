# Iterate Spec: events.jsonl worktree-awareness + dashboard timing WARN

- **Run ID:** iterate-2026-05-16-fix-events-worktree-aware
- **Type:** bug
- **Complexity:** medium
- **Status:** implemented

## Goal
Under `/shipwright-iterate` worktree isolation, F7's `work_completed` event is
written to the ephemeral worktree's `shipwright_events.jsonl` and discarded on
`git worktree remove` — it never reaches the main repo's canonical event log.
Make the event-log producer (`record_event.py`) and the F11 verifier
(`check_events_has_commit`) resolve the log worktree-aware via
`git rev-parse --git-common-dir`, and silence the cosmetic dashboard `run_id`
WARN that fires every iterate because F5b renders the dashboard before the F6
commit SHA exists.

## Acceptance Criteria
- [x] AC-1: `record_event.py` (`read_events` + `append_event`, incl. the
      `.lock` path) resolves `shipwright_events.jsonl` via `git --git-common-dir`;
      an event recorded from inside a worktree lands in the **main** repo's log.
- [x] AC-2: `check_events_has_commit` resolves the log the same way; the F11
      verifier finds the F7 commit in the main repo's log when run from a worktree.
- [x] AC-3: Resolution logic is a single shared helper
      (`shared/scripts/lib/events_log.py::resolve_events_path`) modelled on
      `data_collector.py::_resolve_events_path`; no behavior change in a
      non-worktree (single-repo) checkout. Improves on the reference: plain
      `git rev-parse --git-common-dir` (no `--path-format=absolute` — Git
      2.31+ dependency) resolved to absolute in Python; `cwd=project_root`,
      `timeout`, no shell; emits a `warnings.warn` diagnostic when the
      git-failure fallback branch is taken (no silent data loss).
- [x] AC-4: The F0/F11 leak-guard (`worktree_isolation.py`) does not flag
      `shipwright_events.jsonl` / `shipwright_events.jsonl.lock` as a
      `main_tree_leak` — F7 writing the main log is a designed write, not a
      leak. Exemption is an EXACT root-relative match — a same-named file in
      a subdirectory is still flagged.
- [x] AC-5: the F5b dashboard render embeds the iterate `run_id` in its
      header; `check_build_dashboard_has_run_id` then passes deterministically
      via its existing `run_id in content` condition (no mtime heuristic).
      The verifier no longer WARNs on a normal iterate.
- [x] AC-6 (boundary): producer→main-log→consumer round-trip test proves an
      event written from a worktree is read back by the verifier; a parity
      test pins `resolve_events_path` to `data_collector._resolve_events_path`.
- [x] AC-7: `config.py::read_events` resolves via the shared helper — the
      F5b dashboard reads full event history inside a worktree (in scope).

## Affected FRs
- FR-01.11 (/shipwright-iterate): no normative change — internal finalization
  fix. Spec Update skipped (BUG + spec describes command behavior, not
  events.jsonl path internals).

## Out of Scope
- The ~20 other `project_root / "shipwright_events.jsonl"` read sites
  (compliance audit groups, `validate_event_log.py`, `verifiers/common.py`,
  build/adopt verifiers). They run in main-repo phases, not worktrees;
  retrofitting all of them is a separate sweep.
- `data_collector.py::_resolve_events_path` stays as-is (separate
  distributable plugin; already correct — it is the reference being mirrored).
- Changing whether `shipwright_events.jsonl` is tracked vs gitignored.

## Design Notes
n/a — no UI.

## Affected Boundaries
| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `record_event.py:append_event` | `iterate_checks.py:check_events_has_commit` | JSONL event log |
| `record_event.py:append_event` | `config.py:read_events` (dashboard) | JSONL event log |

The change is to **path resolution**, not the line format. The boundary risk
is producer/consumer *divergence*: if the producer writes the main log but a
consumer reads the worktree copy (or vice-versa), the round-trip silently
breaks. The round-trip test (AC-6) pins producer and consumer to the same
resolved path.

## Confidence Calibration
- **Boundaries touched:** producer `record_event.append_event` (writes
  JSONL) ↔ consumers `iterate_checks.check_events_has_commit` +
  `config.read_events` (read JSONL). The change is path *resolution*, not
  the JSONL line format.
- **Empirical probes run:**
  - Boundary round-trip — `append_event` from a real worktree → main log
    on disk → `check_events_has_commit` reads it back: PASS.
  - Resolver parity — shared `resolve_events_path` vs compliance
    `data_collector._resolve_events_path` agree on main/worktree/non-git
    (3 tests): PASS.
  - Two-worktree concurrent append → one main log, 50/50 events, no loss:
    PASS (the centralized-lock concern from review openai#5/gemini#3).
  - Real `git worktree` layout (not mocks) for every worktree test
    (review openai#9): PASS.
  - Git-failure edges — all four fallback branches probed: OSError +
    TimeoutExpired + empty-output + non-`.git` layout → `warnings.warn`;
    non-git dir → silent fallback (no spurious warn): PASS.
  - `GIT_DIR`/`GIT_COMMON_DIR`/`GIT_WORK_TREE` env-leak stripped from the
    git invocation so resolution stays pinned to project_root (code
    review MEDIUM): PASS.
  - Lock-file placement — `.lock` lands next to the main log: PASS.
  - Leak-guard — untracked AND tracked `events.jsonl(.lock)` exempt;
    same-named file in a subdir still flagged: PASS.
  - Drift meta-test — forward + coverage + reverse: PASS.
  - Full regression sweep — 2626 tests pass, 7 pre-existing baseline
    failures verified identical on origin/main, 0 regressions.
- **Edge cases NOT probed + why acceptable:**
  - Operator-input probe categories from `references/boundary-probes.md`
    (POSIX `export`, inline `#`, quoted `#`): N/A — `events.jsonl` is a
    machine-only append-only log, never hand-edited; and this change
    touches path *resolution*, not the line format (`read_events`
    corrupt-line tolerance is untouched).
  - Git < 2.31 + `--path-format=absolute`: deliberately removed (the fix
    for review gemini#2) — not a gap, the removal IS the mitigation.
  - A destroyed `.git` linkage inside a worktree (rev-parse returncode!=0
    from a worktree): silent fallback. Acceptable — a worktree with a
    broken gitlink is not functionally a worktree.
- **Confidence-pattern check:** no "are you confident?"→yes→bug pattern in
  this run. The external review's HIGH silent-fallback finding was a
  catch; in response I added the warn-on-fallback probes + the parity
  test. Most recent probes (parity, drift, full sweep) returned no
  findings → calibration exhausted.

## Verification (medium+)
- **Surface:** cli
- **Runner command:** `uv run --extra dev pytest shared/tests/test_events_log.py
  shared/tests/test_events_log_ssot.py shared/tests/test_verify_iterate_finalization.py
  shared/tests/test_worktree_isolation_lib.py -p no:cacheprovider`
  (single `shared/tests` package — avoids the cross-`tests/`-package
  collection collision; the boundary round-trip test inside
  `test_verify_iterate_finalization.py` drives producer `record_event`
  → main log → consumer verifier end-to-end.)
- **Evidence path:** `.shipwright/runs/iterate-2026-05-16-fix-events-worktree-aware/surface_verification.json`
