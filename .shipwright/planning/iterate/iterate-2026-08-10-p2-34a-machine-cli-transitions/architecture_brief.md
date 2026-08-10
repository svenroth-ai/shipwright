# Architecture Brief: machine-callable triage transitions

## The problem

Two applications currently implement triage writes. A stale status check can
therefore be accepted by one writer after the other has changed the card.

## What already exists here

- Python CLI commands and a locked append-only triage store.
- A Command Center that reads the resolved store state natively.

## What would newly, permanently exist

A documented JSON-and-exit-code CLI contract for the existing transition
commands. It adds no service, store, lock primitive, or new persisted format.

## Options on the table

- **A:** Make the existing Python CLI the machine-callable writer.
- **B:** Make the Python and TypeScript lock primitives interoperate.
- **C:** Keep the two writers.

## Constraints that are not negotiable

The WebUI stays out of scope; existing human CLI behavior remains compatible.
