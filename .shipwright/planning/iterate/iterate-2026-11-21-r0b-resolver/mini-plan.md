# Mini-plan: R0b resolver `shipwright_paths.py` + guard (no behaviour change)

Spec: `.shipwright/planning/iterate/campaigns/root-files-into-config/sub-iterates/R0b-resolver.md`; BRIEF sections 4.6, 4.7, 5/R0b, 11.0-11.9 (R0a survey).

## Goal
Centralise every reference to a root `shipwright_*` file behind one stdlib-only module, with the paths still at the repo root and byte-identical behaviour, so R1-R3 become edits to one file.

## Design
- `shared/scripts/lib/shipwright_paths.py`: registry (key, basename, KIND in config/baseline/register/derived/marker/state/pointer, moves, marker, main_root, retired, lock, fixed_tmp). API: `rel`/`name`, `path`, `main_path` (main-repo-root variant, class 8), `rel_at(key, commit)` + `legacy_rel` (per-commit repo-relative POSIX, class 8, 11.9 items 1+6), `lock_for` (run_config, ac_registry; sync_config -> events lock, 11.9 item 4), `lock_beside`, `family_globs`, `names_of`/`snapshot_paths` (generated lists), `json_path_or_none`.
- Import contract: unique top-level module name; plugin code appends `shared/scripts/lib` to `sys.path` for the import only (ADR-045: no `lib` collision), restoring `sys.path` afterwards.
- Migration: an AST codemod replaces every exact string literal (262 sites, 150 files) by `_sp.rel("<key>")`; hand migration for locks (7 writers + events lock), constructed name (`group_a`), regexes (`review_record_tier`, `events_references`), globs (`change_type_paths`), class-8 readers (`rel_at`), generated lists (`CONFIG_MARKERS`, `CONFIG_FILES`, `DERIVED_SNAPSHOTS`, `RESTORABLE_SNAPSHOTS`), model config (`main_path`).
- Guard test (shared/tests): AST scan of production Python (literals, f-strings, concatenation, `.lock` construction, `.shipwright/` prefix rules, class-8 call shapes) with a reasoned allowlist; carriers (bash, YAML, deploy-profile JSON, SKILL/agent/reference md, templates) held to a per-file count ratchet because prose cannot call a resolver.
- Out of scope: pointer format, moving any file, dual-lock (R1), prefix-rule decisions (R3).

## Risks
Import mechanics across 14 plugins; bloat anti-ratchet (many files at their baseline); hooks that now import the resolver at startup (skew window with a stale shared cache).

## Tests
All 18 pytest roots green; new `test_shipwright_paths.py` (frozen pre-resolver names, generated lists identical) and `test_shipwright_paths_guard.py`.

## Review dispositions (code review round, commit 8dbdf0e57 + follow-up)

External-Code-Review-Findings (openai revise, glm revise) and Stage 2 code-reviewer, each `accepted-and-fixed` unless stated:

| Finding | Disposition |
|---|---|
| generate_handoff_on_stop imports the resolver outside the cache-race retry | accepted-and-fixed: import moved into `_do_lib_imports` |
| session_start / master_stop_check / track_tool_calls / check_required_checks / iterate_worktree_gate crash on stale cache | accepted-and-fixed: try/except ImportError with literal fallback (guard LITERAL_ALLOWED, reasoned) |
| `json_path_or_none` changed behaviour for unknown or non-`.json` names | accepted-and-fixed: unknown names keep the old construction |
| `name = rel` conflates basename and path (4 basename-compare sites) | accepted-and-fixed: `name()` is a real basename function; sites use it |
| generate_session_handoff `rel(skill+"_config")` KeyError | accepted-and-fixed: `json_path_or_none` |
| events_references blind to `_sp.rel("events")` | accepted-and-fixed: TOKEN covers resolver call forms |
| `sys.modules[__name__]` KeyError under exec-before-register loaders | accepted-and-fixed |
| lock_for("sync_config") vs events_lock_path | accepted-and-fixed: equality pinned by test |
| RESTORABLE exclusion hand-listed | accepted-and-fixed: `run_written` flag |
| probe test clobbers sys.modules; id()-keyed parametrize | accepted-and-fixed |
| allowlists are per file, not per hit | rejected-with-reason for R0b: whole-file entries are reasoned and finite; per-hit pinning deferred to R1 |
| carrier ratchet may not tighten; carriers miss .ts/.js | deferred to R1/R3 inventory (carriers flip with the plugin version in R3) |
| ~150 packed bootstrap lines | rejected-with-reason: zero-net-line placement is forced by the bloat anti-ratchet |
| class-8 heuristic misses diff/ls-files/log | deferred: documented limit beside the module-constant blind spot |
| group_a json_path_or_none now stricter for non-`.json` registry keys | accepted: no such files exist; noted |

## Confidence Calibration (Step 3.8)

Probes run: 6. (1) Frozen-name test: all 26 registry names equal the pre-resolver literals. (2) `-I` isolated run of a plugin tool, a shared hook and a stop hook (producer -> shipwright_paths import under the real sys.path bootstrap). (3) Round-trip of locks: `lock_for("run_config")` equals the old `.with_suffix(".json.lock")` / `with_name` result; sync_config lock equals `events_lock_path`. (4) Mirror-layout tests of design/test/adopt/iterate caches. (5) Swapped-`os.name` import probe (found one finding: pathlib bootstrap in dev_server/profile_config -> fixed with os.path -> re-probed clean). (6) Cache-race retry test (found one finding: import outside the retry -> fixed -> re-probed clean). Asymptote: two consecutive no-finding probes after each fix. Not probed: a real cross-version plugin-cache skew (needs two installed versions; mitigated by mandatory cache sync after merge).

## Doubt review dispositions (Stage 3, commit f8f40a143)

- security_gate / rtm_gate_support transitive crash on stale shared tree: accepted-and-fixed (try/except ImportError + literal fallback; guard LITERAL_ALLOWED).
- grade routing / authoritative eager shared import: accepted-and-fixed (same pattern).
- generate_session_handoff `json_path_or_none(...).name` None hazard: accepted-and-fixed (`_sp.name`).
- Three module names for one resolver (R1 state hazard): deferred to R1, which must keep the module stateless or unify imports; documented in the resolver.
- `_p` left on sys.path when the import raises: accepted (appended, not prepended; only the stale-cache degraded path).
