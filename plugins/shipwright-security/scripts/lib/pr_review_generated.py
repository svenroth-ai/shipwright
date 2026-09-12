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

**`is_safe_to_skip_review` — the strictly narrower, higher-stakes sibling that
decides whether the PR-review GATE ITSELF may skip a model call entirely —
lives in `pr_review_skip_safety.py`** (split out iterate-2026-09-12-generated-
prefixes-provenance-anchor, once this file crossed the 300-line guideline).
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
# PR #722 finding: `reviews.json` was matched but its own-directory siblings
# were not — `spec_review_reply.json` / `code_review_reply.json` /
# `doubt_review_reply.json` (the internal-cascade reply convention) and
# `external-code-review-raw.json` / `external-code-review.json` /
# `external-plan-review.md` (missing the legacy `[^/]*-external-...` branch's
# required prefix before "external-", or a `.md` extension the old regex never
# covered) all slipped through, so the reviewer was fed prior-review
# transcripts this rule exists to keep out.
#
# `self-review-payload.json` is DELIBERATELY left unmatched. It is the payload
# SENT TO a review stage, not a transcript OF one — author-influenced content,
# not tool-written record — so it stays exactly where the module docstring's
# warning says an over-broad entry does the most damage: it needs a reviewer's
# eyes, not a free pass.
#
# Deliberately NARROW otherwise. The `.md` siblings in the same directory —
# the iterate spec and its mini-plan — are AUTHORED, state the acceptance
# criteria, and are exactly the intent a reviewer should read the diff
# against. They stay in. The rule is "a reviewer does not review prior
# reviews", not "planning docs are uninteresting".
#
# THESE REGEXES ARE FOR `is_generated_path` (HIDE-FROM-THE-MODEL) ONLY. They
# are NOT reused for the skip-the-gate-entirely decision — as of Round 4, NO
# review-evidence path grants skip-safety at all (see
# `pr_review_skip_safety.is_safe_to_skip_review`'s docstring).
#
# Split in two, not one, after external plan review (glm + openai,
# iterate-2026-09-11-pr-review-evidence-filter-gap) independently converged
# on the same finding: the first version of the PR #722 fix added
# `[^/]*_reply\.json` / `external-...review....json` as unanchored
# alternatives, matching at ANY depth under `.shipwright/planning/iterate/` —
# not just inside a genuine run's own directory. An attacker could plant
# `.shipwright/planning/iterate/other-tree/evil_reply.json` (no real run ever
# owns "other-tree") and have it hidden from the reviewing model on a
# self-chosen name. The LEGACY alternatives below (`reviews.json`, the old
# flat `X-external-Y.json` shape) keep their original, deliberately loose
# match — untouched, pre-existing, accepted risk, not this iterate's to
# retighten. The NEW alternatives this iterate adds are anchored instead: see
# `_REVIEW_EVIDENCE_RE_RUN_ANCHORED` below, which requires exactly one
# directory segment (a run directory) between the prefix and the filename.
#
# Round 2 of that same external review (glm=approve, openai=revise) then
# converged on a second, smaller finding: even run-anchored,
# `[^/]*_reply\.json` was still a wildcard on the basename itself, hiding
# `evil_reply.json` (or any name) from the model on nothing but a suffix
# match, while the actual producer only ever writes three: a `git log
# --diff-filter=A -- "*_reply.json"` survey across every branch in this repo
# found `spec_review_reply.json` / `code_review_reply.json` /
# `doubt_review_reply.json` and nothing else. Closed to that exact set.
# `external-[^/]*review[^/]*` keeps its wildcard on the RUN-ANCHORED branch
# too: `external_review.py` prints to stdout with no fixed output name, so no
# closed set can be drawn for that family without breaking legitimate future
# runs. (Neither alternative is ever skip-safe, as of Round 4 — see below.)
_REVIEW_EVIDENCE_PREFIX = ".shipwright/planning/iterate/"
_REVIEW_EVIDENCE_RE = re.compile(
    r"(^|/)("
    r"reviews\.json"
    r"|[^/]*-external-[^/]*review[^/]*\.json"
    r")$"
)
_REVIEW_EVIDENCE_RE_RUN_ANCHORED = re.compile(
    r"^[^/]+/("
    r"(spec|code|doubt)_review_reply\.json"
    r"|external-[^/]*review[^/]*\.(json|md)"
    r")$"
)

# MAINTENANCE NOTE (external plan review, Round 3, glm, low): the
# `(spec|code|doubt)_review_reply\.json` alternative above is closed against
# THIS repo's history, not the review cascade's name space in the abstract.
# If a future review stage is added (e.g. a `security_review_reply.json`),
# its transcript will NOT be hidden from the reviewing model by default —
# extend this alternative (hide side) when that happens. There is no
# skip-side set to extend any more (see the Round 4 note in
# `pr_review_skip_safety.py`).

# Round 5 (the live PR-review gate, again, on this iterate's own PR #727):
# the gate flagged `external-[^/]*review[^/]*\.(json|md)` as a review-evasion
# wildcard — a contributor could name an arbitrary file to match it and have
# its diff hidden from the model. Measured before deciding: `git ls-files
# .shipwright/planning/iterate` on origin/main carries 40+ DISTINCT basenames
# for the same handful of review-evidence artifact KINDS (code-review.json,
# code_review.json, stage2-code-review.json, stage2_code_review.json,
# code-review-raw.json, external-code-review-raw.json,
# external-code-review.raw.json, self-review.json, self_review.json,
# spec-review.json, spec_review_payload.json, ... — and that list is not
# exhaustive). That measurement rules out BOTH candidate fixes at once:
# - Widening the wildcard is out: a pattern loose enough to catch that many
#   real names is loose enough for an attacker to hit deliberately. The
#   review-evasion concern stands.
# - An exact-basename allowlist (the `_reply.json` move, above) is ALSO out:
#   it would need ~40 entries today and would still miss whatever the next
#   run invents. Name-trust does not work when the *writers* choose names ad
#   hoc per run, unlike the closed `_reply.json` family, which has exactly
#   three fixed producers.
#
# The defect is upstream of this classifier: the pipeline has no canonical
# name per review-evidence artifact kind, so no path-based filter — wide or
# narrow — can classify this family safely. The real fix is to make the
# writers emit ONE canonical name per kind under the run directory, the same
# move `pr_review_skip_safety.is_safe_to_skip_review` already made via
# `_SKIP_REVIEW_CANONICAL_BASENAME_PATHS` — only then does an exact-path
# allowlist become possible here too. That is a producer-side change, tracked
# separately (trg-3b206c08), not this classifier's to attempt. This PR
# does NOT close the underlying gap PR #722 waits on; `is_generated_path`'s
# hide-only wildcard stays exactly as wide as before this iterate started,
# unchanged from the pre-existing regex above.


def is_generated_path(path: str) -> bool:
    """True iff ``path`` is a producer-generated artifact (not reviewable code)."""
    p = (path or "").strip()
    if any(p.startswith(pre) for pre in _GENERATED_PREFIXES):
        return True
    if p in _GENERATED_AGENT_DOCS:
        return True
    if p.startswith(_REVIEW_EVIDENCE_PREFIX):
        if _REVIEW_EVIDENCE_RE.search(p):
            return True
        rest = p[len(_REVIEW_EVIDENCE_PREFIX):]
        if _REVIEW_EVIDENCE_RE_RUN_ANCHORED.match(rest):
            return True
    return p.rsplit("/", 1)[-1] in _GENERATED_BASENAMES
