# Architecture Brief: affected_acs on iterate events

## The problem
Iterates that change runtime behaviour often record "no spec impact" without saying which acceptance criteria they looked at, so promises can be lost unnoticed in a later rebuild.

## What would newly, permanently exist
One new optional-then-required event field plus one presence-only finalization check and a read-only replay tool. It adds no data store and writes nothing new.

## Options on the table
- **A:** a presence-only finalization check on a new event field.
- **B:** a write-time refusal at the finalize step when the field is absent.
- **C:** do nothing; rely on reviewers reading the diff.

## Constraints that are not negotiable
Nothing may hold a PR on the content of the declaration; the existing finalization check list file is at its size cap.
