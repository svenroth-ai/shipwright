# Anchor or remove PR-review skip-safety for the 4 _GENERATED_PREFIXES entries

## Context

`is_safe_to_skip_review`'s `_GENERATED_PREFIXES` check (in
`plugins/shipwright-security/scripts/lib/pr_review_generated.py`) was a plain
directory-prefix match with no closed-set/canonical-path anchoring — unlike
the basename and review-evidence categories in the same function, which were
anchored after prior doubt-review findings closed the same class of gap.

A follow-up doubt review (Round 4 of
`iterate-2026-09-11-pr-review-evidence-filter-gap`) traced one prefix to a
concrete downstream consumer: `.shipwright/compliance/ci-security.json` is
read by `shipwright-compliance/scripts/lib/security_gate.py` as the pass/fail
oracle for a deploy-time PreToolUse gate, trusting the file's content with no
independent regeneration or provenance verification. The gap was no longer
only theoretical.

## Decision (per prefix)

- **`.shipwright/compliance/`** — removed from skip-safety entirely.
  `ci-security.json` alone is a live deploy-gate oracle; anchoring it to its
  own path would repeat the "exact path is not provenance" mistake Round 4
  already closed for `reviews.json`. Its siblings have no closed set either.
- **`.shipwright/agent_docs/iterates/`** — removed entirely, not merely
  anchored. A first draft anchored the filename to `<run_id>.json` /
  `<run_id>.test-results.json` (`RUN_ID_STRICT`-shaped, enforced at write
  time by the legitimate producer). Stage-3 doubt review disproved this: the
  shape is public and freely choosable by anyone, not a signature, and
  `plugins/shipwright-iterate/scripts/lib/complexity_history.py::
  load_history_prior` trusts any shape-valid file's `complexity`+`date`
  fields unauthenticated. Removed to match the `compliance/` treatment.
- **`CHANGELOG-unreleased.d/`** — anchored (kept skip-safe) to
  `<one of six ALLOWED_CATEGORIES>/<name>_<NNN>.md` (ASCII digits only,
  fixed after an external-review finding that unqualified `\d` also matches
  Unicode decimal digits). No identified downstream reader trusts drop
  content for a gate or automated decision; drops are aggregated into
  `CHANGELOG.md` by a human-run `/shipwright-changelog`. The disclosure
  comment was reworded (Stage-3 doubt review, medium) to state explicitly
  that a matching PR gets **zero review**, human or model — not merely
  "hidden from one review call" the way the `external-*review*` hide-side
  wildcard is.
- **`.shipwright/agent_docs/runtime/`** — removed. Gitignored and CI-gated
  never-tracked (`shared/tests/test_runtime_dir_gitignored.py`); granting
  skip-safety here was pure downside with no legitimate write to preserve.

## Consequences

A PR touching only compliance/iterates/runtime files now goes through one
real (if trivial) review call instead of an automatic skip; a CHANGELOG-only
PR keeps the automatic skip. `is_generated_path` (the hide-from-the-model
side) is unaffected throughout — these files are still excluded from what
the model sees, only the skip-the-gate-entirely decision changed.

`pr_review_generated.py` crossed the 300-line source guideline once this
fix's rationale comments were added (276 → 386 lines); split along the
`is_generated_path` / `is_safe_to_skip_review` consumer boundary into two
files, both back under 300 lines, per the code-reviewer's exact
recommendation.

## Rejected alternatives

Narrowing `.shipwright/agent_docs/iterates/` to a `RUN_ID_STRICT`-anchored
filename (kept skip-safe) was the first draft; rejected once
`complexity_history.load_history_prior` was identified as an unauthenticated
content-trusting consumer of exactly that shape — the same "filename shape
is not provenance" defect Round 4 already closed for `reviews.json`.

## Residual, deliberately out of scope

External code review found that both `is_generated_path` and
`is_safe_to_skip_review` normalize (`.strip()`) each changed path before
matching — a pre-existing pattern, not introduced by this diff, that could
in principle let a path differing only by leading/trailing whitespace from a
canonical skip-safe shape be misclassified. Filed as `trg-0eb7b587` rather
than fixed here: it is a repo-wide, pre-existing normalization choice
shared by both classifiers, not specific to the 4 `_GENERATED_PREFIXES`
entries this iterate's stated scope covers.

## Review cascade

self (disclosed one file-size gap) → spec (PASS) → code (PASS, 2 fixed
findings: the file split, a two-axis test) → doubt (2 findings, both fixed:
the iterates/ removal above, the CHANGELOG disclosure wording) → external
code (glm=approve, openai=revise, 2 fixed: ASCII-only counter regex, verified
no other importer of the removed `is_safe_to_skip_review` re-export).
