# Stack-profile resolver core (campaign stack-profile-resolver, unit S1)

Run: `iterate-2026-10-24-s1-resolver-core`. Brief: `.shipwright/planning/campaigns/2026-10-24-stack-profile-resolver-BRIEF.md` (D1-D10).

## What was built

- `shared/scripts/profile_resolver.py` (+ `profile_model.py`, `profile_schema_check.py`, split only for the 300-line limit; the D2 hot-file rule covers all three): lookup project, then user, then bundled; first FILE wins, never falls through.
- `shared/scripts/tools/resolve_profile.py`: `resolve | list | validate`, exit codes 0/2/3/4, provenance on stderr, `list --json` carries `contract_version: 1` (fixture pinned).
- `shared/schemas/stack_profile.schema.json`: lax by design (`additionalProperties: true`); typed keys only where a wrong type would crash or misroute a loader (services[], dev_server, testing.*, required_env_vars, rules, folder_structure, migrations, design_system). Polymorphic cases (port integer or placeholder string, `testing.unit` string or object, nullable blocks) each have a fixture.
- `!/.shipwright/profiles/` in the gitignore template and the repo block (D10); `profile_test_isolation.py` autouse fixture wired into nine test roots (D4).

## Decisions taken in this unit

- Integral floats (`3000.0`, `1.0`) count as integers, matching Draft 2020-12; `additionalProperties: false` is rejected as an unsupported construct, so the hand checker cannot diverge from `jsonschema`.
- A plain missing user profiles directory warns in `list` (D4 literal reading); it is silent for `resolve`.
- A file named like a sentinel (`generic.json`) in any source is an error even though `generic` itself reads no file.
- A lower-priority source with a defective entry never blocks a valid winner; it is only recorded as a shadow.
- An existing but unreadable (or non-directory) project or explicit directory is an error, never a silent fall-through; only the user directory is treated as absent.
- No FR is minted in S1. Tests are tagged `FR-01.06` (the test phase is the first consumer of a resolved profile). The capability FR is minted or folded when the loaders switch over (S2-S5).

## Trust decision (D8, accepted residuals)

A project- or user-level profile can carry commands that run. Same trust class as the repo's own `package.json` scripts. Resolution returns the shadow warning and provenance lines for every loader to print. Two accepted residuals: `~/.shipwright/profiles/` commands run in EVERY project including untrusted clones, and `_expand_env` (dev_server) substitutes project-controlled environment variables into those commands. Attacker precondition: the user has such a profile AND opens a hostile repo AND runs a phase; existing control: the same repo's own scripts already run in that phase.

## Architecture Review

Internal (architecture-internal-reviewer, opus): approve. External: glm approve, openai approve. Open point accepted: until S2 rewires the loaders, the CLI finds profiles that no phase uses yet; the campaign tracks "every phase finds it" as unmet until S4/S5.

## Internal Plan Review (opus-plan-reviewer, severity medium)

| Finding | Disposition |
|---|---|
| Unreadable project dir falls through (D1) | accepted-and-fixed (`_listdir` strict for non-user sources) |
| Sentinel-named file ignored by resolve | accepted-and-fixed (error in any source) |
| Hot-file rule covers one of three files | accepted-and-fixed (docstrings; PR text) |
| Missing or corrupt schema file escapes the error contract | accepted-and-fixed (`schema_unsupported`, exit 3; parse cached) |
| Integer-valued floats diverge from jsonschema | accepted-and-fixed |
| Containment resolved twice | accepted-and-fixed (resolved once, that path is read) |
| Test-only module in runtime tree, duplicated env constant | accepted (location forced by cross-root import; equality test added) |
| `_NON_PROFILE_STEMS` too broad | accepted-and-fixed (full stems) |
| CLI edge cases (`--json` with `--path-only`) | accepted-and-fixed for the mutual exclusion; `validate --json` failure object not added |

## External-Plan-Review-Findings (glm revise, openai revise)

| Finding | Disposition |
|---|---|
| Dir or dangling symlink at the winning path could count as absent | accepted-and-fixed (tests added) |
| Hand checker vs jsonschema parity (bool as integer) | accepted-and-fixed (mutation fixtures, parity test) |
| Three modules instead of one | rejected-with-reason: the 300-line source limit is a hard repo rule (bloat gate) |
| Packaged-layout boundary probe | accepted: probes run in each consumer root; siblings and the schema sit in the same shared tree the cache syncs |
| Gitignore negation effectiveness | accepted-and-fixed (scratch-repo test with the rendered template) |
| Wrong-case lookup behaviour | accepted-and-fixed (deterministic error, tests) |

## External-Code-Review-Findings (openai revise, glm approve)

| Finding | Disposition |
|---|---|
| Lower-priority defects block a valid winner | accepted-and-fixed |
| Discovery ignores `.JSON` extension | accepted-and-fixed |
| `NAME_RE.match` accepts trailing newline | accepted-and-fixed (`fullmatch`) |
| `covers` marker unregistered in some roots | accepted for the design plugin (registered); the other roots already register it |
| Sentinel scan swallows OSError for the project dir | accepted-and-fixed |
| `load_profile_file` stem for upper-case extension | accepted-and-fixed |
| `main` raised SystemExit mid-run | accepted-and-fixed (returns the code) |

## Code review (code-reviewer, opus) and doubt review (doubt-reviewer, opus)

| Finding | Disposition |
|---|---|
| Symlink loop raises RuntimeError on 3.11, escaping the error contract (medium) | accepted-and-fixed |
| list_profiles repeats a directory seen twice; load_profile_file mis-ranks bare-path shadows; vacuous Windows test; fixture pins bundled names; tmpdir-based canary; blank lines | accepted-and-fixed |
| Boundary probes moved shared/scripts to the end of sys.path via remove() (doubt, medium) | accepted-and-fixed (exact restore) |
| Deeply nested JSON raised RecursionError and crashed list (doubt, medium) | accepted-and-fixed (maps to invalid) |
| Integral-float port passes the schema but dev_server validation rejects it (doubt, low) | rejected-with-reason for S1 (parity with Draft 2020-12 is the contract); S2 hand-off: the dev_server normaliser must coerce integral floats |
| No `.tmp` re-exclusion under profiles/ (doubt, low) | accepted-and-fixed (`/.shipwright/profiles/*.tmp`) |
| Relative `SHIPWRIGHT_USER_PROFILES_DIR` resolves against a repo-controlled cwd (doubt, low) | accepted-and-fixed (relative value ignored). `source: user` is NOT a trust elevation over `project`; a project-level symlinked profiles directory is accepted by design (same trust class as the repo's own files). |
