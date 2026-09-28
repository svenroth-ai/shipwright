# Architecture Brief: architecture-review-internal-arm

## The problem

Both `/shipwright-plan` and `/shipwright-iterate` ask, via two external LLMs,
whether a change should be built at all and what the smallest thing that
would do is. That question is asked only when external review is available,
configured, and not declined by the operator — if any of those is false, the
architecture question is simply never asked for that run. The plan-soundness
question has an equivalent internal-first reviewer that closes this same gap
already; the architecture question does not.

## What already exists here

- An external, two-LLM "architecture review" call (`external_review.py
  --mode architecture`) that already runs, but only inside the branch where
  external review is available.
- An internal, single fresh-context reviewer ("Internal Plan Review") that
  already asks the plan-soundness question unconditionally, before any
  branching, on both `/shipwright-plan` and `/shipwright-iterate`.
- A review-record system (`reviews.json`, a closed but additively-growable
  set of review types) that a downstream compliance gate reads to confirm
  every review pass answered, one way or another.

## What would newly, permanently exist

A second internal, fresh-context reviewer — separate from the existing
Internal Plan Review reviewer — asking only the architecture question, over
a short brief (not the plan), running unconditionally before branching, on
both `/shipwright-plan` and `/shipwright-iterate` (medium+ only there). Its
outcome is recorded as an additional member of the existing review-type set,
so the same downstream gate can confirm it ran. It reuses the existing
review-model configuration dial rather than adding a new one. It has no
transport under the alternative (non-Claude) driver yet — that stays
unsupported until a follow-up.

## Options on the table

- **A:** A separate, dedicated fresh-context reviewer for the architecture
  question, additive review-type member.
- **B:** Extend the existing plan-soundness reviewer to ask both questions in
  one pass, over the plan plus a short list of alternatives.
- **C:** Record the outcome only in the change's own written record (a
  section, no new review-type member) rather than in the review-record
  system, mirroring how the external architecture call itself is recorded.
- **D:** Do nothing — leave the question asked only when external review
  happens to run.

## Constraints that are not negotiable

None.
