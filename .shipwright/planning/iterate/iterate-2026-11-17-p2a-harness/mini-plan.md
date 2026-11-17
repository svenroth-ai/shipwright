# Mini-plan: P2a golden-trace harness (changelog pilot)

## Goal
Give the pilot a harness that runs a release scenario in a scratch project and records a normalized, comparable trace of what it left behind, so later units (P2b scenarios, P3-P5 conversion) can prove the conversion changed nothing. No product behaviour changes.

## Changes
1. `shared/testkit/gh_stub.py` (stdlib): stand-in for `gh` reached through the P1 argv-prefix seam; refuses and acts per the brief contract (`pr create` needs the head on the remote, `pr merge` really merges and deletes the head, `release create` needs the tag on the remote and persists, `release view` then answers); every call, refusals included, goes to an argv log.
2. `shared/testkit/release_scratch.py` (stdlib + `minimal_valid_project`): scratch project = phases + git + bare origin (fake GitHub fetch URL, file push URL) + stub state dir; `build_env` builds the environment from an allowlist (no keys, no `SHIPWRIGHT_ROOT`, `GIT_ALLOW_PROTOCOL=file`) and `assert_no_secrets` fails on any secret-shaped name.
3. `shared/testkit/golden_trace.py` (stdlib): `collect` (commits, refs, status, whitelisted step output, argv log; SHAs, timestamps, paths normalized; judgement output masked), the per-step `Driver` interface with `CompositeDriver` and `run_scenario`, and the freeze check (`freeze_problems`: sha256 lock plus approved deltas).
4. `plugins/shipwright-changelog/tests/golden/`: `conftest.py` (fixtures, step list), `test_trace_freeze.py` (freeze of the real tree: no lock = unfrozen; synthetic-tree cases; a driver smoke test).
5. Unit tests in `shared/tests/` for each helper; one docs paragraph in `docs/hooks-and-pipeline.md`.

## Not done
No scenarios, no replay driver, no lock file (P2b, P2-op). No product code touched.

## Alternative approach considered
Folding scratch building into the P1 offline proof test: rejected because P2b and P2p need the builder from two test roots and the stub from a spawned process.
