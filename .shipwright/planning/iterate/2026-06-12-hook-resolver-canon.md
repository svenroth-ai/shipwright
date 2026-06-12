# Iterate Spec — a1-2 (WP5): hook project-root / worktree resolvers + project guard

**Run ID:** `iterate-2026-06-12-hook-resolver-canon`
**Campaign:** `2026-06-10-audit-1-auto` · **Sub-iterate:** a1-2
**Intent:** CHANGE (tooling / hook contracts) · **Complexity:** medium
**Spec impact:** none (framework hooks, no FR)
**Risk flags:** `touches_shared_infra`, `touches_io_boundary`

## Problem (WP5 of the 2026-06-10 deep audit)

Five hooks resolve the project root wrongly or skip the Shipwright-project guard:

- **F5 (MED):** the two compliance PreToolUse gates (`check_rtm_coverage.py`,
  `check_security_scan.py`) do `project_root = os.getcwd()`. Hooks fire with
  cwd = workspace root, which in a subdirectory-project layout is one level
  ABOVE the managed project → the gate finds no RTM and silently fails open.
- **F6 (MED):** `mark_plugin_edit.is_plugin_side()` tests `rel.startswith("plugins/")`
  / `"shared/"`, but worktree edits relativize to `.worktrees/<slug>/plugins/…`
  (hooks run with cwd = MAIN root) → False → the plugin-cache-sync reminder
  never fires for the dominant (worktree) edit path. The sibling
  `check_file_size.py` got the prefix-strip (ADR-126); this one did not.
- **F7 (MED):** `check_drift._emit_drift_to_triage` has no `_is_shipwright_project`
  guard → opening a foreign repo with a stale `CLAUDE.md` writes
  `.shipwright/triage.jsonl` into a tree the framework isn't installed in.
- **F8 (MED):** the content-drift dedup key embeds the ABSOLUTE root of whatever
  tree the session started in → a drift recorded from main is keyed to the main
  root; a later worktree session computes a worktree-rooted key, finds the old
  one absent, and machine-dismisses the still-present drift.
- **F10 (LOW):** the toolcall-counter producer (`track_tool_calls.py`) writes via
  `resolve_project_root()` (auto-descends), but the readers
  (`estimate_context_pressure.py`, `reset_tool_counter.py`) used env-or-cwd → in
  an auto-descent layout they read a counter file that never exists → count 0 →
  context-pressure checkpointing silently dead.

## Acceptance Criteria

- **AC-1** Each hook resolves correctly in subdirectory + worktree + foreign-repo
  layouts (unit tests).
- **AC-2** `check_drift` no-ops (writes nothing) in a non-Shipwright dir.
- **AC-3** Full F0 suite green; no new bloat crossing.

## Plan

- **F5:** add `_resolve_project_root()` to both compliance gates — bootstrap
  `shared/scripts` onto `sys.path` (depth `parents[4]`), import
  `lib.project_root.resolve_project_root`, fall back to env/cwd on
  ImportError/ValueError. Swap the two `os.getcwd()` call sites.
- **F6:** `mark_plugin_edit._strip_worktree_prefix()` reuses
  `bloat_baseline.strip_worktree_prefix` (local regex fallback); `is_plugin_side`
  strips before the `startswith` tests.
- **F7:** `check_drift._is_shipwright_project()` (shared predicate + marker
  fallback); `_emit_drift_to_triage` returns 0 + writes nothing when False.
- **F8:** `_canonical_anchor(anchor, project_root)` + `_content_anchor(finding,
  project_root)` make the key repo-relative (absolute anchors `relative_to(root)`;
  relative anchors kept verbatim; residual `.worktrees/<slug>/` stripped;
  `normcase` folds drive-letter case). Both call sites updated.
- **F10:** `_resolve_project_root()` in both counter readers mirrors the producer's
  `resolve_project_root()` auto-descent; explicit absolute `--counter-file` and
  `SHIPWRIGHT_PROJECT_ROOT` still win.

## Affected Boundaries (ADR-024)

| Boundary | Direction | Round-trip |
|---|---|---|
| `.shipwright/compliance/traceability-matrix.md` | consumer (read) | resolver finds RTM in subdir/env/foreign layouts |
| `.shipwright/locks/plugin_edit_pending.<sid>.json` | producer (write) | worktree-prefixed rel ↔ is_plugin_side classification |
| `.shipwright/triage.jsonl` | producer (write) | F7 guard: write iff Shipwright project; F8 key stable main↔worktree |
| `.shipwright/toolcall_count` | producer writes / readers read | producer `resolve_project_root` ↔ readers `resolve_project_root` (same file) |

## External-Plan-Review-Findings

OpenRouter (gemini + openai). High/medium findings + dispositions:

| # | Sev | Finding | Disposition |
|---|---|---|---|
| G1 | HIGH | F8 `relative_to(root)` raises ValueError for an anchor outside the root → crash | **accepted-and-fixed** — `_canonical_anchor` wraps `relative_to` in `try/except ValueError` → falls back to the normalized full posix path. New test `test_absolute_anchor_outside_root_does_not_crash`. |
| O5 | MED | Define behavior for absolute anchors outside root | **accepted-and-fixed** — same as G1; explicit test added. |
| O4/G4 | MED/LOW | Worktree strip must be `^`-anchored + separator/`./`-robust | **accepted-already-met** — fallback regex is `^\.worktrees/[^/]+/`; `is_plugin_side` normalizes `\`→`/`, strips leading `/`; shared `strip_worktree_prefix` collapses `./`. Tests cover backslash + `shared/` worktree paths. |
| O6 | MED | Legacy absolute-key triage items won't dedup against new repo-relative keys → one-time effect | **accepted-already-covered** — the resolve pass dismisses the stale legacy item (existing `test_check_drift_legacy_noncanonical_item_resolved_on_recanon`); the migration is the intended one-time dismissal, not unbounded duplicates. |
| O9/O11 | MED | Counter-reader precedence + env-override tests | **accepted-already-met** — `test_explicit_counter_file_arg_wins` (absolute file), `test_env_var_root_wins` (env), `test_estimate_reads_subproject_counter` (resolver); RTM gate `test_rtm_gate_resolves_via_env_var` + `test_foreign_repo_no_marker_allows`. |
| O2/G2 | MED | Fail-open fallback to env/cwd on ImportError may reintroduce fail-open | **rejected-with-reason** — the fallback only triggers on a resolver IMPORT failure (not a resolution miss); resolver-first is strictly better than the prior unconditional `os.getcwd()`. Matches the established codebase pattern (`track_tool_calls`, `mark_plugin_edit`, `audit_detector`). |
| O1/O3/G3/O7/O12 | MED/LOW | Centralize the `parents[N]`/`sys.path` bootstrap + project-guard into one shared helper instead of per-hook replication | **rejected-with-reason (scoped follow-up)** — the per-hook `parents[N]`+`sys.path.insert`+ImportError-fallback is the canonical pattern every shared hook already uses; centralizing it touches all hooks and is out of WP5 scope. The guard already prefers `lib.project_root._is_shipwright_project` (shared predicate) with a marker fallback. `normcase` (O12) preserves the legacy key's exact folding — changing it would itself be a migration. Follow-up: a `shared/scripts/lib/hook_bootstrap.py` helper. |
| O8 | LOW | `_emit_drift_to_triage` returning 0 on skip is ambiguous vs "0 appended" | **rejected-with-reason** — 0 is the existing contract (count of NEW items); callers only use it for a debug count and never branch on skip-vs-empty. F7 is verified by the absence of `.shipwright/` (test asserts the dir is not created), which is unambiguous. |

## External-Code-Review-Findings

Internal reviewer cascade (spec-reviewer HARD-GATE → code-reviewer →
doubt-reviewer): **delegated_to_orchestrator** (runner has no Agent tool).
External LLM code review (OpenRouter gemini + openai):

| # | Sev | Finding | Disposition |
|---|---|---|---|
| O1 | MED | "No tests in diff" — AC1/AC2 unverified | **rejected-with-reason** — false alarm: the reviewer was handed the source-only diff (test files excluded). 19 WP5 + 4 F5 + 6 updated drift-emit tests exist and pass. |
| O2 | MED | F8 worktree-root edge: if `project_root` IS a worktree root, keys might still diverge | **rejected-with-reason** — `test_dedup_key_stable_across_trees` proves main root `tmp/main` and worktree root `tmp/.worktrees/slug` yield the identical key `drift:claude.md:content`. Relativizing to whichever resolved root produces the same repo-relative tail. |
| O3 | MED | F7 guard skips the resolve pass → stale items in a now-foreign dir never auto-resolved | **rejected-with-reason** — by design: a non-Shipwright dir must not be read/written by this hook at all (F7's whole point). If a dir genuinely is Shipwright-managed the markers are present and the resolve pass runs. Verified by `test_no_triage_written_in_foreign_dir` (no `.shipwright/` created). |
| GEM | MED | Are `:timestamp` keys also tree-stable, or do they carry absolute paths? | **accepted-investigated-and-tested** — `check_timestamp_drift` emits BARE names from fixed `KEY_FILES`/`KEY_DIRS` (never absolute), so timestamp keys were already tree-independent; F8 correctly scoped to `:content`. New regression test `test_timestamp_keys_are_tree_independent` makes this empirical. |

Net: 0 code changes required from the external review; 1 confirmatory regression
test added (timestamp-key stability).

## Self-Review

7-item checklist (all PASS):

1. **Spec Compliance** — PASS. All five findings (F5/F6/F7/F8/F10) fixed in the
   six named files; AC-1 (subdir/worktree/foreign tests), AC-2 (foreign-dir
   no-op) covered; AC-3 verified in F0.
2. **Error Handling** — PASS. Every resolver import is `try/except
   (ImportError, ValueError)` → env/cwd fallback; `_canonical_anchor`
   `try/except (OSError, ValueError)` (+ the inner `relative_to` ValueError
   guard for outside-root anchors); `_emit_drift_to_triage` keeps its
   always-exit-0 best-effort contract.
3. **Security Basics** — PASS. `sys.path.insert(0, ...)` inserts only the exact
   computed `shared/scripts` path; no user input flows into a path. F7 guard
   prevents writing triage state into an unrelated foreign tree (reduces
   write-surface).
4. **Test Quality** — PASS. 18 new WP5 tests + 4 new F5 tests; red-then-green
   verified; tests assert behavior (rc/keys/file presence), not implementation;
   plan-review High edge case has its own test.
5. **Performance Basics** — PASS. One extra import + a `relative_to` per finding;
   no loops/IO added on the hot path. The F7 guard short-circuits BEFORE any
   triage import in foreign dirs (strictly faster there).
6. **Naming & Structure** — PASS. `_resolve_project_root` / `_strip_worktree_prefix`
   / `_is_shipwright_project` mirror the names used by the sibling canonical
   hooks; no new abstractions.
7. **Affected Boundaries (ADR-024)** — PASS. Producer/consumer of each touched
   serialized format identified (see table above); real round-trip probes run
   in Step 3.8 (counter producer↔reader same-file; triage write-then-read;
   main↔worktree dedup-key parity).

## Confidence Calibration

Empirical probes (medium + `touches_io_boundary`). All REAL (subprocess /
producer→file→consumer), not assertions.

**Probes run (2 rounds, both clean → asymptote reached):**

- **P1 — counter producer↔reader round-trip (F10):** fired `track_tool_calls.py`
  twice from a workspace root above a `webui/` subdir project, then ran
  `estimate_context_pressure.py` from the same cwd. Producer wrote `2` into
  `webui/.shipwright/toolcall_count`; reader saw `2`. **Agree.** (Before: reader
  read the non-existent workspace-root counter → 0.)
- **P2 — F7 project guard:** foreign dir (CLAUDE.md, no marker) → `_emit_drift_to_triage`
  returned 0 and created NO `.shipwright/`. Shipwright project → 1 item written
  and read back. **Pass.**
- **P3 — F8 cross-tree dedup-key parity:** main root and `.worktrees/slug` root,
  same content finding → both `drift:claude.md:content`. **Equal.**
- **P4 — F6 `is_plugin_side` matrix:** 7 cases (worktree-prefixed plugins/, shared/,
  backslash, shared/tests exclusion, docs exclusion, plain plugin, README) — all
  correct.
- **P5 — F5 gate end-to-end (subprocess):** ran the ACTUAL `check_rtm_coverage.py`
  + `check_security_scan.py` from a workspace root above a `webui/` subdir
  carrying a low-coverage / unresolved-findings RTM → both soft-block (rc 2). A
  bare RTM at cwd still gates (cwd fallback) → rc 2. **Pass.**

**Findings from probes:** 0 (the Gemini-High `relative_to` edge + the gemini
timestamp-key question were caught at review-time and pre-empted with tests).

**Edge cases NOT probed (acceptable):** Windows-symlinked project roots (resolver
uses `.resolve()`; symlink behavior is the stdlib's, unchanged by this diff);
`SHIPWRIGHT_PROJECT_ROOT` pointing at a non-existent dir (resolver already guards
with `is_dir()` — covered by `lib.project_root`'s own tests, not re-probed here).

**Asymptote:** two consecutive probe rounds (unit suite + P1–P5 integration) with
zero new findings per boundary → boundaries calibrated.

## Test Completeness Ledger

| Behavior (this diff) | Disposition | Evidence |
|---|---|---|
| F5 RTM gate resolves via subdir auto-descent / env / cwd, blocks low coverage | tested | test_enforcement_hooks::TestSubdirectoryProjectLayout::test_rtm_gate_blocks_from_workspace_root, ::test_rtm_gate_resolves_via_env_var, ::test_foreign_repo_no_marker_allows |
| F5 security gate resolves via subdir auto-descent, blocks unresolved findings | tested | ::test_security_gate_blocks_from_workspace_root |
| F6 is_plugin_side strips `.worktrees/<slug>/` (plugins/shared/SKILL.md/backslash; excludes shared/tests, docs; idempotent for plain) | tested | test_wp5::TestIsPluginSideWorktreePrefix (8 cases) + probe P4 |
| F7 check_drift no-ops (no `.shipwright/`, no triage) in a non-Shipwright dir | tested | test_wp5::TestCheckDriftProjectGuard::test_no_triage_written_in_foreign_dir; emits in a project ::test_emits_when_shipwright_project + probe P2 |
| F8 content dedup key repo-relative + stable across main/worktree; outside-root no crash | tested | test_wp5::TestContentAnchorRepoRelative (4 cases incl. outside-root) + probe P3 |
| F8 (verify) timestamp keys already tree-independent | tested | test_wp5::test_timestamp_keys_are_tree_independent |
| F10 counter producer↔reader agree under auto-descent; precedence (abs file > env > resolver) | tested | test_wp5::TestCounterReadersAutoDescent (4 cases) + probe P1 |
| drift_anchor extraction preserves dedup behavior (drive-letter, legacy migration) | tested | test_drift_triage_emit (existing suite, repointed via re-export) |

0 testable-but-untested. No `could-test-but-didn't`. No web surface (pure-Python
tooling) → F2/F0.5 web surface `none`.
