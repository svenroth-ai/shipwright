# Python loaders use the stack-profile resolver, no silent fallback

Run: `iterate-2026-10-24-s2-python-loaders` (campaign `stack-profile-resolver`, unit S2). Brief: `.shipwright/planning/campaigns/2026-10-24-stack-profile-resolver-BRIEF.md` (D1-D10, S2 items 1-7 and the 1a table).

## What was built

- `shared/scripts/profile_consumer.py`: the glue every loader calls. Reads the run config's profile, resolves through the S1 resolver, prints the provenance line (D8a) and the shadow warning (D8b) on stderr, and adds a remediation hint to errors (`fix \`profile\` in shipwright_run_config.json, add the profile file, or set it to generic`; CLI origins name the option instead).
- Rewired onto it: `dev_server` (`profile_config`, new `_profile_input`, `multiservice`), `validate_env` (`init_env_file` / `validate` take an optional `profile_dir`; an error result `{"action": "error", reason, kind}` and a non-zero exit), adopt's `_scaffold_env_local`, `test_runner`, `performance_check` (new `performance_profile`), and `shipwright-design/.../setup-design-session.py`.
- Behaviour change: `setup-design-session` treats a null or empty `profile` in `shipwright_project_config.json` as the legacy `supabase-nextjs` default (before, only an absent key did); a corrupt config is an error.
- The path comparison uses real paths on both sides (the prose path is `<plugin>/../../shared/...` and may cross a symlink, junction or `..`); an empty `{profile}` renders `<bundled>/.json`, which names nothing, so the loader falls through to the run config default (table 1a). When the name came only from the path, errors name `--profile-path` as the origin.
- The live skill prose passes only `--profile-path <shared>/profiles/<profile>.json` (no `--profile`); `profile_consumer.name_over_bundled_path` turns a path that only spells a bundled file into its NAME, so sentinels exit 0 with the documented skip, and a project shadow wins with its warning (tests use the exact Step 3.8 and Step 1 shapes).
- The dev_server CLI maps resolver error kinds to exit codes (not_found 2, otherwise 3); boolean ports and timeouts are rejected.
- Every loader now reports `profile_source` (project | user | bundled | explicit | builtin) in its JSON.
- Per-loader table (S2 item 1a), one pinned test per cell: a reserved sentinel (`generic` / `detecting`) means built-in defaults; a run config that names nothing keeps the loader's documented legacy behaviour (test_runner and design: `supabase-nextjs`; dev_server: the build-config `dev_url` fallback; performance_check: explicit "no budgets (no profile)", exit 0; validate_env: skip); an unknown, corrupt or too-new profile is an error (exit 2 for not found, 3 for invalid or schema drift) and never a fallback.
- D9: the name-keyed command tables (`PROFILE_TEST_COMMANDS`, the npx defaults) apply only to a bundled profile, decided by provenance, so a project profile named `supabase-nextjs` gets its own commands (`profile_declares_no_layer` follows the same rule). A custom profile that declares no command for a layer is an error, not an npx guess. A custom profile's declared `e2e` command runs instead of the Playwright runner.
- D6 forward registry: each loader declares `PROFILE_KEYS_READ`; one test per root checks the keys exist in `stack_profile.schema.json`.
- D8f: prose-shaped invocations (`--profile X --cwd root`, and the legacy `--profile X --profile-path <bundled>/X.json`) resolve by NAME so a project shadow wins. `test_runner` gained `--project-root` (default `--cwd`); `performance_check` gained `--profile` / `--project-root`.
- S1 hand-offs: a dangling `.shipwright/profiles` symlink raises (user dir: absent); the isolation probe is tamper-evident (all boundary probes read the env var); dev_server accepts integral floats (`3000.0`) and rejects NaN, Infinity and 1e300; `shared/scripts` is never left on `sys.path` at import time (append, import, remove; the triage helper's `load_shared_lib` inserts at runtime and predates S2); plus the low items (`_row` resolved path, control-character escaping in `list`, fixture renames, session-base fixture, rooted Windows env path, warning when the env var is ignored).
- `docs/hooks-and-pipeline.md`: the changed reads, the D8d call-site trace and the rewritten `dev_url` fallback row.

## Decisions and justified deviations

- **Glue module (`profile_consumer.py`), against D2's "no new loader helper".** The cutover rules (sentinel, nothing named, error remediation) are identical in five loaders; five hand copies would drift. The module holds no lookup logic (that stays in the resolver) and each loader keeps its own sentinel / absent-profile policy as an explicit branch. Accepted deviation, recorded here.
- **S1-owned resolver files edited in S2.** D2's hot-file rule gives `profile_resolver.py` / `profile_model.py` / `resolve_profile.py` / `profile_test_isolation.py` to S1. The orchestrator handed the S1 review findings (dangling symlink, tamper-evident probe, low items) to S2 because S2 is the first consumer that hits them; no other unit edits these files in parallel (S3 and S4 start after S2 merges).
- `profile_consumer` imports are append-then-remove (D2): a plugin's own `lib` / `tools` packages must never be shadowed.
- Legacy `PROFILE_DEV_SERVERS` stays only as the `_get_services_for_test` seam; no runtime path reads it.

## Trust (D8d)

`test_runner.run_tests` (shell=True) and dev_server `Popen` run only inside a phase the user invoked (`/shipwright-test`, `/shipwright-build`, preview, iterate F0.5); no hook, session start or background producer resolves a profile to run its commands (traced in `docs/hooks-and-pipeline.md`). Unattended and campaign invocations count as "user invoked" for this trace, and the shadow warning is stderr-only (an accepted residual: nobody may read stderr in an unattended run). Accepted residuals (unchanged from S1): `~/.shipwright/profiles/` commands run in EVERY project including untrusted clones, and dev_server `_expand_env` substitutes project-controlled environment variables into those commands (attacker precondition: the user has such a profile AND opens a hostile repo AND runs a phase; existing control: the same repo's own scripts already run in that phase).

## Architecture Review

Internal (architecture-internal-reviewer, opus): revise, all points integrated (see the glue-module and hot-file notes above). External: glm approve, openai approve.

## Internal Plan Review (opus-plan-reviewer)

Integrated: provenance-based D9 for `profile_declares_no_layer`; prose-shaped `--profile generic --profile-path <bundled>` invocation resolves by name; hint wording; no stale `path` keys in the error result; `profile_source` on init and skips; design `config_profile`; cli ValueError handling; `--project-root`.

## External-Plan-Review-Findings (openai revise, glm approve)

| Finding | Disposition |
|---|---|
| New glue module conflicts with D2 | rejected-with-reason: five identical cutover rules; module holds no lookup logic (see Decisions) |
| Resolver edits belong to S1 | rejected-with-reason: orchestrator-sanctioned S1 hand-offs; no parallel editor |
| Compatibility paths (corrupt run config, `profile_dir`, explicit file classification, `--init` exit) | accepted-and-fixed (tests) |
| Shadow warning at every loader; D8f prose; command-run trace | accepted-and-fixed |
| Missing bundled file now an error | accepted-and-fixed (test pins the install-repair text) |
| Bloat arithmetic asserted | accepted-and-fixed (measured: test_runner 324, validate_env 591, performance_check 792 against caps 324, 602, 795) |

## Confidence calibration (Step 3.8)

Probes run against real files: BOM + CRLF + non-ASCII project profile through `test_runner` (resolved, source=project); empty-string profile in the run config (treated as naming nothing, legacy default); `performance_check` stdout is pure JSON with provenance on stderr; dev_server profile with `3000.0` port resolved to int 3000. One finding: a non-ASCII command output on Windows makes `subprocess` text decoding raise in a reader thread (pre-existing in `run_tests`, not caused by this unit). Two consecutive no-finding probes: asymptote reached. Not probed: junction targets on non-NTFS volumes.

## Stage-1 Spec Review (spec-reviewer, opus; two passes, both REJECT, escalated)

| Finding | Disposition |
|---|---|
| Pass 1, blocking: D6 per-loader consumed-keys constant missing | accepted-and-fixed (`PROFILE_KEYS_READ` in five loaders, a test per root); confirmed met in pass 2 |
| Pass 1, low: stale `_load_profile_data` seam in `test_dev_server_no_web_server`, stale docstring, `_plain` untested | accepted-and-fixed |
| Pass 1, low: no adopt cache-layout test | rejected-with-reason: adopt's `_scaffold_env_local` imports `validate_env` from the shared tree, which the shipwright-test and shipwright-design cache-layout tests already exercise |
| Pass 1, low: `--project-root`, custom-profile-without-command error, docs size | accepted: additive, tested; S5 reconciles the docs |
| Pass 2, blocking: S2 edits S1-owned `profile_resolver.py` / `profile_model.py` (D2 hot-file rule) | NOT resolved by the runner: the dispatch brief handed these S1 review findings (dangling symlink, NaN/Infinity, tamper-evident probe, rooted Windows path, low items) to S2 explicitly, so they are in scope of the task as given; the runner cannot grant itself a D2 amendment. Escalated to the orchestrator/operator with the exact file list (`profile_resolver.py`, `profile_model.py`, `resolve_profile.py`, `profile_test_isolation.py`, `test_profile_resolver_source_gaps.py`). Later: the edits went through the orchestrator's 3f-bis re-run and the unit merged as PR #899. |
| Pass 2, low: `get_test_command` names `pc.ProfileInvalid`; glue module is a new helper | accepted: callers catch `ValueError` and branch on `.kind`; the raise-by-name is in the producer, not a catcher |
| Pass 2, low: `shipwright_test_config.json` `enabled: true` with no profile still runs budgets | accepted: pre-existing, outside the 1a cell |

## External-Code-Review-Findings (openai revise, glm revise)

| Finding | Disposition |
|---|---|
| high: custom profile E2E command ignored (Playwright runner used) | accepted-and-fixed (custom profiles run their declared command; test added) |
| medium: S2 edits the resolver (D2) | see the pass 2 row above |
| medium: dev_server paths other than `cmd_start` may raise | rejected-with-reason: `cmd_start` is the only caller of the services loader (grep); the CLI maps the result to a non-zero exit |
| medium: removed `default_profile_path` / `load_profile` helpers | rejected-with-reason: no importers in the repo (grep); `deploy_profile.load_profile` is a different function |
| medium: CLI-origin hint named the run config | accepted-and-fixed (CLI origins name the option; test added) |
| low: `project_root=None` default, bool port, dead legacy map, `NO_PROFILE_REASON` override, stub strictness | rejected-with-reason: bool ports are already rejected by `_validate_services`; the legacy map is still the `_get_services_for_test` seam; the explicit skip reason is mandated by the 1a table |

## Code and doubt review

Not run inside the runner: the Stage-1 gate did not pass there (see above), so Stage 2 (`code-reviewer`) and Stage 3 (`doubt-reviewer`) were not started. Update after merge: the campaign orchestrator re-ran the whole cascade (3f-bis) on the pinned head, the unit then merged as PR #899 (`1caabdcc6`); the Stage-1 escalation row above and the round 3 table are the record of that re-run's findings.

## Round 3 review dispositions

| Finding | Disposition |
|---|---|
| Path comparison collapsed `link/..` lexically before following the symlink (POSIX) | accepted-and-fixed (no `abspath`; POSIX-only test, not runnable on the Windows build host) |
| deploy / preview / build agent / adopt prose routed a profile error into the missing-env-vars branch; adopt still named `profile_dir` | accepted-and-fixed (one sentence each) |
| test skill detected a free-form profile name; test-runner invocation lacked `--cwd` | accepted-and-fixed (bundled name or `generic`; `--cwd {project_root}`) |
| Custom profile declaring a layer without a command skipped silently | accepted-and-fixed (error like unit; a layer not declared at all may still skip) |
| Hint says "run config" when the name came from the built-in default | accepted-not-fixed: unreachable in practice (the default is a bundled name that always resolves), so wording-only |
| Wrong-case names on the path route | accepted: only lowercase profile names are recognised by the path route |
