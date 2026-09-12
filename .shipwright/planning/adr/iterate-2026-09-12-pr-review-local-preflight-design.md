# Local PR-review preflight (`--base`/`--diff-file`)

## Context

`pr_review.py` is the required Tier-3 CI gate (FR-01.17). Three real PRs
(#725, #729, #742) were blocked on 2026-09-12 by findings this gate raised,
each costing a full push → CI → review round trip to learn about. The gate
itself is not the problem — it found three real defects in one day — the
problem is *when* the operator learns its verdict.

## Decision

Add a local preflight mode: `pr_review.py --base <ref>` (diffs the current
worktree against a merge base) or `--diff-file <path>` (reviews an arbitrary
pre-built diff), backed by a new `pr_review_local.py` module. It runs the
identical prompts, model and generated-file filter as CI, but is a
**preflight, never a waiver**: no PR comment, no review state, no dismissal
of stale verdicts, and nothing it writes is read by
`review_record_tier.decide()`. Wired into the iterate skill's F11
finalization step, right after `ensure_current.py`'s fetch (so the merge
base cannot be stale), before push.

Rejected alternative: narrowing the required CI gate to Tier-3/external-
contributor PRs only, so internal PRs skip straight to merge. Rejected
because the gate is the component that is working; the fix is running it
sooner, not less often — CI stays the sole required authority.

## Consequences

An operator gets the CI gate's verdict before pushing, at the cost of one
extra local step (skippable — it degrades to advisory-only if
`OPENROUTER_API_KEY`/model transport is unavailable, but a malformed
invocation or an unresolvable `--base`/`--diff-file` still STOPs, per
`EXIT_USAGE`). `--diff-file` sends its target file's content to the model
verbatim, so an operator must never point it at a file that may hold a
secret — documented in the module's own docstring.

## Rationale

The private-temporary-index diff technique (`GIT_INDEX_FILE` → a scratch
index, `git read-tree <merge-base>` + `git add -A`, then
`git diff --cached`) is the same one F0's diff-coverage gate already uses —
reused here rather than duplicated as a shared import, to avoid coupling
`shipwright-security` to `shipwright-iterate`'s F0 internals (cross-
referenced in both docstrings). This makes untracked files reviewable
without touching the operator's real index or HEAD.

## Details

Full review cascade (internal spec-reviewer/code-reviewer, external
GLM+OpenAI code and architecture review), every finding raised and how it
was addressed or dismissed, and the F0.5 dogfooding run that caught a real
F11 shell gap, are recorded in
[iterate-2026-09-12-pr-review-local-preflight.md](../iterate/iterate-2026-09-12-pr-review-local-preflight.md).
