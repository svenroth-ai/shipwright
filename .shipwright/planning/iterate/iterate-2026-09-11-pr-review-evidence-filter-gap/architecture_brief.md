# Architecture Brief: pr-review-evidence-filter-gap

## The problem
The PR-review gate's own filter for "prior-review transcripts a reviewer
should never see" misses several file-naming shapes that this repo's review
tooling actually writes, so the automated reviewer is sometimes fed the raw
text of an earlier review pass instead of the code diff.

## What would newly, permanently exist
Nothing. This widens the matching in an existing filter function
(`_REVIEW_EVIDENCE_RE` in `pr_review_generated.py`) that already exists to
solve exactly this problem for one file shape (`reviews.json`).
