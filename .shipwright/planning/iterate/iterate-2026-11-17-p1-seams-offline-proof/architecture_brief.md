# Architecture Brief: offline seams for the changelog release path

## The problem
The release scripts call `gh` and a hosted model directly, so no test can run a whole release without a network, a GitHub login and an API key. The planned golden-trace harness needs to run them offline, and a stray test variable must never be able to publish fake notes to a real release page.

## What already exists here
- `shared/scripts/repo_identity.py`: a top-level shared helper consumed by both a plugin and the shared tools.
- `SHIPWRIGHT_TEST_DISABLE_OSS_SCANNERS`: a test env variable set in conftests.
- Tests patch `subprocess.run` / `_run` in-process; that cannot cover a real spawned process.
- The release audit already spawns `uv run --with pyyaml`.

## What would newly, permanently exist
One small stdlib module that reads two `SHIPWRIGHT_TEST_*` variables, plus a refusal in `create_github_release` for fixture-marked notes. Tests keep it correct (one test scans that nothing else reads the variables).

## Options on the table
- **A:** An environment-variable argv prefix for `gh` and a fixture-model switch, read in one shared module.
- **B:** Test-only dependency injection (pass a runner object into each script).
- **C:** Do nothing; mock `subprocess.run` per test.

## Constraints that are not negotiable
Every default path must stay byte-for-byte unchanged; on Windows `gh` is spawned as `["gh", ...]`.
