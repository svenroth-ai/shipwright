# Mini-Plan: profile-declared test roots

Run-ID: iterate-2026-11-02-profile-declared-test-roots
Spec: .shipwright/planning/iterate/2026-11-02-profile-declared-test-roots.md

## 1. Files
- edit `shared/schemas/stack_profile.schema.json`: optional `traceability` object with `test_roots` (array of strings).
- edit `shared/profiles/vite-hono.json`: `traceability.test_roots` = server/tests, server/src, client/src, client/e2e, client/tests, e2e.
- new `plugins/shipwright-compliance/scripts/lib/collectors/_test_links_profile_roots.py`: `profile_test_roots(project_root) -> list | None` (run-config profile name, resolve via shared profile_consumer with sys.path append/remove, validate list-of-str, never raises; one stderr line on a broken profile).
- edit `_test_links_io.py` (at 295 lines, so only a 3-line hook): `_resolve_test_roots` falls to the profile roots when the compliance config has no `test_roots` key, then to the defaults; the "no folder resolved" warning text gains the profile hint.
- edit `docs/stack-profiles.md`: document the key.
- tests: new `plugins/shipwright-compliance/tests/test_test_links_profile_roots.py` (AC1-3, 5 via the gate regen), new `shared/tests/test_stack_profile_test_roots_schema.py` (AC4).

## 2. Work breakdown
1. Schema key + vite-hono value + schema test (all bundled profiles still validate).
2. Profile-roots module + unit tests (profile hit, no profile, sentinel, unknown name, broken file, wrong type).
3. Hook into `_resolve_test_roots`, precedence tests (config wins; profile used; default).
4. Gate regen test on an archive-like tree (run config + project profile present).
5. Docs.

## 3. Test strategy
Unit tests only (collector is pure filesystem); one gate-level test with the real `_layer_coverage_regen._build`. No UI, no E2E. F0.5 surface: cli (runner pytest).

## 4. Alternative approach
Widen the default discovery to any-depth `tests`/`e2e` directories for all projects: no profile coupling, but changes every project's manifest.

## 5. Revisions after the internal reviews (integrated into the plan above)
- New module `_test_links_profile_roots.py` owns: profile lookup, the "no test folder resolved" warning (moved out of `_test_links_io.py`, which sits at 295 of 300 lines), the per-root dedupe set.
- `_test_links_io.py` imports it at MODULE level (never inside a function): the gate's `_load_collector` clears `scripts.*` from `sys.modules` after import, so a call-time relative import would fail.
- `shared/scripts` on `sys.path`: guarded `_ADDED` pattern (add only if absent, remove only what this module added); path computed like `_lib_loader` (`parents[5]/shared/scripts`). Test: an entry already at index 0 survives the import.
- Profile lookup uses `search_dirs=[project dir, bundled dir]` only (no user-level dir), so the manifest depends on tracked files plus code and is the same locally, in CI and in the gate archives. `quiet=True`, never `emit()`.
- Profile entries go through the SAME entry loop as the config entries (drops `**`, absolute, `..` and symlink escapes). `profile_test_roots` catches `(ValueError, OSError)`.
- Precedence is REPLACE per tier, as the user approved: compliance config, else profile roots, else conventional defaults. Profile roots that resolve to at least one existing folder replace the defaults. A profile list that is empty, or whose folders all fail to exist, falls back to the defaults and (when non-empty) writes one warning naming the profile (typo guard). (An earlier revision unioned with the defaults; both external reviewers flagged it as contradicting the approved spec, so it was reverted.)
- `quiet`/`warn=False` flows through to the profile line; a broken-profile line is deduped per resolved root.
- The warning names where the roots came from (compliance config, profile `<name>`, or defaults).
- AC5 gate test lives in `shared/tests/` (the `tools` package collides inside the compliance test root, ADR-044); AC1-3 stay in the compliance root; the gate test goes through `_load_collector`.
- Schema: `traceability.test_roots` is an array of `{type: string}`; further entry checks stay in the collector.
- Docs: `docs/stack-profiles.md` (key, user-level profiles do not affect it, a wrong type breaks the profile for every phase), `docs/hooks-and-pipeline.md` context-loading row (compliance reads run-config `profile` and the project/bundled profile), changelog drop noting the one-time manifest change for existing vite-hono projects.

## 6. Triage of the internal reviews
- fix: sys.path guard; module-level import; AC5 test location; user-level profile dir excluded; quiet+dedupe; union with defaults / fallback; 300-line cap; shared entry loop; docs rows + changelog; schema entry type; source named in the warning.
- disclose (known limitations): (a) a project that gitignores `shipwright_run_config.json` gets default roots in the gate archives while a local run uses the profile roots; the warning text points at `traceability.test_roots` for that case; (b) one-time large manifest change for existing vite-hono projects.
- decline: caching per (root, mtime): five cheap reads per process, not worth the invalidation logic.

## 7. External plan + architecture review (glm, openai): plan=revise/revise, architecture=approve/approve
- fix: revert the union with defaults to REPLACE per tier (spec and plan now agree); warning when a profile declares roots but none exist.
- fix: when the run-config profile name is not found among project/bundled profiles, the diagnostic says user-level profiles are not consulted for test roots and points at `traceability.test_roots`.
- fix: gate parity test builds a real temporary git repo with a committed run config + project profile and goes through the real archive + `_load_collector` path; extra test: shared dir unreachable returns None plus one line, no exception.
- disclose: gitignored run config => gate archives use default roots (warning text names this cause); `sys.path` convention is accrued tech debt owed to the next change needing profile data in a plugin; a type-invalid `traceability` in a profile fails that profile's validation for every phase (existing schema behaviour for typed keys).
