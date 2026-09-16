# Task: stop normalizing whitespace in `is_generated_path`

Small-complexity CHANGE. No iterate spec file exists at this complexity (per
the phase matrix); this file stands in as the spec for review purposes.

## Context

`is_generated_path` in `plugins/shipwright-security/scripts/lib/pr_review_generated.py`
decides whether a file path in a PR diff is a producer-generated artifact and
should be hidden from the reviewing model (it does NOT decide whether the
PR-review gate can skip review entirely — that's the stricter sibling,
`is_safe_to_skip_review` in `pr_review_skip_safety.py`).

`is_safe_to_skip_review` used to `.strip()` its input before matching, which
let a real, distinct on-disk path differing only by leading/trailing
whitespace from a canonical shape borrow that shape's classification. That was
fixed on a prior iterate (PR #746). `is_generated_path` had the identical
`.strip()` call and was never fixed to match — this iterate closes that gap.

## Acceptance

1. `is_generated_path` no longer `.strip()`s its input before matching against
   `_GENERATED_PREFIXES` / `_GENERATED_AGENT_DOCS` / `_GENERATED_BASENAMES` /
   the review-evidence regexes.
2. No other classification logic changes (no widening/narrowing of the actual
   match rules); `is_safe_to_skip_review` itself is untouched (already fixed).
3. A regression test proves whitespace-variant paths are no longer
   misclassified as generated, covering `is_generated_path` called directly.
4. (Discovered during Stage-2 code review, then investigated and scoped in):
   `is_generated_path`'s one real production caller,
   `pr_review_diff_filter.filter_generated_paths` (via `_clean_diff_path`),
   is checked for whether it re-normalizes whitespace upstream in a way that
   would defeat (1) at the real call site. Investigation found the real call
   path is NOT vulnerable end-to-end even before this fix, because
   `filter_generated_paths` requires *every* path `_section_paths` collects
   for a section — including the `diff --git a/X b/X` header line's own
   capture, independent of `_clean_diff_path` — to classify as generated
   before excluding it, and a non-rename file whose name ends in whitespace
   already leaks that padding onto the header's `a/`-side capture. See
   `plugins/shipwright-security/tests/test_pr_review_generated_no_strip.py`'s
   module docstring for the full trace.
   `_clean_diff_path`'s own blanket `.strip()` was narrowed anyway (to
   `.rstrip("\r")`, its one legitimate purpose — CRLF diffs) since it served
   no other purpose, as a hardening measure, not because it was an active
   end-to-end vulnerability.

## Out of scope

- Widening or narrowing `_GENERATED_PREFIXES` / `_GENERATED_AGENT_DOCS` /
  `_GENERATED_BASENAMES` / the review-evidence regexes.
- Anything in `is_safe_to_skip_review` (`pr_review_skip_safety.py`) — already
  fixed on a prior iterate.
- `_DIFF_GIT_RE`'s own trailing-whitespace-eating behavior on its `b/`-side
  capture — investigated, found to be harmless given the "every collected
  path must be generated" exclusion rule, and out of scope for this narrow
  fix.
