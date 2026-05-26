# Step G — Layer-3 Review

Run `review_runner.run_review(...)` (from `scripts/lib/review_runner.py`).
Writes `.shipwright/adopt/review.md`. Without any API key, the review
documents `status: skipped, reason: no_api_key` — acceptable.

If the review returns HIGH/MAJOR findings about hallucinations or
contradictions, **AskUserQuestion**: `fix (re-run enrichment)` /
`accept with caveat` / `abort`.
