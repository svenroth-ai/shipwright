# Architecture Brief: compaction-state-audit

## The problem
An autonomous iterate run's in-flight state can be silently lost to
context-window auto-compaction: a small-complexity plan exists only in
conversation, a reviewer's findings can sit unwritten between the reviewer
returning and the record being made, and resuming an interrupted run only
checks two coarse signals instead of the fuller review record already on
disk.

## What would newly, permanently exist
Nothing. This changes when and how existing machinery is used: the
already-existing mini-plan file convention now applies at one more
complexity tier, the already-existing `reviews.json` review record (and its
existing `record_review_pass.py` reader/writer) is read by two more
existing consumers (B1's resume check, the handoff renderer) that
previously did not look at it, and existing skill prose is tightened with
an explicit ordering instruction.
