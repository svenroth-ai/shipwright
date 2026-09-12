# iterate-2026-09-12-generated-prefixes-provenance-anchor

## Intent

`is_safe_to_skip_review`'s `_GENERATED_PREFIXES` check (in
`plugins/shipwright-security/scripts/lib/pr_review_generated.py`, since split
into `pr_review_skip_safety.py`) was a plain directory-prefix match with no
closed-set/canonical-path anchoring — unlike the basename and review-evidence
categories in the same function, which were anchored after prior doubt-review
findings closed the same class of gap.

A follow-up doubt review (Round 4 of
iterate-2026-09-11-pr-review-evidence-filter-gap) traced one prefix in this
set to a concrete downstream consumer: `.shipwright/compliance/ci-security.json`
is read by `shipwright-compliance/scripts/lib/security_gate.py` as the
pass/fail oracle for a deploy-time PreToolUse gate, trusting the file's
content with no independent regeneration or provenance verification. The
classification gap was no longer only theoretical.

## Scope

For each of the 4 `_GENERATED_PREFIXES` entries, either anchor it to its
real, closed, write-time-enforced shape (and confirm no content-trusting
consumer exists for that anchored shape), or explicitly remove it from
skip-safety and disclose why — following the pattern
iterate-2026-09-11-pr-review-evidence-filter-gap used for its own categories,
starting with the prefix that has a confirmed consumer.

## Decisions (per prefix)

- `.shipwright/compliance/` — REMOVED entirely. `ci-security.json` alone is a
  live deploy-gate oracle; anchoring it to its own path would repeat the
  "exact path is not provenance" mistake Round 4 already closed for
  `reviews.json`. Siblings have no closed set either.
- `.shipwright/agent_docs/iterates/` — REMOVED entirely (not merely
  anchored). A first pass anchored the filename to `<run_id>.json`/
  `<run_id>.test-results.json` (RUN_ID_STRICT-shaped, enforced at write time
  by the legitimate producer). Stage-3 doubt review disproved this: the
  shape is public and freely choosable by anyone, not a signature, and
  `plugins/shipwright-iterate/scripts/lib/complexity_history.py::
  load_history_prior` trusts any shape-valid file's `complexity`+`date`
  fields unauthenticated. Removed to match the compliance/ treatment.
- `CHANGELOG-unreleased.d/` — ANCHORED (kept skip-safe) to
  `<one of six ALLOWED_CATEGORIES>/<name>_<NNN>.md`. No identified
  downstream reader trusts drop content for a gate or automated decision;
  drops are aggregated into `CHANGELOG.md` by a human-run
  `/shipwright-changelog`. Disclosure reworded (Stage-3 doubt review,
  medium) to state explicitly that a matching PR gets zero review, human or
  model, not merely "hidden from one review call".
- `.shipwright/agent_docs/runtime/` — REMOVED. Gitignored and CI-gated
  never-tracked (`test_runtime_dir_gitignored.py`); granting skip-safety was
  pure downside.

## Out of scope

Real cryptographic/provenance validation of review-evidence or iterate-
record content (verifying a file was actually produced by the tool, not
merely path/shape-conforming) is a materially larger change and not
attempted here — consistent with the Round 4 precedent for `reviews.json`.
