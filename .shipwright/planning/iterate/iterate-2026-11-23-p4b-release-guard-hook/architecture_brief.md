# Architecture Brief: release guard before push, merge and release page

## The problem

A release run (`release.py prepare` ... `commit-and-tag` ... `record-event`) is a chain the model drives step by step. In the full-run report, models pushed tags and the trunk (`git push --tags origin main`, `git push origin HEAD`) and ran `gh pr merge` while the verified release commit and tag did not exist or did not match HEAD. Code in `release.py` now makes each step safe, but nothing stops the model from skipping a step and running the outward command by hand.

## What already exists here

- `release.py commit-and-tag` writes `.shipwright/runtime/release_state.json` (version, release commit, checks passed); `release.py prepare` writes `release_run.json` in the git directory.
- The skill prose says "stop if a step fails".
- Compliance has fail-open PreToolUse `Bash` gates (`check_rtm_coverage.py`, `check_security_scan.py`) and iterate has `bare_python_stdin_guard.py`.
- `close-phase` verifies the release read-only after the fact.

## What would newly, permanently exist

A PreToolUse `Bash` hook in the changelog plugin that reads the two files above and refuses `git push` of a tag or trunk, `gh pr merge` and `gh release create` while a release is in progress and the record for HEAD is missing. It runs on every Bash call of a session that has the changelog plugin; the plugin keeps its command matcher correct.

## Options on the table

- **A:** A PreToolUse hook in the changelog plugin, inert unless a release is in progress.
- **B:** Make the skill prose and `close-phase` stricter and rely on the model following them.
- **C:** Move the outward commands into `release.py` (a `publish` subcommand) so the model never types them, and leave the hook out.
- **D:** Do nothing.

## Constraints that are not negotiable

An ordinary `git push` and a hook bug must never block a user (fail open). The release record written by P4 is the only source of truth for "verified".
