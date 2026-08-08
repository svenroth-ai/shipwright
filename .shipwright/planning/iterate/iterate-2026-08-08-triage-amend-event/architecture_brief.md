# Architecture Brief: triage store `amend` event

## The problem

Correcting a triage card's title, description, severity, or category today
requires dismissing it and filing a new one, which mints a new id and breaks
any cross-reference to the old one. Measured over three days: roughly 30
cards were dismissed and re-filed for content-identical corrections, one
wave alone 23 cards / 46 events, on a premise that later turned out wrong.
No data was lost — the dismissed cards remain in the log as a history — but
the churn cost time and left the board's dismissed pile half full of
"retitled" entries that just point at another card.

## What already exists here

- The store (`.shipwright/triage.jsonl`) is a git-tracked, append-only JSONL
  log with `merge=union` plus its own dedup pass, which is what lets many
  concurrent branches write to it without conflicts.
- It already has one "correction-shaped" event: `status`, which flips a
  card's open/dismissed/promoted/snoozed state without minting a new id.
  Every module that treats a card as a live record (corruption detection,
  the outbox delivery sweep, main-branch sync, garbage collection) already
  has to reason about `status` events layered on top of the original card.

## What would newly, permanently exist

A third event kind, `amend`, alongside the existing `append` and `status`.
It corrects a card's content fields in place (id stays stable) rather than
superseding the card. Every module listed above that already reasons about
`status` events gains matching logic for `amend` events, since a shape only
some of them recognize is a shape that reads differently depending on which
part of the system looks at it. This is a permanent addition to the wire
format every current and future producer/consumer of this log must know
about, not a one-off script.

## Options on the table

- **A:** Add `amend` as a third event kind in the existing store, resolved
  by the same reader that already resolves `status` events.
- **B:** A separate, dedicated log file for corrections, read as an overlay
  on top of the existing store's output.
- **C:** Do nothing — keep dismiss-and-refile as the only correction path.

## Constraints that are not negotiable

- The store must stay append-only (never rewrite or mutate an existing
  line) — its git `merge=union` conflict-free-concurrent-write property
  depends on it, verified this week under roughly a dozen concurrent
  branches.
- Whatever is built must not touch the dismissed history already written —
  the ~30 existing supersede chains stay exactly as recorded.
