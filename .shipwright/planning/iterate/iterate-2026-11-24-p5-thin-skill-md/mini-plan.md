# Mini-plan: P5 thin SKILL.md, pins moved, F7 prose removed

## Goal
The changelog skill prose writes no run state in any mode and names no run-state writer; the tag push and its F1a/F1b/F4 branching
move into one CLI subcommand reading the run state; the P0.3 prose pins are mapped one by one; the P4 review's private-helper import is
replaced by a public wrapper.

## Changes
1. `SKILL.md` and four references: remove the `update-step` / `--restore` mentions and unit-history sentences (F7); Step 7 push becomes one `release.py push-tag` line.
2. `scripts/lib/release_push.py` + `release.py push-tag`: F1a (feature branch: only the tag; trunk: recorded branch + exactly this tag, HEAD moved only by event files), F1b (hand-invoked release from a feature branch: only once the release commit is on the PR's base on origin, else `waiting_for_merge` exit 1), F4 (refused push = its exit code). A driven run never merges its PR: no merge check.
3. `release_verify.on_base` extracted from the PR check so both use one ancestry test.
4. `shared/.../changelog_checks.check_release_tag` (public) used by `checks/verify_release_tag.py`.
5. Tests: in-process push-tag tests, prose test that fails on the old prose, public-entry boundary test, CLI driver replays `push-tags` through the CLI; pins in `test_skill_event_ships_in_release_pr.py` re-expressed.
6. Golden: approved deltas for the five prose files and `driver_cli.py`; live prose stays in `REQUIRED` (no re-pin).

## Risks
- The hook (P4b) cannot see a push made inside the CLI: `push-tag` repeats the record and event-only rules.
- A squash-merged hand-invoked release is refused by `push-tag` (release commit not on base).
