# Architecture Brief: changelog-release-notes

## The problem

Every tag `/shipwright-changelog` creates and pushes gets no visible release
page: clicking the tag on the code host shows only a one-line commit message,
never the change history for that version. This has been true for every
release so far (40+ tags), so nobody looking at the project's release history
from the outside — a user deciding whether to upgrade, a contributor
scanning what shipped — can currently do so without opening the repository
and reading `CHANGELOG.md` directly.

## What already exists here

- `/shipwright-changelog` already writes a Keep-a-Changelog section per
  version to `CHANGELOG.md` (Step 4), and tags + pushes the release (Step 6/7).
- The framework already makes one-shot LLM calls outside the Agent-tool
  subagent mechanism for review/judgment tasks (the external-review call used
  in this very iterate).
- The framework already has a "producer writes a derived artifact, a
  mechanical check gates it before anything downstream consumes it" pattern
  elsewhere in this plugin (the aggregator's MSYS-mangling linter, the
  manifest-sync verify-commit step).

## What would newly, permanently exist

A step in the release flow that reads the just-tagged CHANGELOG section,
produces a condensed human-readable summary of it, and publishes that summary
as a release page on the code host — running once per release, from now on.
Whoever maintains `/shipwright-changelog` going forward is responsible for
keeping this step correct (e.g. if the code host's release-notes size limit
or link-rendering rules change).

## Options on the table

- **A:** Publish a release page whose body is condensed from the CHANGELOG
  section by an automated summarization step, gated by a mechanical check
  before publishing.
- **B:** Publish a release page whose body is the CHANGELOG section verbatim
  (no condensation).
- **C:** Do nothing — leave release pages as bare tags; readers keep going to
  `CHANGELOG.md` directly.

## Constraints that are not negotiable

- The code host's release-body size limit (~125,000 characters).
- No backfill for already-published tags (operator decision, out of scope
  for this change regardless of which option is taken).
