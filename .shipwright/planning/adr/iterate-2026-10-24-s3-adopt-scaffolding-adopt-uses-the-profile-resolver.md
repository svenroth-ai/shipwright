# Adopt, matcher, CI/CodeQL scaffolds and run-config writers use the stack-profile resolver

Run: `iterate-2026-10-24-s3-adopt-scaffolding` (campaign `stack-profile-resolver`, unit S3). Brief: `.shipwright/planning/campaigns/2026-10-24-stack-profile-resolver-BRIEF.md` (D1-D10, S3 items 1-7).

## What was built

- `profile_matcher.match_profile(signature, dirs)` takes an ordered list of directories and discovers through the resolver's `list_profiles` (ownership, name rules, containment, non-profile files); custom profiles score by the same rule (>= 0.30 else `generic`). An invalid candidate is skipped with a `warnings[]` entry and keeps its name; a non-object `stack` counts as no dependencies. The result carries `source` and `warnings`; candidates carry `source`.
- New `adopt_profile.py` (adopt lib): `discovery_dirs` (a missing bundled directory raises `BundledProfilesMissing`, exit 1 in `analyze_codebase`), `resolve_effective` (override, else snapshot match, else `generic`; resolved through `profile_consumer.resolve_named`; `detecting` is refused; a provenance change since analysis aborts), `hint_warning`.
- `generate_adoption_artifacts`: the effective profile is resolved before any write; failure prints the error, exits with the resolver code (2 not found, 3 invalid) and writes nothing. The resolved name is used throughout; CI, CodeQL and automerge scaffolds use it (override wins over the snapshot) and pass the resolved source. The result carries `profile: {name, source, shadows, warnings}`.
- `ci_workflow.template_path_for_profile(name, source)` and `codeql_workflow.languages_for_profile(name, source)`: only `None` (legacy name-only), `bundled` and `builtin` provenance get the name-keyed default (D9); a miss returns a `message` ("no CI template for profile X (source: ...)").
- `SNAPSHOT_SCHEMA_VERSION` 1.0 -> 1.1 (additive `profile.warnings`, `profile.source` on every arm, `candidates[].source`); new frozen fixture `adopt-snapshot-1.1.json`, documented in `cross-repo-contract.md` for the WebUI (S6). `--profile-hint` keeps its pre-existing `source: "user-hint"`.
- `shipwright-project`: `lib/profile_check.py`; `write_run_config.py` and `checks/write-project-config.py` accept any name the resolver resolves or a reserved sentinel and exit 4 with nothing written otherwise.

## Review dispositions

- Internal architecture: approve. Accepted: matcher goes through `list_profiles` (no own scanning), provenance-drift abort, shadow shown in the adopt result. Noted: `_scaffold_env_local` (S2) runs after the run config is written; an `action: error` there is reported, not fatal.
- Internal plan (opus): approve-with-fixes. Fixed: non-object `stack`, `detecting` refused, resolver exit code kept, narrow analyze error handling, unresolvable hint warned, plugin-layout test for the project writers. Rejected: `source` required (kept optional for legacy name-only callers; the one production caller passes it); renaming `user-hint` (pre-existing 1.0 value, documented instead).
- External plan (GLM, GPT): revise. Fixed: provenance in the miss message, legacy 1.0 snapshots resolve by name through the current resolver (the drift check applies only when a source was recorded), warnings printed by the analyze CLI, consumer audit done first (PR body). Architecture review: both approve.

## Trust (D8c)

A project-sourced match is marked `source: project` in the snapshot and the adopt result, with `shadows` and the shadow warning. Adopt runs no profile commands.

## Review dispositions (fix round 1)

- Code + doubt (opus): `write-project-config.py` without `--project-root` used `<project>/.shipwright` as the root, so a project profile exited 4 on the real Step-7 call path. Fixed by decoupling two roots: the profile LOOKUP root defaults to the parent of `.shipwright` when `planning_dir.parent` is named `.shipwright` (checked on the unresolved path, so a linked `.shipwright` works); the WRITE root (config location, gitignore merge, artifact checks, recorded `planning_dir`) is unchanged from before S3. Round 2 (doubt): an earlier version moved the write root too; reverted, because a config at `<project>/shipwright_project_config.json` from the early `detecting` call would overwrite an adopted repo's config and activate the Stop/Post hooks (`is_shipwright_project()`) during Steps 1-6. The pre-existing defect that the config lands under `<project>/.shipwright/` when only `--planning-dir` is passed is a separate issue, left unchanged on purpose and listed as a follow-up in the PR body. A snapshot without `profile.matched` and an incomplete install (missing schema) no longer fall back to `generic`. A missing shared tree is an install error (exit 1), not a bad name (exit 4). `.shipwright/triage.jsonl` was removed from the commit.
- Exit codes of `generate_adoption_artifacts`: 2 means both "snapshot not found" and the resolver's `not_found` for the selected profile; 3 is invalid/drift. Callers must read stderr to tell the two exit-2 causes apart.
- `shared/tests/test_setup_writes_canonical.py`: 5 failures (CI=true, one root) reproduce identically on a clean checkout of origin/main 59e822f3d (temporary worktree), so they are not caused by this diff.
- Accepted/handed off: `_scaffold_env_local` (S2) still resolves after the run config is written and reports `action: error` without aborting; the matcher filters one resolver warning by its message suffix (pinned by a test).
