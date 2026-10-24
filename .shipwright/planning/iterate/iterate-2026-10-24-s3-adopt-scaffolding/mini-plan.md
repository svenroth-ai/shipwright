# Mini-plan: S3 adopt, matcher, CI/CodeQL template keying, run-config writers

Goal (brief S3): adopt and the project writers use the stack-profile resolver so custom profiles work.

1. `profile_matcher.match_profile(signature, dirs)`: takes an ordered list of (source, dir); first dir owns a name even if its file is invalid (D1); invalid candidates are skipped with `warnings[]`; result carries `source` (project|user|bundled|explicit|builtin) and `warnings`; candidates carry `source`. Same >= 0.30 rule for custom profiles.
2. New `lib/adopt_profile.py`: `discovery_dirs` (resolver D1 triple, missing bundled dir raises) and `resolve_effective` (override, else snapshot match, else generic; resolved via `profile_consumer.resolve_named`).
3. `analyze_codebase`: uses discovery_dirs; a missing bundled dir is an error (exit 1) not silent `generic`; `SNAPSHOT_SCHEMA_VERSION` 1.0 -> 1.1 (additive `profile.source/warnings`, `candidates[].source`), new frozen fixture 1.1.
4. `generate_adoption_artifacts`: resolve the EFFECTIVE profile before any write, abort with SystemExit and nothing written on failure; reuse the resolved name for all artifacts; CI/CodeQL/automerge scaffolds use the effective profile (override wins) and pass the resolved source. File must not grow (grandfathered 716).
5. `shared/scripts/lib/ci_workflow.template_path_for_profile(name, source)` and `codeql_workflow.languages_for_profile(name, source)`: only None/bundled/builtin provenance get name-keyed defaults (D9); scaffolders accept `source` and return a `message` ("no CI template for profile X") on a miss.
6. `shipwright-project`: `lib/profile_check.profile_error` used by `write_run_config.py` and `checks/write-project-config.py`: accept any resolvable name or sentinel, reject D3-failing/unresolvable names with exit 4 and nothing written.
7. Audit every other consumer of `run_config.profile` (table in PR body).
Tests: new adopt/project/shared test files, one pytest process per root.
