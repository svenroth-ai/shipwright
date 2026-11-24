# Architecture Brief: where the release's tag push and its branching live

## The problem
A release cut from a feature branch must push only its own tag, and only after the pull request is merged when a person invokes it;
on the trunk it pushes the trunk with the tag. Today a model reads this as prose and types the push; a model that misreads it can publish
a tag before the merge or push a local trunk. A hook (already built) blocks a literal push while a release is in progress.

## What already exists here
- A release CLI (`release.py`) with one subcommand per step; the run state (branch kind, mode) is kept between calls.
- A release guard hook that reads Bash commands and denies a tag or trunk push without a matching release record.
- `release.py record-event` already refuses a feature-branch release without a PR URL.

## What would newly, permanently exist
One more `release.py` subcommand that performs the tag push itself after reading the run state, plus the checks that make the same refusals the
hook makes (a recorded release, event-only HEAD on the trunk). The hook cannot see a push made inside the CLI.

## Options on the table
- **A:** a `push-tag` subcommand that decides and pushes.
- **B:** a subcommand that only decides (prints go / wait) and the push stays a literal line the hook sees.
- **C:** keep the push and its branching as prose.

## Constraints that are not negotiable
Frozen traces of the replay harness must not change; the driven-run flow pushes its tag with the PR open.
