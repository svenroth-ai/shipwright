# Custom stack profiles reach the interview, the docs and an end-to-end proof

Campaign stack-profile-resolver, unit S5 (last unit).

## Decision

- Project interview step 7 lists candidates from `resolve_profile.py list --json` (valid ones only), lets the user name a custom profile in plain language, and keeps `generic` when nothing fits.
- `write-project-config.py` gains a lookup-only `--profile-root` (both SKILL call sites pass it) so a requirements file outside the project still finds `.shipwright/profiles/`. `--project-root` keeps its meaning (config location). The early `in_progress` call with `generic`/`detecting` skips the profile check; a missing shared tree degrades to a stderr warning.
- The config-location defect (config under `<project>/.shipwright/` when only `--planning-dir` is passed) is left unchanged on purpose: relocating it risks adopted-repo overwrite and hook activation and needs its own reviewed change.
- New `docs/stack-profiles.md` (locations, lookup order, committing, copy-and-rename, an explicit `command` on every declared layer, `schema_version`, shadow warning, trust). guide ch.5/4.2/App.B, hooks-and-pipeline and the CLAUDE.md "never hand-composed" sentence (now excepting `.shipwright/profiles/`) are reconciled.
- `*.py` guard (`shared/tests/test_stack_profile_py_guard.py`): an AST check that no module builds a profile path outside the resolver and that no `except ValueError` around a resolver call swallows the error (re-raise, exit, return a failure, or branch on `.kind`). Both guards read the git index through `shared/tests/index_files.py` (one policy, documented there).
- `test_runner` names the real `testing.<key>.command` per layer; S2/S3/S4 prose and test nits are applied.
- An integration test builds a tmp project, runs from a git worktree and drives test_runner, dev_server, validate_env and adopt: source=project everywhere, schema_version too new fails every loader with one message while adopt discovery only warns, user-level profiles, bundled-name shadow (D9).

## Architecture Review

External, `--mode architecture`, over a brief about the `*.py` guard only: GLM approve (two low notes: the guard is heuristic so keep the call-name list discoverable; fall back to a text pattern if it passes about 200 lines or a third allowlist); OpenAI reject (medium: a permanent repo-wide scanner is disproportionate to a hypothetical regression; verify propagation through existing consumer tests; recommended option C, no guard). The runner halted the unit as its contract requires. Operator decision (2026-10-24): keep the BRIEF as written, the guard stays, because it prevents re-introducing hard-wired bundled-profile paths and swallowed resolver errors that would silently ignore custom profiles; the cost is one more test to maintain. OpenAI's dissent is overruled by the operator-approved BRIEF rev 3, where the guard is an acceptance criterion.

## External-Plan-Review-Findings

| Reviewer | Finding | Disposition |
|---|---|---|
| GLM+OpenAI (high) | `--project-root` at the call sites relocates `shipwright_project_config.json` | accepted-and-fixed (new lookup-only `--profile-root`; config location unchanged, pinned by a test) |
| GLM (medium) | S4 accepted nits and the index-vs-working-tree policy missing from the plan | accepted-and-fixed (ls-files -z, dedupe, unmerged message, policy in `index_files.py`, commands-test widening and rename) |
| GLM (medium) | record decisions on the BRIEF S4 item 3 amendment and the config location | accepted: config location left unchanged (above); BRIEF S4 item 3 NOT amended (contract change, a human call) |
| GLM (medium) | verbatim-copy pin test for the per-layer hint | accepted-and-fixed (`test_test_runner_copied_bundled_profile.py`) |
| GLM/OpenAI (medium) | discovery vs selection; "no match keeps generic" vs an explicit failing name | accepted-and-fixed (separate integration assertions; an explicit pick resolves and stops on failure) |
| OpenAI (medium) | copied-profile contract missing from docs and tests | accepted-and-fixed (docs/stack-profiles.md; exit-3 hint test) |
| OpenAI (medium) | index policy must be stated; reverse-exemption check kept | accepted-and-fixed |

## Confidence Calibration

Boundaries: resolver CLI/loader output consumed by four command loaders, and the profile name written by the project writer. Probes: (1) the four loaders run as subprocesses from a git worktree against a committed project profile: source project; (2) same with schema_version 99: exit 3 with one message in each; (3) adopt discovery with the same file: warning, candidate excluded, run continues; (4) planted-path and planted-swallow cases for the `*.py` guard, red then green. Probes with findings: 2 (`--project-root` relocating the config; a legacy-path canon lint hit on a test variable name), both fixed and re-probed. Not probed: a live Claude session answering the interview question (acceptable: the prose calls plain CLIs).

## External-Code-Review-Findings

| Reviewer | Finding | Disposition |
|---|---|---|
| GPT (medium) | path rule missed `Path(root) / ".shipwright/profiles/x.json"` (file below the directory) | accepted-and-fixed (any `/profiles/` component in a whitespace-free string; project and user planted cases) |
| GPT (medium) | `except ValueError: sys.exit(0)` counted as loud | accepted-and-fixed (zero or omitted exit status, `raise SystemExit(0)` are swallows; planted cases) |
| GLM (medium) | S3 hand-off `codebase-analysis.md:11` neither fixed nor verified | verified: S4 already replaced the bundled path with the lookup-order wording; nothing left to change |
| GLM (medium) | integration test: env var assumption, loose adopt source assertion | accepted-and-fixed (the integration conftest isolates `SHIPWRIGHT_USER_PROFILES_DIR` per test; adopt asserted as `user-stack` / `user`) |
| GLM (low) | import-error degrade also applied to `--status complete` | accepted-and-fixed (degrade only for the early `in_progress` call; complete exits 1 as before, pinned) |
| GLM (low) | vacuous assertion in the copied-profile test | accepted-and-fixed (removed) |
| GLM (low) | method try/except double-walked under `<module>` | accepted-and-fixed (classes are scope boundaries; planted method case) |
| GLM (low) | e2e uses the private `_get_services_resolved` | rejected-with-reason: `dev_server.py` only starts, stops or reports services; the signature is pinned in a comment and by `test_dev_server_profile_resolution.py` |

## Review-Cascade-Round-1-Reconciliation

| Finding | Disposition |
|---|---|
| Guard exempted production modules by the `test_` filename prefix (`test_runner.py`, `test_gate.py`, ...) | accepted-and-fixed: test files are recognised by location only (a `tests`/`test` directory or `conftest.py`); a test pins that `test_runner.py` is scanned and that a planted `except ValueError: return None` at its resolver call turns the guard red |
| `RESOLVER_CALLS` missed `resolve_in_dir`, `check_name`, `config_profile`; wrappers unhandled | accepted-and-fixed: names added (`check_name` only as an attribute call); per-module wrapper closure plus pinned cross-module wrappers (reverse-checked); planted wrapper case |
| `.kind`/`.exit_code` counted as loud when merely mentioned | accepted-and-fixed: counts only when branched on (If/IfExp/Compare/Match) or returned as the code; planted red cases |
| A returned call counted as loud although it ignores the exception | accepted-and-fixed: loud only when it receives the caught exception or is a non-zero int; `return dict()`, `return default_profile()`, `return _skipped(...)` are swallows |
| `Profile*` handlers not treated as the `ValueError` family | accepted-and-fixed: handler types ending in ProfileError/NotFound/Invalid/SchemaDrift count; planted cases |
| `adopt_profile.hint_warning` cosmetic kind-message change | accepted-and-fixed: reverted. It feeds the snapshot `profile.warnings[]` (via `analyze_codebase.py`), the same channel as the S3 matcher, so it is on the swallow allowlist with that reason |
| Rule 1 skips the first argument of `.get/.pop/.setdefault`; public helpers not flagged | accepted as a documented blind spot (`bundled_dir`, `search_dirs`, `_PROFILES_DIR`, `_profiles_dir`), stated in the guard module docstring |
| Interview: invalid rows hidden; explicit pick could fall back to `generic` | accepted-and-fixed: invalid rows (name + `error`) are shown; an invalid or unlisted explicit pick runs `resolve` and STOPS |
| `warnings` described as skipped candidates; exit-4 wording | accepted-and-fixed: `warnings` carries directory problems only, invalid candidates are `valid:false` rows with `error`/`kind`; writer exits 4 when the name does not resolve to a usable profile, 1 when the shared tree is missing on a complete scaffold (step-7 reference and `docs/hooks-and-pipeline.md`) |
| `{project_root}` vs `{project_path}` for list/resolve/writer | accepted-and-fixed: one placeholder, `{project_root}`, defined once in step-7 (file mode: the project being scaffolded, never the requirements file's folder); `first-actions.md` early-config call aligned; `step-e-artifact-generation.md` not touched |
| e2e helper leaked the developer's git setup; `.gitignore` canon not applied; main-checkout copy could satisfy the asserts | accepted-and-fixed: `core.excludesFile=` neutralised and `GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE` stripped; the managed gitignore is merged before `git add .`; the main checkout's profile directory is removed after the worktree is created (D10); private-API reason kept in a comment |

The swallow allowlist is larger than the BRIEF's single S3 matcher entry. Added, each reverse-checked and with a reason: `profile_matcher._discover` (BRIEF, `warnings[]`), `adopt_profile.hint_warning` (feeds the same `warnings[]`), `profile_resolver._row` (builds the `valid:false` discovery row, the D1 skip), `profile_check.profile_error` (returns the reason string; both callers exit 4). Operator decision to keep the guard (BRIEF rev 3) stands.

## Review-Cascade-Round-2-Reconciliation

| Finding | Disposition |
|---|---|
| BRIEF S5 item 3 allows a single swallow exception; `profile_check.profile_error` was a second | accepted-and-fixed: `profile_error` is gone. `check_profile` lets the resolver's `ValueError` through and `describe` formats the reason; `write_run_config.py` and `write-project-config.py` each catch it, print it and `return 4` (same exit codes and messages; the unit tests keep their assertions through a test-side adapter). `check_profile` is a pinned wrapper, so a caller that swallowed it would be red |
| `profile_resolver._row` is the resolver itself, not a caller | accepted-and-fixed: `RESOLVER_MODULES` (`profile_resolver.py`, `profile_model.py`) are excluded from the swallow scan by location, like rule 1's allowlist (reverse-checked: they must still exist); the allowlist entry is removed |
| Remaining swallow allowlist | exactly two entries, pinned by a test: the S3 matcher `_discover` and `adopt_profile.hint_warning`. `hint_warning` belongs to the same S3 `warnings[]` family: its string is appended to the snapshot's `profile.warnings[]`, and the hint is resolved again, loudly, at generation |
| `raise SystemExit` / `raise SystemExit from e` | accepted-and-fixed: a bare-name `SystemExit` is a zero exit; planted reds |
| A re-raising handler still counted as protecting a helper | accepted-and-fixed: a `try` protects only through a handler that does not propagate (bare `raise`, `raise exc`, `raise ... from exc`); a re-raise as another type protects; planted red (re-raising local wrapper inside a swallowing `try`) and green |
| `return str(e)` / `return log.warning(e)` / `return _skipped(p, n, e)` counted as handling | accepted-and-fixed: conversion and logging callees are neutral, and a returned call is loud only when it is a failure builder (name pattern) handed the exception; planted reds |
| `_get_services_resolved` (multiservice `cmd_start`) not covered; `kind` through a local | accepted-and-fixed: pinned wrapper (reverse-checked) and `_branches_on_kind` follows one `kind = getattr(e, 'kind', ...)` / `e.kind` assignment into a later test; multiservice's real handler is green, its kind-dropped variant red |
| `ast.TryStar`, `contextlib.suppress(ValueError)` | accepted-and-fixed: both scanned; planted reds |
| Loud forms searched inside nested functions of a handler | accepted-and-fixed: handler scans stop at nested functions, classes and lambdas |
| Guard parses every file repeatedly | accepted-and-fixed: parsed trees and `_all_swallows()` are cached; the guard test module runs in about 7 s |
| e2e: scrubbed env only for `_git`; commit hooks | accepted-and-fixed: one `_env()` (GIT_DIR, GIT_WORK_TREE, GIT_INDEX_FILE stripped) used by `_git` and `_run`; `core.hooksPath=` empty |
| Import aliases, lambda / `partial` wrappers, any-path loudness, `except BadProfile` via alias | accepted as documented blind spots (module docstring); the guard is a heuristic and this is the last hardening round |

The guard rules were split into `stack_profile_py_rules.py` and `stack_profile_py_handlers.py` for the 300-line cap.
