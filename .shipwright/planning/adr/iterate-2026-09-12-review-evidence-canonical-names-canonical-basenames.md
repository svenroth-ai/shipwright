# Canonical review-evidence basenames per artifact kind

## Problem

Review-evidence files under `.shipwright/planning/iterate/<run_id>/` were
written with ad-hoc, per-run filenames chosen by each producer instead of one
canonical name per artifact kind. `iterate-2026-09-11-pr-review-evidence-filter-gap`
measured 40+ ad-hoc basenames for the same handful of kinds on `origin/main`,
which ruled out both a path-classifier wildcard (too loose) and an
exact-basename allowlist (can't keep up with new names) for the PR-review
classifier (`plugins/shipwright-security/scripts/lib/pr_review_generated.py`).
Filed as trg-3b206c08 by that iterate's doubt-reviewer.

## Decision

Give each review-evidence kind (self/spec/code/doubt/plan/external_code;
`plan_internal` excluded — it records no payload file) exactly ONE canonical
basename, in `shared/scripts/lib/review_payloads.CANONICAL_PAYLOAD_BASENAMES`.
`record_review_pass.py record` rejects (exit 2) any `--payload-file` whose
basename doesn't match, via `canonical_basename_error`. Every documented
producer site (standalone iterate, sub-iterate-runner, campaign-mode's 3f-bis
delegated cascade, and the SubagentStop salvage-hook fallback) redirects its
output to the canonical name.

`spec`/`code`/`doubt` reuse the exact names the classifier's own
`_REVIEW_EVIDENCE_RE_RUN_ANCHORED` already anchors to
(`(spec|code|doubt)_review_reply.json`) — unchanged by this dict, just finally
mandatory instead of a free-form "path to the reply". `self` keeps
`self-review-payload.json` (already established, deliberately never hidden
from a review). `plan`/`external_code` are new: `external-plan-review-raw.json`
/ `external-code-review-raw.json`, matching the classifier's own
`external-*review*-raw.json` example.

**Scope boundary, made explicit after Stage-3 doubt review:** the check is
basename-only, not directory-anchored. The classifier's hide rule is already
run-anchored on the full path; a future change extending its exact-path
allowlist to this family must keep enforcing the directory itself rather than
assuming this CLI check already covers it. Enforcing the directory here too
would require rewriting the fixture layout of ~10 test files (every existing
`payload()` test helper writes to a flat `tmp_path`, not a run-anchored one)
for a risk the classifier's own regex already covers on its side — judged out
of proportion for this change.

## SubagentStop salvage hook (`write-review-payload-on-stop.py`)

This hook backstops the spec/code/doubt cascade's orchestrator-writes-next
mandate against a compaction landing between a reviewer's return and that
write. It used to write a distinctly-named `{type}_salvaged_raw.json`
fallback file (`iterate-2026-08-09-compaction-state-audit`). It now writes
directly to the SAME canonical basename the orchestrator's own write targets,
via a hardcoded local `CANONICAL_BASENAME` mirror dict (the hook is
deliberately self-contained, no `shared/scripts/lib` import, to avoid an
ADR-044 `lib`-package collision with this plugin's own `scripts/lib`). A new
test (`shared/tests/test_review_payload_canonical_basenames.py`) pins the two
dicts equal and round-trips the hook's output into `record_review_pass.py
record` as an end-to-end proof — the boundary a code-review pass found
untested in the first draft.

A Stage-3 doubt review then found the direct-write change introduced its own
narrow risk: if the hook resolves a different project root than the
orchestrator's (`SHIPWRIGHT_PROJECT_ROOT` unset, stale cwd), it could now
plant a canonical-named stray in the wrong tree — one that collides with a
later `git` fast-forward, unlike the old distinctly-named file which was a
harmless leftover. Fixed with a `wrong_root()` guard: if `reviews.json` is
entirely absent under the resolved root, the hook refuses to salvage and never
creates the directory, since SKILL.md Step 7's `init` always creates
`reviews.json` before any of these three reviewers is ever spawned — so total
absence means "wrong tree", never "not yet recorded".

## Rejected alternatives

- **Widen the PR-review classifier's wildcard.** Rejected by the prior iterate
  (`iterate-2026-09-11-pr-review-evidence-filter-gap`) across 5 review
  rounds: too loose, would hide genuine attacker-supplied look-alike files.
- **Grow the classifier's exact-basename allowlist ad hoc.** Rejected for the
  same reason this trg exists: it cannot keep up with new producer-chosen
  names, which is exactly the problem being fixed at the source.
- **Enforce the run-directory path in `canonical_basename_error` too.**
  Considered and explicitly deferred (see Scope boundary above) — the cost
  (rewriting ~10 test fixtures) was judged disproportionate to a risk already
  covered by the classifier's own run-anchored regex.
- **Leave the salvage hook's old distinct filename in place.** Would have left
  the compaction-recovery path broken: a salvaged file under the old name is
  now unrecordable by the new CLI check, silently discarding a finding that
  should have survived a compaction (found by Stage-1 spec review; the actual
  fix chosen was to redirect the hook's write target instead of leaving the
  old name and requiring a manual copy step).

## Review record

Full internal cascade ran despite `small` classification (no risk flags
fired) per this repo's standing review-cascade grant: `spec-reviewer` REJECT
→ fix → PASS; `code-reviewer` PASS with 1 medium + 4 low findings, all
addressed; `doubt-reviewer` (Stage 3, `advisory-must-address`) raised 3 medium
+ 5 low doubts — the 3 medium doubts were all fixed with code changes (the
directory-boundary docstring clarification above, a defensive `mkdir -p`
before the standalone Step 4 Branch A external-review redirect so a degraded
Internal Plan Review no longer leaves the run directory missing, and the
`wrong_root()` guard); the 5 low doubts were addressed via small doc/test
fixes plus reasoned, documented deferrals (this ADR; a migration note at F4;
one low residual risk — a first-match `run_id` misroute to an existing-but-
different run — accepted as narrow and unmeasured in practice after the
dominant failure mode was already closed).
