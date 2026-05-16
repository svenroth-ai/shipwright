# Iterate Spec: iterate-worktree-isolation

- **Run ID:** iterate-2026-05-15-iterate-worktree-isolation
- **Type:** change
- **Complexity:** large (escape-hatch Option 2 — force iterate; user-acknowledged over-threshold scope)
- **Status:** implemented

## Goal

Make `/shipwright-iterate` worktree-isolation **unconditional and structural**:
every iterate run, always, in its own worktree + branch + PR — not a detected,
opt-in "Parallel" mode. Remove the primary/secondary/canonical session-role
machinery (a workaround for the missing unconditional isolation) and eliminate
the parallel-iterate merge/race hotspots (stale branch base, shared-tree
finalize, ADR-number collision).

## Acceptance Criteria

- [x] **AC-1** — Invoked from the main repo, the worktree-setup step
  unconditionally creates `.worktrees/<slug>/` + branch `iterate/<slug>` whose
  base equals freshly-fetched `origin/<default>` HEAD. No menu, no
  run-detection precondition. *(test_setup: creates_worktree_and_branch,
  branch_base_is_fresh_origin_default)*
- [x] **AC-2** — Invoked with cwd already inside a `.worktrees/<slug>/`, the
  setup step creates no new worktree (`action: noop`); `{project_root}` = cwd.
  *(test_setup: noop_inside_worktree)*
- [x] **AC-3** — Slug collision (worktree dir OR `iterate/<slug>` branch
  exists) → setup exits 2 with an actionable message; no partial worktree.
  *(test_setup: collision_branch_exists, collision_worktree_exists)*
- [x] **AC-4** — `git fetch origin` failure → setup exits 3 (hard-fail); with
  `SHIPWRIGHT_ITERATE_NO_FETCH=1` it warns and branches from the local
  `origin/<default>` ref. *(test_setup: fetch_failure_hard_fails,
  fetch_failure_override_continues)*
- [x] **AC-5** — The leak-guard exits non-zero when `{project_root}` does not
  resolve under `.worktrees/`; exits 0 when it does. *(test_check:
  blocks_when_run_in_main_repo, allows_clean_isolated_worktree)*
- [x] **AC-6** — The leak-guard exits non-zero when the main repo working tree
  carries uncommitted entries not in the Step-1 snapshot; exits 0 when only
  pre-existing snapshot entries are dirty. *(test_check: blocks_on_main_tree_leak,
  tolerates_preexisting_main_tree_dirt)*
- [x] **AC-7** — `detect_parallel_sessions.py`, `write_session_role.py`,
  `check_session_role.py`, `lib/session_role.py` and their three test files
  deleted; a repo grep for `session_role`/`detect_parallel_sessions` in `*.py`
  + `*.json` returns zero live-code references.
- [x] **AC-8** — SKILL.md no longer contains B1c, the B1 "Parallel" option,
  the primary/secondary/canonical role prompt, or the F11 role check.
- [x] **AC-9** — F11 performs `git push origin iterate/<slug>` + `gh pr create`
  and contains no `git checkout <main>` / `git merge iterate/`.
- [x] **AC-10** — F4 changelog-drop pattern verified intact (no regression).
- [x] **AC-11** — F5c file-per-iterate verified intact (no regression).
- [x] **AC-12** — F3 writes a run-id-keyed decision-drop; `aggregate_decisions.py`
  assigns sequential `ADR-NNN` at the one serialized point. *(test_aggregate:
  aggregates_drops, numbering_starts_at_one, dry_run; test_write_decision_drop:
  two_drops_distinct_counters)*
- [x] **AC-13** — Every git/file/test op in SKILL.md + iterate tool scripts is
  `{project_root}`-rooted (`git -C`, absolute paths); `gh pr create` runs with
  cwd explicitly `cd`'d into the worktree.
- [x] **AC-14** — `integration-tests/test_parallel_iterate_isolation.py` drives
  two parallel worktree setups: own worktree+branch, no cross-tree write, clean
  main tree, slug-collision rejected, leak caught. *(6 tests)*

(AC-15, raised at the approval gate: `iterate_stop_finalize.py` made
worktree-aware via the run pointer — Phase 5.)

## Affected FRs

- `FR-01.11 — /shipwright-iterate` (`.shipwright/planning/01-adopted/spec.md`)
  is the owning FR. It is broad ("complexity-adaptive SDLC for ongoing
  changes") and its acceptance criteria are `TBD` placeholders, so no
  normative FR text changed. The iterate spec + ADR are the normative record
  for the worktree-isolation mechanics (degraded-mode: adopted project, FR
  ACs not yet enumerated).

## Out of Scope

- webui code (`.shipwright-webui/` stays pure UI — zero process logic).
- node_modules / .venv sharing between worktrees — rehydration accepted.
- Auto-merging this run's PR — this run stops at PR opened (user decision).
- Anything beyond scope items A–H + the AC-15 consequence.

## Affected Boundaries

`touches_io_boundary` fired. New serialized formats + producer/consumer pairs:

| Producer (writes) | Consumer (reads) | Format |
|---|---|---|
| `setup_iterate_worktree.py` `write_snapshot` | `check_iterate_isolation.py` `detect_leak` | `main_tree_snapshot.json` |
| `setup_iterate_worktree.py` `write_run_pointer` | `iterate_stop_finalize.py` `_active_worktree_root` | run pointer JSON |
| `write_decision_drop.py` | `aggregate_decisions.py` + verifier `check_adr_in_iterate_history` | decision-drop JSON |
| `setup_iterate_worktree.py` (stdout) | SKILL.md B1a `{project_root}` rebind | JSON contract |

## Confidence Calibration

- **Boundaries touched:** the four producer/consumer pairs above.
- **Empirical probes run:**
  - snapshot JSON producer→file→consumer round-trip — `test_snapshot_round_trip`, `test_detect_leak_*` (clean / new-path / pre-existing).
  - decision-drop JSON round-trip through the aggregator — `test_aggregate_decisions` (numbering, dry-run, malformed, authoring-date, architecture-impact).
  - run pointer round-trip — `test_run_pointer_round_trip`, `test_prune_stale_run_pointers`.
  - worktree detection from a main repo AND a nested worktree — `test_is_worktree_*`, `test_main_repo_root_from_worktree`.
  - slug-collision (branch + worktree) — `test_collision_*` → exit 2, no partial state.
  - fetch-failure with and without the offline override — `test_fetch_failure_*`.
  - git porcelain directory-collapsing edge case (untracked `.shipwright/`) — `test_main_tree_status_paths_expands_untracked_shipwright` (added after review M3).
  - two simulated parallel iterate runs — `integration-tests/test_parallel_iterate_isolation.py` (6 probes incl. no-cross-tree-write + clean main tree + leak caught).
  - noop-from-worktree leaves a usable leak-guard baseline — `test_noop_inside_worktree_ensures_pointer_and_snapshot` (added after review M1).
- **Edge cases NOT probed + why acceptable:** real network `git fetch`
  failures (simulated via a bogus origin URL — the failure path is
  URL-agnostic); concurrent `aggregate_decisions` runs (the file_lock +
  snapshot-under-lock makes the second run's already-deleted drops degrade to
  recorded `errors[]`, reasoned not probed); the leak-guard against a repo
  with NO git at all (the guard reports `not_a_git_repo` — covered by the
  GitError path, not a separate test).
- **Confidence-pattern check:** the code review explicitly asked "do the
  invariants hold?" — it produced findings (M1–M3, L1–L4). All 7 were fixed
  and one further probe ran afterward (the 128-test re-run) with no new
  finding. Stopping rule satisfied: most recent probe clean, all applicable
  categories covered, no unresolved yes-then-bug pattern.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run --extra dev pytest shared/tests/ shared/scripts/tests/ shared/scripts/tools/tests/ plugins/shipwright-iterate/tests/ integration-tests/` (run per-suite — `shared/scripts/tests` and `plugins/*/tests` are separate `tests` packages and cannot co-collect).
- **Evidence:** 2282 passing across the suites + 0 regressions; the only 7
  failures (`test_hooks.py` secrets/filesize, `test_artifact_path_canon`)
  reproduce identically on the base `origin/main` and are pre-existing,
  unrelated baseline failures.
- **Justification (surface≠none):** the iterate skill has no startable
  web/api surface; correctness is empirically driven through pytest over the
  new scripts, the leak-guard, and the two-parallel-runs integration test.
