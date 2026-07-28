"""What counts as a producer-generated artifact — the POLICY, not the mechanism.

Root fix for trg-e1c554d9: a medium+ PR regenerates producer-owned artifacts
(compliance MDs, the three regenerated agent-docs, changelog drops, append-log
state files, prior review records) that carry NO reviewable logic but dominate
the diff — ~82% of chars on PR #310. `pr_review_diff_filter` drops those
sections BEFORE the truncation check, so the reviewer stays under the size cap
and sees only real code; the excluded list is surfaced by the caller in the PR
meta + comment (transparent, never silent).

Split out of `pr_review_diff_filter` so the *membership rules* — the part that
changes whenever a producer is added, and the part whose over-reach is a
security bug — are one small reviewable file, separate from the unified-diff
parsing they feed (iterate-2026-07-27-pr-review-forged-boundary).

**The governing rule, learned twice on that run.** "Regenerated, therefore no
reviewable logic" is sound for a dashboard and WRONG for anything an attacker
authors or an agent obeys. This gate's input is untrusted by definition, so an
over-broad entry here does not merely waste review — it silently hides the file
AND tells the maintainer it carried nothing worth reading.
"""

from __future__ import annotations

import re

__all__ = ["is_generated_path"]

_GENERATED_PREFIXES = (
    ".shipwright/compliance/",           # dashboard / RTM / SBOM / test-evidence / change-history
    ".shipwright/agent_docs/iterates/",  # one regenerated JSON entry per iterate run
    ".shipwright/agent_docs/runtime/",   # regenerated runtime snapshots
    "CHANGELOG-unreleased.d/",           # per-run changelog drop files
)

# `.shipwright/agent_docs/` is NOT a blanket prefix, and that is deliberate.
# Only these three `.md` files are producer-regenerated — the same three the
# repo's own churn allowlist names (`churn_merge.AGENT_DOC_MDS`). Their siblings
# are AUTHORED: `architecture.md` is curated prose the churn resolver
# specifically refuses to auto-merge, `spec.md` is the requirements spec,
# `conventions.md` / `decision_log.md` / `known_issues.md` are hand-written —
# and the whole directory is this repo's agent-instruction surface, which the
# reviewer's own system prompt orders it to BLOCK on for injected instructions.
# Excluding it wholesale told the model to scrutinise a directory it could never
# see, and told the maintainer those files carried "no reviewable logic". Same
# error as the lockfile one below, one prefix earlier.
_GENERATED_AGENT_DOCS = frozenset({
    ".shipwright/agent_docs/build_dashboard.md",
    ".shipwright/agent_docs/session_handoff.md",
    ".shipwright/agent_docs/triage_inbox.md",
})

_GENERATED_BASENAMES = frozenset({
    "shipwright_test_results.json",  # latest-run test state (regenerated each run)
    "shipwright_events.jsonl",       # append-only event log (union-merged)
    "triage.jsonl",                  # append-only triage backlog
    "triage.outbox.jsonl",           # triage outbox staging
})

# DEPENDENCY LOCKFILES ARE DELIBERATELY ABSENT from that set (2026-07-27).
# They were in it on the "regenerated, so no reviewable logic" argument, which
# is wrong for the one gate that reviews UNTRUSTED PRs: a lockfile is where a
# typosquatted package arrives, and the PR author regenerated it. Filtering it
# hid every dependency change that shared a PR with one ordinary file. The size
# argument is also spent — the cap is 1M chars and a lockfile fits.
# See iterate-2026-07-27-pr-review-forged-boundary.

# A run's REVIEW EVIDENCE, under `.shipwright/planning/iterate/`: the review
# record `record_review_pass.py` maintains, and the raw reviewer replies
# `external_review.py` emits. Both are tool-written transcripts OF a review —
# feeding them to the reviewer is circular, and they are bulky: measured 45,596
# chars (19% of the reviewed diff) on PR #446, which was the difference between
# fitting the size cap and failing closed on truncation.
#
# Deliberately NARROW. The `.md` siblings in the same directory — the iterate
# spec and its mini-plan — are AUTHORED, state the acceptance criteria, and are
# exactly the intent a reviewer should read the diff against. They stay in.
# The rule is "a reviewer does not review prior reviews", not "planning docs
# are uninteresting".
_REVIEW_EVIDENCE_PREFIX = ".shipwright/planning/iterate/"
_REVIEW_EVIDENCE_RE = re.compile(
    r"(^|/)(reviews\.json|[^/]*-external-[^/]*review[^/]*\.json)$"
)


def is_generated_path(path: str) -> bool:
    """True iff ``path`` is a producer-generated artifact (not reviewable code)."""
    p = (path or "").strip()
    if any(p.startswith(pre) for pre in _GENERATED_PREFIXES):
        return True
    if p in _GENERATED_AGENT_DOCS:
        return True
    if p.startswith(_REVIEW_EVIDENCE_PREFIX) and _REVIEW_EVIDENCE_RE.search(p):
        return True
    return p.rsplit("/", 1)[-1] in _GENERATED_BASENAMES
