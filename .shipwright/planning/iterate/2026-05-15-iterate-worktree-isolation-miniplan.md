# Mini-Plan: iterate-worktree-isolation

- **Run ID:** iterate-2026-05-15-iterate-worktree-isolation
- **Spec:** `.shipwright/planning/iterate/2026-05-15-iterate-worktree-isolation.md`
- **Complexity:** large (escape-hatch Option 2 — force iterate)

## Approach

Eight scope items (A–H). F + G are verify-only (already implemented). The
remaining work is built in TDD phases, tests-first per phase. One atomic commit
at F6. This run finalizes via push + `gh pr create` (stops at PR opened).

## Key design decisions (made during planning — flag for review)

1. **Worktree-setup script** `shared/scripts/tools/setup_iterate_worktree.py`.
   Detects main-vs-worktree via `git rev-parse --git-common-dir` ≠ `--git-dir`.
   In main repo: `git fetch origin` (hard-fail unless `SHIPWRIGHT_ITERATE_NO_FETCH=1`)
   → `git worktree add .worktrees/<slug> -b iterate/<slug> origin/<default>` →
   prints the worktree absolute path on stdout (the skill's `{project_root}`
   rebind value). In a worktree: no-op, prints cwd. Slug collision → exit 2,
   no partial state. Also writes the **run pointer** + **main-tree snapshot**
   (see #4).
2. **Leak-guard** `shared/scripts/checks/check_iterate_isolation.py`.
   Called at F0 and F11. Exits non-zero if `{project_root}` is not under
   `.worktrees/`, OR if the main repo working tree has uncommitted entries
   absent from the Step-1 snapshot (snapshot-and-diff attribution — Q3 answer).
3. **H — decision-drop pattern (two new scripts, `write_decision_log.py`
   left untouched for non-iterate phases).** Non-iterate phases (build, plan)
   don't run in parallel worktrees, so their `write_decision_log.py` max+1 is
   race-free and stays. Iterate F3 switches to a new
   `shared/scripts/tools/write_decision_drop.py` → writes
   `.shipwright/agent_docs/decision-drops/<run-id>_NNN.md` (run-id identity,
   no number). New `shared/scripts/tools/aggregate_decisions.py` (mirrors
   `aggregate_changelog.py`) assigns sequential `ADR-NNN` continuing from
   `decision_log.md` max, folds drops in, deletes processed drops — invoked
   from `/shipwright-changelog` Step 4. `verifiers/iterate_checks.py`
   `check_adr_in_iterate_history` updated: when the entry `adr` field is a
   run-id (not `ADR-NNN`), verify the decision-drop file exists instead of
   grepping `decision_log.md`.
4. **Stop-hook worktree-awareness (AC-15).** `iterate_stop_finalize.py`'s
   fallback finalizer currently resolves the project root from cwd — which,
   per the invariant, stays at the **main repo**. Left alone it would write
   `session_handoff.md` into the main tree → the leak-guard would then reject
   the run. Fix: `setup_iterate_worktree.py` writes a main-repo run pointer
   `.shipwright/iterate_active.json` `{run_id, worktree_path, branch}`;
   `iterate_stop_finalize.py` reads it and finalizes the worktree, not the
   main repo. Also fixes its brittle `parents[4]` shared-scripts import.
5. **Transient-file homes + gitignore.** Snapshot + run pointer live in the
   **main repo** `.shipwright/` (the leak-guard resolves it via
   `--git-common-dir`): `.shipwright/runs/<run-id>/main_tree_snapshot.json`
   and `.shipwright/iterate_active.json`. Add `/.shipwright/runs/` and
   `/.shipwright/iterate_active.json` to `.gitignore` so they are never
   tracked drift (today `.shipwright/runs/` is untracked-but-not-ignored).
6. **SKILL-structure tests updated in the same diff** (Test-Update-Klausel).
   `test_skill_phase_matrix.py`, `test_skill_step_6_rules_present.py`,
   `test_hooks_json_registration.py`, `test_iteration_reviews_section_8.py`,
   `test_skill_risk_taxonomy_consistency.py`, `test_skill_e2e_gate_consistency.py`
   are re-run and updated for the B1/B1c/F11 changes.

## Build phases (TDD — tests first per phase)

### Phase 1 — Mechanism scripts
- `setup_iterate_worktree.py` + `tests/test_setup_iterate_worktree.py`
  (AC-1,2,3,4 + pointer/snapshot writes).
- `check_iterate_isolation.py` + `tests/test_check_iterate_isolation.py`
  (AC-5,6).

### Phase 2 — H: decision-drop + aggregator
- `write_decision_drop.py` + test (run-id ADR drop).
- `aggregate_decisions.py` + test (NNN assignment, fold-in, cleanup).
- `verifiers/iterate_checks.py` `check_adr_in_iterate_history` — run-id-aware.
- Wire `aggregate_decisions.py` into
  `plugins/shipwright-changelog/skills/changelog/SKILL.md` Step 4.

### Phase 3 — Delete role machinery (D)
- Delete `detect_parallel_sessions.py`, `write_session_role.py`,
  `check_session_role.py`, `lib/session_role.py` + 3 test files.
- `data_collector.py` L918 — drop the `session_role` docstring sentence.
- Grep-verify: only historical artifacts remain (AC-7).

### Phase 4 — SKILL.md + references surgery (A,B,C,D,E,H)
- New First-Actions section **"Worktree Isolation (unconditional)"** —
  detect/fetch/create/rebind. Placed after B1, integrated with resume.
- B1 — drop "Parallel" option; rework Resume to cd into the existing
  worktree; drop "Complete" cross-tree-merge wording.
- Delete B1c entirely; delete the "Session roles" blockquote; rewrite B1a
  (parallel conventions become the normal flow; remove the merge-hotspot
  WARNINGs — now fixed).
- B2 — `{project_root}`-root the reads.
- Path A Step 6 / Path C Step 5 — drop `git checkout -b` (branch exists
  from the worktree step).
- F0 — add the leak-guard call.
- F3 — switch to `write_decision_drop.py`; ADR identity = run-id.
- F5c / F7 / summary — ADR identity = run-id.
- F11 — remove role check + `checkout main; merge; push origin main`; add
  leak-guard + `git push origin iterate/<slug>` + `gh pr create`; rebase
  guidance against current `origin/<default>`.
- `{project_root}` audit pass over the whole file (B): no `cd <subdir>`,
  `git -C`, absolute paths.
- references — `iteration-reviews.md` handoff section worktree-aware.

### Phase 5 — Iterate tool-script audit (B + AC-15)
- `iterate_stop_finalize.py` — worktree-aware via the run pointer; fix
  `parents[4]`.
- `campaign_*.py`, `classify_*.py` — confirmed path-clean by inventory;
  light touch only if a `{project_root}` gap surfaces.

### Phase 6 — Integration test (AC-14)
- `integration-tests/test_parallel_iterate_isolation.py` — two simulated
  parallel worktree setups; assert own-worktree/own-branch, no cross-tree
  write, clean main tree, slug-collision rejection.

### Phase 7 — Docs + SKILL-structure tests
- `docs/hooks-and-pipeline.md` (mandated — hooks/scripts changed).
- `docs/guide.md` — "Parallel Development with Worktrees" chapter.
- Update the 6 SKILL-structure tests (decision #6).
- `.gitignore` — add the two transient-file lines (decision #5).

### Phase 8 — Finalization F0–F12
- F0 (full `uv run pytest`) + F0.5 (surface=cli) + leak-guard.
- F1–F5c, F6 single atomic commit.
- F7 event, F11 → push branch + `gh pr create` (STOP at PR opened).

## Test strategy

- Per-phase pytest, tests-first.
- F0: `uv run pytest shared/scripts/tests/ shared/tests/
  plugins/shipwright-iterate/tests/ integration-tests/ -q` (full suite).
- F0.5 surface=cli: `surface_verification.py` over the new script tests +
  the integration test.
- Boundary Probe (Step 6a): round-trip the snapshot JSON and the
  decision-drop format (producer→file→consumer).

## Alternative considered (rejected)

**H via `write_decision_log.py` run-id headings + a merge-time renumber
hook.** Rejected: a git merge hook is launcher/infra logic (violates the
"logic only in skill + tool scripts" invariant) and can't be unit-tested
deterministically. The decision-drop + changelog-time aggregation mirrors
the already-proven F4 changelog-drop pattern and keeps the serialized
point inside an existing skill step.

## Out of scope

webui code; node_modules/.venv sharing; CI producer; auto-merging this
run's PR. Anything beyond A–H + the AC-15 consequence.
