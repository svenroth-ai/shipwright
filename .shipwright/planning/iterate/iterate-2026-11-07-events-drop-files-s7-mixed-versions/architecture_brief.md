# Architecture Brief: mixed plugin versions around the per-run event drop layout

## The problem
Teammates run different plugin generations against one repo. A plugin that does not know a layout must not silently write the wrong one or stamp release evidence over a log it cannot read, and a PR must not keep appending to the legacy log once the repo moved to per-run drop files.

## What already exists here
- A dormant drops layout selected by a config key; readers that read both layouts; an integrity checker for the drop folders.
- `events_layout()` maps any unknown value to legacy.

## What would newly, permanently exist
A small stdlib-only sentinel module consulted at the one write choke point and by two evidence producers, a merge-base-judged CI check script, and a conditional gitignore re-include.

## Options on the table
- **A:** sentinel at the write choke point + evidence refusal + merge-base CI check (as described).
- **B:** do nothing: rely on every teammate updating when the flag flips.
- **C:** make `events_layout()` itself raise on an unknown value (affects every reader too).

## Constraints that are not negotiable
Legacy-layout bytes and behaviour unchanged while no drops exist; a PR opened before the flip is never failed; a rollback must never lock the repo out of writing events.
