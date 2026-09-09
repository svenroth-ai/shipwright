"""Real PR #690 review-verdict fixtures (trg-ac24ec5b).

The exact bytes of the first two `PR Review` BLOCK comments on
svenroth-ai/shipwright PR #690 (`gh pr view 690 --repo svenroth-ai/shipwright
--json comments`), the run that motivated the non-converging halt: ten pushes,
twelve verdicts, nine of them restating one finding. These two are proof the
loose claim-overlap matcher in `pr_review_convergence` fires on wording that
actually occurred, not on invented text tuned to the matcher.

Underscore-prefixed so pytest does not collect this as a test module.
"""

from __future__ import annotations

ROUND1_URL = "https://github.com/svenroth-ai/shipwright/pull/690#issuecomment-5581682816"
ROUND1_CREATED_AT = "2026-09-08T08:19:23Z"
ROUND2_URL = "https://github.com/svenroth-ai/shipwright/pull/690#issuecomment-5582432326"
ROUND2_CREATED_AT = "2026-09-08T09:13:44Z"

ROUND1_BODY = "## 🤖 Shipwright PR Review\n\n**Decision: 🔴 BLOCK**\n\nThe promotion mechanism has substantial behavioral coverage and protects the spec from several write-ordering and collision hazards. However, recorded evidence fingerprints are computed and reported but do not participate in the decision that clears a prior promotion, so changed or stale evidence is silently accepted as a consistent explicit promotion. This violates the stated content-based revalidation contract and can leave a hard enforcement binding based on evidence that no longer matches the recorded decision.\n\n> ℹ️ 9 generated file(s) were excluded from review (regenerated artifacts — compliance docs, agent-docs, changelog drops, state logs, prior review records — with no reviewable logic): `.shipwright/agent_docs/iterates/iterate-2026-08-11-changelog-manifest-version-sync.json`, `.shipwright/agent_docs/iterates/iterate-2026-08-13-triage-detail-maxlength.json`, `.shipwright/agent_docs/iterates/iterate-2026-09-08-p3-5-promote-layers-per-fr.json`, `.shipwright/agent_docs/iterates/iterate-2026-09-08-p3-5-promote-layers-per-fr.test-results.json`, `.shipwright/compliance/layer_promotion_ledger.json`, `.shipwright/planning/iterate/iterate-2026-09-08-p3-5-promote-layers-per-fr/reviews.json`, `.shipwright/triage.jsonl`, `CHANGELOG-unreleased.d/Added/iterate-2026-09-08-p3-5-promote-layers-per-fr_001.md`, `shipwright_events.jsonl`.\n\n### 🚫 Blocking issues\n- shared/scripts/tools/promote_required_layers.py:145-149 — `fingerprint_drifted` is attached to the report only, while `evaluate_fr` treats any still-explicit prior promotion as `already_explicit_consistent` without checking the fingerprint. Make fingerprint drift a decision-enforced condition: when the latest promoted entry's fingerprint differs from the current manifest evidence, return an escalation (or require a new operator decision) instead of silently skipping; add a regression test that changes coverage/tests after promotion and asserts exit 3 with no automatic rewrite.\n\n### Comments\n- shared/scripts/tools/promote_required_layers.py:79-88 — malformed active requirements with an empty `spec_path` are only rejected if they otherwise produce a promotion; nodes with no evidence can be silently skipped. Consider validating `spec_path` for every active node during planning so malformed manifest records consistently produce a named operational error.\n\n---\n_Automated Tier-3 review by `openai/gpt-5.6-luna` via OpenRouter (external / sensitive-path PR). Tier 1/2 PRs are reviewed locally at `/shipwright-iterate` Step 8 — see B4.5._\n"

ROUND2_BODY = '## 🤖 Shipwright PR Review\n\n**Decision: 🔴 BLOCK**\n\nThis is a large behavioral change that promotes advisory requirement bindings into hard enforcement based on manifest fields alone. The implementation records only a hash of coverage and test-link data, but does not establish that the evidence came from CI for the current commit or manifest revision, leaving an autonomous and durable promotion path vulnerable to stale or locally authored evidence. The added tests also encode promotion from fixtures without any CI provenance, so they would pass despite this missing trust boundary.\n\n> ℹ️ 9 generated file(s) were excluded from review (regenerated artifacts — compliance docs, agent-docs, changelog drops, state logs, prior review records — with no reviewable logic): `.shipwright/agent_docs/iterates/iterate-2026-08-11-changelog-manifest-version-sync.json`, `.shipwright/agent_docs/iterates/iterate-2026-08-13-triage-detail-maxlength.json`, `.shipwright/agent_docs/iterates/iterate-2026-09-08-p3-5-promote-layers-per-fr.json`, `.shipwright/agent_docs/iterates/iterate-2026-09-08-p3-5-promote-layers-per-fr.test-results.json`, `.shipwright/compliance/layer_promotion_ledger.json`, `.shipwright/planning/iterate/iterate-2026-09-08-p3-5-promote-layers-per-fr/reviews.json`, `.shipwright/triage.jsonl`, `CHANGELOG-unreleased.d/Added/iterate-2026-09-08-p3-5-promote-layers-per-fr_001.md`, `shipwright_events.jsonl`.\n\n### 🚫 Blocking issues\n- shared/scripts/lib/layer_promotion.py:61-70,240-279 — `highest_ok_layer` and `evaluate_fr` trust `coverage == "ok"` and link statuses without verifying a CI run/job, source commit, manifest revision, or freshness; require immutable, validated CI provenance for the selected evidence (or refuse/escalate when it is absent) before returning `promote`, and add tests for stale/local/cross-commit evidence.\n- shared/scripts/lib/layer_promotion_ledger.py:39-58 and shared/scripts/tools/promote_required_layers.py:153-165 — the recorded fingerprint covers only mutable `coverage` and `tests` JSON and is not bound to an authenticated CI result or the current source revision, so a stale or fabricated manifest can create a permanent `promoted` ledger entry; include and validate the CI run/job ID, commit SHA, manifest revision, and test identity before applying the promotion, rather than tracking this as a follow-up.\n\n### Comments\n- shared/scripts/tools/tests/test_promote_required_layers.py:37-61 — the clean-promotion fixture contains no CI provenance, so strengthen it to model the evidence contract and ensure the test fails when provenance is missing or mismatched.\n\n---\n_Automated Tier-3 review by `openai/gpt-5.6-luna` via OpenRouter (external / sensitive-path PR). Tier 1/2 PRs are reviewed locally at `/shipwright-iterate` Step 8 — see B4.5._\n'

def round1_comment() -> dict:
    return {"author": {"login": "github-actions"}, "createdAt": ROUND1_CREATED_AT,
            "url": ROUND1_URL, "body": ROUND1_BODY}


def round2_comment() -> dict:
    return {"author": {"login": "github-actions"}, "createdAt": ROUND2_CREATED_AT,
            "url": ROUND2_URL, "body": ROUND2_BODY}


#: REAL commit SHAs — `gh pr view 690 --repo svenroth-ai/shipwright --json
#: reviews` (fetched 2026-09-09, doubt-review round) still returns each
#: review's GitHub-stamped `commit.oid`, submitted ~1 second after its
#: sibling issue comment (`pr_review.py`'s `_post_verdict` posts both
#: together). That is the whole reason `verdicts_span_distinct_commits`
#: now prefers this binding: unlike `commits[]`/`committedDate` (below), a
#: review's `commit.oid` is not lost when the PR is later rebased — #690 was,
#: in a later, unrelated session, which is exactly what makes the two paths'
#: reliability visibly different on the same real PR.
ROUND1_COMMIT_SHA = "3f7beacff7e8794e377cf5b9fae5f97e2876d300"
ROUND2_COMMIT_SHA = "1078c49151e2d2229ee0a599f1cd41342944a3d1"

ROUND1_REVIEW_SUBMITTED_AT = "2026-09-08T08:19:24Z"
ROUND2_REVIEW_SUBMITTED_AT = "2026-09-08T09:13:45Z"


def round_reviews() -> list[dict]:
    """The two real `CHANGES_REQUESTED` reviews GitHub paired with
    ``round1_comment``/``round2_comment`` — same fetch as the bodies above,
    id/state/commit.oid all real, unedited."""
    return [
        {"id": "PRR_kwDORsUSgM8AAAABMlDfTw", "author": {"login": "github-actions"},
         "state": "CHANGES_REQUESTED", "submittedAt": ROUND1_REVIEW_SUBMITTED_AT,
         "includesCreatedEdit": False, "commit": {"oid": ROUND1_COMMIT_SHA}},
        {"id": "PRR_kwDORsUSgM8AAAABMlnrbw", "author": {"login": "github-actions"},
         "state": "CHANGES_REQUESTED", "submittedAt": ROUND2_REVIEW_SUBMITTED_AT,
         "includesCreatedEdit": False, "commit": {"oid": ROUND2_COMMIT_SHA}},
    ]


#: `commits[]`/`committedDate` is the FALLBACK binding path, used only when
#: `reviews` is unavailable. #690's real commit history from Sept 8 is no
#: longer reachable post-rebase, so — unlike the SHAs and review data above,
#: all real — these two `committedDate` values are synthetic placeholders,
#: positioned strictly around ROUND1_CREATED_AT/ROUND2_CREATED_AT so the
#: fallback path's own tests still exercise it meaningfully. The real oids
#: are reused so a test mixing both fixtures never binds two different
#: "current heads" to the same round.
def round_commits() -> list[dict]:
    return [
        {"oid": ROUND1_COMMIT_SHA, "committedDate": "2026-09-08T08:10:00Z"},
        {"oid": ROUND2_COMMIT_SHA, "committedDate": "2026-09-08T08:45:00Z"},
    ]
