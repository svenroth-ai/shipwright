# Architecture Brief: autonomous release merge picks its method, pins the head, stops when the base moved

## The problem

An autonomous `/shipwright-changelog` release merges its own release PR with a merge commit, which fails on a
repository that allows only squash merges (this one). Under squash or rebase, commits another PR merged into the
base after the release branch was made would land in the release without their changelog entries, and a commit
pushed to the release branch after the audit would be merged unaudited.

## What already exists here

- `release.py push-tag` already answers which literal push line to run (or why none); the push stays one literal line in SKILL.md so the release guard hook sees it.
- After a squash or rebase merge, push-tag proves the merge commit carries exactly the release and stops with `foreign_commits_on_base` otherwise (unit U3).
- The release guard hook judges any `gh pr merge` of the release by HEAD (the release or its event commit).
- The `gh` test stub (frozen harness file) merges by merge, squash or rebase into a local bare remote.

## What would newly, permanently exist

A new `release.py merge-ready` subcommand that reads the repository's merge settings and the PR head, and returns the
one merge line to run (method + pinned head) or a refusal reason; before a squash or rebase it checks whether the base
moved. The changelog plugin's tests and SKILL.md keep it correct. The test stub learns to report merge settings and
honour a head pin.

## Options on the table

- **A:** a `merge-ready` decision call that prints one literal merge line (method from settings, head pinned), stopping before a squash/rebase when the base moved.
- **B:** always `--squash` with a head pin, no settings read, no base check (push-tag's proof catches foreign commits after the merge).
- **C:** update the release branch from the base automatically, then merge.
- **D:** do nothing: autonomous releases keep `--merge`; squash-only repositories release in guided mode only.

## Constraints that are not negotiable

- Operator decisions 2026-11-28: squash and merge commit must both work, merge commit preferred; always pin the head; a release branch behind the base before an autonomous squash or rebase stops, nothing merged, no automatic re-creation; never change repository settings.
- Outward commands stay one literal line in SKILL.md so the release guard hook sees them.
