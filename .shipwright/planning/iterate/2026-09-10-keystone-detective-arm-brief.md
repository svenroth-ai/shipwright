# Architecture Brief: keystone gate post-merge detective arm

**Question: should this exist at all, and at this scope?**

## Context

The keystone AC gate (P3.6, merged PR #702) is a preventive, pull_request-only CI check: it
blocks a PR if a changed acceptance criterion's bound test isn't green, but ONLY on the
pull_request event, and it trusts its own same-run local regeneration of the traceability
manifest. Its own design doc disclosed two limitations at merge time and filed them as triage
cards rather than building them in-PR: (1) a direct push to the default branch bypasses it
entirely, (2) nothing re-checks, after the fact, whether a commit that reached `main` actually
satisfied the gate using evidence nobody could have forged for that specific commit.

Card `trg-a05c4aba` (ruling Q5) asks for a "complementary DETECTIVE control" that composes with
`resolve_ci_verification`/`resolve_execution_evidence` (the two existing cross-commit
unforgeability predicates already built for a different consumer, P3.5's per-FR layer promotion)
rather than reusing the preventive gate's own same-run producer. The card explicitly warns
against shipping an "open-ended detective arm TBD" and demands the misclassification cases be
named up front.

## Proposed scope (full design: `2026-09-10-keystone-detective-arm.md`)

An advisory-only, non-blocking CLI + pure evaluator that, for a given commit, recomputes the
keystone gate's verdict using CI-VERIFIED per-test evidence instead of that commit's own
committed (self-reported) manifest bytes, and classifies the result into one of six named,
mutually-exclusive outcomes (two "no evidence yet" cases, two "query failed" cases, and
gate-violated / gate-confirmed-clean). Not wired into `ci.yml`. Not a Required Check. Composes
with two existing, frozen, already-reviewed modules without editing either.

## Why now, given the precondition (a real confirmed trunk run) does not hold on `main` today

The card itself says "scoped, not urgent" for exactly this reason. The counter-argument for
building it now anyway: (1) its correctness is independently verifiable via unit tests against
mocked resolver outputs, the same posture the preventive gate's own pure core has always used;
(2) shipping it now means it starts producing real, non-`error` findings the moment `main`'s
pre-existing structural drift (P3.6 design §2.3) is eventually fixed by unrelated work, with zero
lag; (3) the alternative — leaving the card open indefinitely — is the exact "TBD" shape the card
was filed to prevent.

## Alternative: don't build it yet; wait for the precondition to hold, then build

Rejected for the "why now" reasons above, but named as the honest alternative: this iterate's own
value is bounded today (it cannot demonstrate a real violation catch on this repo's current
history, since the precondition is unmet), so the return on building it now is "correct code
sitting inert" rather than "an active safety net." If the reviewer disagrees with the counter-
argument above, deferring is a reasonable call — this brief exists to surface that fork instead of
deciding it unilaterally.
