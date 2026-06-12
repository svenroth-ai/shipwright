# Iterate Spec — Relocate `resolve_main_repo_root` to its thematic home

- **Run-ID:** `iterate-2026-06-12-repo-root-resolver-relocate`
- **Intent:** CHANGE (refactor — module relocation, no behavior change)
- **Complexity:** medium (overridden up from the classifier's `small`)
- **Spec Impact:** NONE (no FR/spec change — internal Python library reorganization)
- **Architecture-impact:** none (no new component/route/surface; a shared primitive
  changes home module only)

## Problem (Think-Before-Coding)

`shared/scripts/lib/events_log.py` hosts `resolve_main_repo_root` — a generic
`git rev-parse --git-common-dir` MAIN-repo-root primitive. Its own docstring
admits it is *"no longer used to locate the event log"*: every real consumer is a
**repo-root** consumer (the decision-drop resolvers, the F11 verifier, the
plugin-sync Stop hook, the compliance Group-F detective), not an event-log one.
It is squatting in the event-log module. The thematic home for a "resolve the main
repo root, fail-soft" helper is `shared/scripts/lib/repo_root.py`, which already
hosts the sibling `main_repo_root_or`.

This was surfaced by the H1 bloat dogfood on `events_log.py` (323 LOC) and tracked
as a follow-up (memory `trg-b9acb195`, "3 repo-root resolvers"). It was explicitly
carved out of the bloat-cleanup campaign as needing its own iterate because it
**reverses the documented 2026-05-29 keep-in-place decision** (decision_log.md
entries at the `iterate-2026-05-29-events-jsonl-worktree-commit` ADR).

## Decision & alternatives considered

**Chosen — move the implementation into `lib/repo_root.py`; re-export from
`events_log` for back-compat; migrate the direct `lib.*` consumers + their tests.**
The re-export keeps `from lib.events_log import resolve_main_repo_root` working for
any caller we do not migrate (notably the compliance Group-F detective, which
reaches shared libs through a cross-plugin `load_shared_lib` bootstrap and already
loads `events_log`).

- **Alternative A — leave it in `events_log.py` (status quo).** Rejected: the
  function is thematically misplaced, the docstring already concedes it; the
  squat is exactly what the bloat dogfood flagged.
- **Alternative B — unify all three resolvers (`worktree_isolation.main_repo_root`
  raises, `repo_root.main_repo_root_or` → fallback, `events_log.resolve_main_repo_root`
  → `None`) into one.** Rejected (out of scope): the three have *deliberately
  different* failure contracts. Collapsing them is a larger design change; this
  iterate only relocates #3 to sit beside #2 in the same module.
- **Alternative C — true module-level re-export (`from lib.repo_root import
  resolve_main_repo_root` in `events_log.py`).** Rejected: it creates an import
  cycle `events_log → repo_root → worktree_isolation → events_log` (worktree_isolation
  imports `events_log.EVENT_FILE`). Under any import order where `repo_root` or
  `worktree_isolation` loads first, the partially-initialized `repo_root` raises
  `ImportError`. The chosen shim does a **lazy** (call-time) `from lib.repo_root
  import …`, which sidesteps the cycle in every order, including the
  `load_shared_lib` bootstrap path.

## Surgical scope (the diff)

**Source (behavior-preserving relocation):**
1. `lib/repo_root.py` — add `resolve_main_repo_root` (verbatim body incl. the
   WP7/F27 UTF-8 + mojibake guard, the `GIT_DIR`/`GIT_COMMON_DIR`/`GIT_WORK_TREE`
   discovery-override stripping, and the warn-vs-silent-`None` diagnostics) +
   its `_git_env` helper + the two module constants. Rewrite the module docstring
   to cover both helpers.
2. `lib/events_log.py` — replace the function with a thin **lazy** back-compat
   shim; drop the now-unused `os` / `subprocess` / `warnings` imports + the two
   constants; rewrite the *"resolve_main_repo_root stays"* docstring section to
   *"relocated to lib/repo_root.py"*.

**Consumer migration (`from lib.events_log` → `from lib.repo_root`, all net-zero
line changes):**
3. `tools/write_decision_drop.py` (244 LOC)
4. `tools/aggregate_decisions.py` (298 LOC)
5. `hooks/plugin_sync_reminder_on_stop.py` (local import inside `_emit_triage`)

**Deliberately NOT migrated — kept on the back-compat re-export:**
- `tools/verifiers/iterate_checks.py` (1140 LOC, grandfathered) and
  `plugins/shipwright-compliance/.../audit/group_f.py` (395 LOC, grandfathered) —
  **anti-ratchet:** both are already-oversized grandfathered files. Migrating
  `iterate_checks` means splitting one combined `from lib.events_log import …`
  line into two (+1 LOC); `group_f` would need an explanatory line — either
  ratchets a grandfathered file past its baseline (a hard CI gate). Growing two
  *other* oversized files to achieve a cosmetic import change is the opposite of
  this iterate's bloat-reduction intent, so they stay on the documented
  back-compat re-export (net-zero diff). The `events_log` shim docstring records
  why. (`group_f` also reaches the symbol through `load_shared_lib("events_log")`,
  so the re-export avoids a second bootstrap of `repo_root`'s `worktree_isolation`
  chain regardless.)
- `tools/commit_event_followup.py` — has its **own** local `resolve_main_repo_root`
  (`-> Path`, different contract, legacy F7b path). Out of scope.
- `lib/architecture_doc.py` — docstring-only mention; updated for accuracy, no code.

**Tests:**
7. New `shared/tests/test_repo_root.py` — the six `resolve_main_repo_root` behavior
   tests move here, importing from `lib.repo_root`.
8. `shared/tests/test_events_log.py` — drop those six + the now-unused `pytest`
   import; add one back-compat test proving `from lib.events_log import
   resolve_main_repo_root` still works and equals the `lib.repo_root` answer.
9. `shared/tests/test_git_tools_utf8.py` — import from `lib.repo_root`; fix docstring.
10. `shared/tests/test_architecture_md_reflects_arch_impact.py` — split import.
11. `shared/tests/test_decision_drop_ssot.py` — update assertion-message/docstring
    prose (`events_log.` → `repo_root.`); the literal-string grep is unaffected
    (consumers still call `resolve_main_repo_root`).

**Docs:** `docs/hooks-and-pipeline.md` (the resolver line) — note the new home.

## Constraints respected
- `test_decision_drop_ssot.py` greps the literal `resolve_main_repo_root` in
  consumer sources — still present post-migration (call sites unchanged in name).
- Import-cycle hazard navigated via the lazy shim (Alternative C rationale).
- Reverses the 2026-05-29 keep-in-place decision → new F3 decision-drop records
  the reversal; the append-only decision_log.md history is left intact.
- `events_log.py` drops to ~223 LOC (a free bloat win below the 300 limit);
  baseline tightening/removal is left to the bloat-cleanup campaign (the documented
  owner of baseline edits) — reductions never trip the anti-ratchet.

## Confidence Calibration
- **Boundaries touched:** `git rev-parse` subprocess boundary (the relocated
  function shells out); Python import graph (`events_log` ↔ `repo_root` ↔
  `worktree_isolation`) and the compliance `load_shared_lib` cross-plugin bootstrap.
  No `.env` / config / serialization boundary. `touches_io_boundary` not flagged.
- **Empirical probes run:** (1) Import-cycle — imported `events_log`, `repo_root`,
  `worktree_isolation` in all four first-import orders (incl. the `from`-import that
  historically breaks) → no `ImportError`; the worktree correctly resolved to the
  MAIN root. (2) Byte-identical behavior — `test_repo_root.py` (6) +
  `test_git_tools_utf8.py` F27 (3) green against REAL git worktrees. (3) Back-compat —
  `from lib.events_log import resolve_main_repo_root` resolves *equal* to
  `lib.repo_root` (test_events_log back-compat test). (4) Cross-plugin bootstrap —
  compliance Group-F via `load_shared_lib("events_log").resolve_main_repo_root`
  (test_audit_groups_c_f.py, 46 compliance tests). (5) Anti-ratchet — authoritative
  `classify_entries` reports **0 ratchets** (events_log 323→220, both grandfathered
  consumers net-zero). (6) Full shared suite **3290 passed / 12 skipped**;
  leak-guard ALLOW; ruff clean; agent-doc 600-char gate 11/11.
- **Test Completeness Ledger:** 7 behaviors, all `tested` with cited evidence,
  0 untestable, 0 untested-testable (machine-readable block in
  `shipwright_test_results.json.iterate_latest.test_completeness`).
- **Confidence-pattern check:** depth — the load-bearing risks were the import
  cycle and the cross-plugin bootstrap; both exercised empirically (4 orders +
  the compliance suite), not asserted. Breadth — all consumers + test files
  enumerated via repo-wide grep; no source file left on a stale `events_log`
  import except the two grandfathered files deliberately kept on the re-export.
