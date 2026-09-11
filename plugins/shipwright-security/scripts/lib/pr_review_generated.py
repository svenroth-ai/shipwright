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

__all__ = ["is_generated_path", "is_safe_to_skip_review"]

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


# The canonical, repo-root location of each `_GENERATED_BASENAMES` file. Used
# ONLY by `is_safe_to_skip_review` (below) — `is_generated_path` above stays
# basename-only, matched at ANY directory, because its stakes are lower: it
# only hides a section from the model while everything else in the diff is
# still reviewed. `is_safe_to_skip_review` decides whether the PR-REVIEW GATE
# ITSELF may post green with no model call at all, so a brand-new file merely
# NAMED e.g. `triage.jsonl` planted at an attacker-chosen path — never the
# actual regenerated artifact the basename rule was written for — must not
# borrow that classification (Stage-3 doubt review, medium finding).
_SKIP_REVIEW_CANONICAL_BASENAME_PATHS = frozenset({
    "shipwright_test_results.json",
    "shipwright_events.jsonl",
    ".shipwright/triage.jsonl",
    ".shipwright/triage.outbox.jsonl",
})


def is_safe_to_skip_review(path: str) -> bool:
    """True iff ``path`` may contribute to skipping the PR-review gate entirely
    (posting `success` with no model call), NOT merely to hiding its section
    from a model that still reviews the rest of the diff.

    Strictly narrower than `is_generated_path`, in two ways (Stage-3 doubt
    review on iterate-2026-09-10-pr-review-generated-only, high + medium
    findings):

    1. Excludes `_GENERATED_AGENT_DOCS` (`build_dashboard.md`,
       `session_handoff.md`, `triage_inbox.md`). That set exists so the diff
       shown to the model isn't padded with noise — but this repo's own
       architecture reads these three files back as agent context in later
       sessions (docs/hooks-and-pipeline.md), and they carry free-form prose a
       contributor controls. Skipping the reviewer entirely for a PR touching
       ONLY these is exactly the "an agent obeys it" case `is_generated_path`'s
       own module docstring warns is unsafe — they need a reviewer's eyes for
       injected instructions, they are not "no reviewable content".
    2. Anchors the otherwise-basename-only `_GENERATED_BASENAMES` matches to
       their one canonical repo-root path (`_SKIP_REVIEW_CANONICAL_BASENAME_PATHS`)
       rather than matching the basename at any directory.

    `_GENERATED_PREFIXES` (`.shipwright/compliance/`, `.shipwright/agent_docs/iterates/`,
    `.shipwright/agent_docs/runtime/`, `CHANGELOG-unreleased.d/`) and the
    review-evidence prefix stay as-is: they are directory-anchored structured
    artifacts, not the free-form agent-instruction surface the exclusion above
    targets.
    """
    p = (path or "").strip()
    if any(p.startswith(pre) for pre in _GENERATED_PREFIXES):
        return True
    if p.startswith(_REVIEW_EVIDENCE_PREFIX) and _REVIEW_EVIDENCE_RE.search(p):
        return True
    return p in _SKIP_REVIEW_CANONICAL_BASENAME_PATHS
