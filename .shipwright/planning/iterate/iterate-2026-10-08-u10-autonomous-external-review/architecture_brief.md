# Architecture Brief: autonomous external review that cannot run must say so, loudly

## The problem

An autonomous run (a campaign sub-iterate, no operator to ask) sometimes cannot run the external
LLM review — the provider errors, every reviewer returns a degraded reply, or the tool itself fails
to start. Today the pass is closed "not run" and the run carries on; nothing proves the reviewer
actually failed rather than being skipped, and nothing reminds the operator afterwards that a merged
change went without its external review.

## What already exists here

- A per-run review record (`reviews.json`) with a closed reason-code vocabulary; `unavailable` is
  already one of the codes, and F11 already refuses a skipped row with no code at all.
- `external_review.py` writes its JSON reply (or a failure / degraded envelope) to a canonical file
  per pass in the run directory.
- An F12 run summary and a PR body template that already carry per-run counters (exemptions).
- A triage store with an idempotent producer API; the external review already auto-files a card when
  ONE of its two reviewers degrades.

## What would newly, permanently exist

A rule in the F11 review-record check that an adapter-backed pass closed `unavailable` must have a
captured adapter-error artifact in the run directory (and in the commit); a small tool that prints
one summary line for the PR body / F12 and can file one re-run triage card per run. The verifier
suite and the existing review-record tests keep it correct.

## Options on the table

- **A:** require the artifact by convention (canonical file names already pinned per pass) and add
  the summary/triage tool.
- **B:** add an explicit artifact-path field to the review record and a CLI flag to set it.
- **C:** halt the autonomous unit whenever the external review cannot run.
- **D:** do nothing — keep `unavailable` as an unverified free choice.

## Constraints that are not negotiable

The operator decided the run MAY continue (no halt), must never continue silently (PR note, F12
line, triage card), and no environment-variable waiver may exist. Interactive behaviour must not
change. The review record schema is read by an external consumer (the WebUI).
