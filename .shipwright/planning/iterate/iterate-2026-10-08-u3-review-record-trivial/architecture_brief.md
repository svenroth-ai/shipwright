# Architecture Brief: review record enforced at trivial / all-not_run

## The problem
A finished change can show every review as "not run" and still pass finalization: at small the
gate accepts any free-text excuse, and at trivial it does not look at the review record or the test
ledger at all. So "nobody reviewed this" and "a reviewed trivial change" look the same afterwards.

## What already exists here
- The per-run review record (`reviews.json`) and its F11 gate, which already refuses unanswered
  passes and, at medium+, a record where no code review happened.
- A closed reason-code vocabulary (`review_not_run` family, incl. `trivial-auto`) that rows MAY carry.
- The Test Completeness Ledger gate, enforced from small up, skipped at trivial.

## What would newly, permanently exist
Nothing new stands up. The existing gates start applying at every complexity: the Self-Review row must
be completed, every skipped pass must carry a code from the existing vocabulary (one default code at
trivial), and the trivial ledger is a recorded default row instead of a skip. One code is added to the
vocabulary for campaign-runner passes that have no place to run.

## Options on the table
- **A:** tighten the existing gates as above (self required everywhere, codes required everywhere).
- **B:** require codes only from small up; keep trivial skipped.
- **C:** do nothing; keep free-text dispositions and the trivial skip.

## Constraints that are not negotiable
The `reviews` object is a cross-repo contract: every known review type must stay present in the
record, so "one row instead of seven" cannot remove keys. Already-merged records are never re-verified.
