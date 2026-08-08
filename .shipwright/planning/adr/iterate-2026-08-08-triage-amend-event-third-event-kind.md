# A third append-only event kind for the triage store

## Context

`.shipwright/triage.jsonl` is append-only with two event kinds: `append`
(mint a card) and `status` (flip its status). There was no way to correct a
card's `title`/`detail`/`severity`/`kind` in place — the only recourse was
dismiss-and-re-file, which mints a new id and breaks any cross-reference to
the old one. Measured over 2026-08-05/07: ~30 cards dismissed and re-filed
for content-identical corrections (one wave alone: 23 cards / 46 events), on
a premise that later turned out wrong — pure churn, no data loss, but real
friction and history noise. Full problem statement, design decisions, and
acceptance criteria: `.shipwright/planning/iterate/2026-08-08-triage-amend-event.md`.

## Decision

Add a third append-only event kind, `amend`
(`{"event":"amend","id":"trg-x","title":"...","detail":"...","severity":"...","kind":"...","by":"...","ts":"..."}`),
folded into `read_all_items`'s existing second pass — the SAME pass that
already applies `status` events, resolved together by `(ts, file-order)`,
never a separate third pass. A field absent from an amend line leaves the
corresponding stored field untouched; a field PRESENT but invalid (e.g. an
unknown severity) invalidates the whole event — skip whole, never half,
mirroring the existing convention for a damaged `status` event. The store
stays append-only and mutability is never reintroduced: its git-tracked,
`merge=union` + triage-specific dedup design is what let ~12 concurrent
worktrees write to it in the same week with zero conflicts, and a mutable
file would reintroduce the N(N-1)/2 collision class `DERIVED_SNAPSHOTS`
exists to prevent.

Internal Opus review, external plan review (openai/deepseek), and a
dedicated architecture-mode call (openai/deepseek, both `approve`) all
independently confirmed this — a third append-only event kind in the
existing store — as the smallest design that would do.

## Consequences

Every current and future consumer of the store must now recognize `amend`,
mirroring the obligation `status` already imposes — both architecture
reviewers named this explicitly as the permanent cost. This iterate makes
`triage.py` core + schema, `triage_integrity`, `triage_validate` +
`triage_gc_core`, `sweep_quarantine`, `sweep_drift_events`, and `triage_cli`
amend-aware; a future consumer that reads the store's raw event stream
without going through `read_all_items` (or without a review that checks it
against this list) can silently mishandle an `amend` line.

Two follow-ups were deliberately deferred rather than expanded into this
iterate's scope, and are recorded on triage card `trg-d5ef8039`:
1. **Delivery-visibility parity** — a buffered-but-undelivered `amend` has
   no dedicated visibility key yet (`pendingAmendDelivery`/
   `undeliveredAmends`), unlike an undelivered `status` flip. Widening the
   existing `undeliveredDecisions` key was rejected: it would silently
   miscount an item carrying both a buffered status flip and a buffered
   amend (set union collapses to one signal), and the Command Center WebUI
   is a confirmed reader of that exact key today. As a cheap interim
   mitigation, the CLI's own `amend` success message now notes when the
   write landed in the local outbox rather than a tracked branch
   (Stage-3 doubt review, finding 1).
2. **WebUI TypeScript reader parity** — `shipwright-webui` (a separate
   repo) has its own triage reader with a committed parity fixture; it must
   learn to recognize `event:"amend"` the same way `read_all_items` does,
   or a card corrected via the CLI renders stale pre-amend content in the
   Command Center until that ships. **This repo has no visibility into that
   reader's actual behavior on an unrecognized event kind** — asserting it
   "degrades gracefully" without reading that code would be an unverified
   claim, so it is recorded as an open question on `trg-d5ef8039` rather
   than assumed.

**Plugin-cache staleness risk (Stage-3 doubt review, finding 2 — rebutted,
not code-fixed).** A stale cached copy of `sweep_drift_events.py` — one
still missing `"amend"` from its recognized-event set — would jam the
ENTIRE outbox delivery pipeline for every event kind, not only `amend`,
since the sweep cannot classify past the first unrecognized line. This is
not a new risk this diff introduces: `CLAUDE.md`'s "When editing plugin-side
files" section already makes `scripts/update-marketplace.sh` +
`check_plugin_cache_sync.py --strict` a standing, mandatory step after every
`shared/scripts/` push, citing a prior staleness incident by name ("cost
iterates 7-11 their fixes"). This diff relies on that existing gate rather
than weakening or bypassing it; what changes is only that the specific
failure shape (a stale sweep jams ALL delivery) is now named, so its stakes
are legible to whoever next skips the sync step.

## Rationale

Option A (a third append-only event kind, folded into the existing
resolution pass) keeps the store's proven concurrency properties, reuses
every existing consumer's `(ts, file-order)` resolution contract instead of
inventing a new one, and mirrors the `status` event's own precedent
end-to-end (residence routing, lock discipline, validation-before-I/O,
schema `oneOf` branch, corruption-boundary recognition, orphan/protected
classification, quarantine reasons). Four independent review rounds
(internal Opus, external plan review ×2 providers, a dedicated architecture
call ×2 providers, and a post-implementation Stage-2 code review) surfaced
real, distinct issues at each stage and converged rather than fatigued — the
architecture round returned zero findings from either provider.

## Rejected alternatives

- **A mutable field update** (rewrite the stored item in place) — reintroduces
  the concurrent-write collision class the append-only design exists to
  prevent; rejected outright by both architecture reviewers.
- **Dismiss-and-re-file, kept as the only correction path** — the status
  quo; rejected because it was the measured problem (pure churn, broken
  cross-references, ~30 cards/week).
- **Widening `undeliveredDecisions` to also cover amends** — rejected per
  the Consequences section above (silent miscounting when an item carries
  both a buffered status flip and a buffered amend; a confirmed WebUI reader
  of the existing key).
- **A separate third resolution pass for `amend`, distinct from `status`'s**
  — rejected: it would let `amend` and `status` disagree about ordering
  semantics for no benefit, and every consumer would need to learn two
  resolution passes instead of one.
