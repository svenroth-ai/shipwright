# Architecture Brief: outbox-only amend delivery signal

## The problem

A correction can appear in a local triage view although it has not reached a
branch. The status-delivery signal cannot describe a correction without changing
its meaning.

## What already exists here

- The listing reports buffered status decisions.
- The triage reader applies valid amendments as ordered overlays.

## What would newly, permanently exist

An additive v2 amend-delivery fact in the existing triage contract. The delivery leaf and
contract tests keep it correct.

## Options on the table

- **A:** Add a separate amend-delivery fact beside the status signal.
- **B:** Combine status and amend facts in the existing status signal.
- **C:** Keep the current envelope.

## Constraints that are not negotiable

The existing status signal remains semantically unchanged, and the separate
Command Center repository is not modified in this iterate.
