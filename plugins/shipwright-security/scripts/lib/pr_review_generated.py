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
# are NOT reused for the skip-the-gate-entirely decision below; see
# `_REVIEW_EVIDENCE_SKIP_RE` and the Internal Plan Review note on
# `is_safe_to_skip_review` for why that needs a materially narrower rule.
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
# `doubt_review_reply.json` and nothing else. Closed to that exact set —
# matching what `_REVIEW_EVIDENCE_SKIP_RE` below already required for the
# higher-stakes skip decision. `external-[^/]*review[^/]*` keeps its wildcard
# on the RUN-ANCHORED branch too: `external_review.py` prints to stdout with
# no fixed output name (see `_REVIEW_EVIDENCE_SKIP_RE`'s own comment), so no
# closed set can be drawn for that family without breaking legitimate future
# runs.
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
# extend this alternative (hide side) when that happens. It never needs
# extending on the skip side: see `_REVIEW_EVIDENCE_SKIP_RE`'s Round 3 note
# for why reply files are deliberately never skip-safe, new stage or not.

# The CLOSED, ANCHORED set used ONLY by `is_safe_to_skip_review` below —
# EXACT basenames, deliberately zero wildcards.
#
# Internal Plan Review, high-severity finding on
# iterate-2026-09-11-pr-review-evidence-filter-gap: `_REVIEW_EVIDENCE_RE`
# above matches ANY `*_reply.json` / `external-...review....json` basename at
# ANY depth under the review-evidence prefix, with no schema or provenance
# check. Sharing it verbatim with `is_safe_to_skip_review` — which decides
# whether the PR-REVIEW GATE ITSELF may post `success` with no model call —
# meant a PR whose only changed file was an attacker-authored
# `evil_reply.json`, or even `external-my-own-review-of-this.json`, would skip
# review entirely on a filename an attacker fully controls.
#
# `external_review.py` does not itself dictate an output filename (it prints
# to stdout; the calling agent picks where to save it), so there is no fixed
# convention to draw a closed `external-...` set from — the survey behind this
# fix found 15+ distinct historical basenames for that one file. Rather than
# widen the closed set with an unenforceable wildcard, `external-*review*`
# files are deliberately EXCLUDED here: `is_generated_path` still hides them
# from the model (lower stakes — a section is skipped, but every other
# changed file, if any, is still reviewed), while a PR whose only changed
# file is one of these still goes through the review step for real (which,
# seeing only generated/hidden content, approves trivially) rather than
# posting `success` with no model call at all. Only `reviews.json`, written
# by `record_review_pass.py` at one fixed path, is in this set — a
# PRE-EXISTING acceptance (see the "Round 3" note below), though this
# iterate narrows it further: before this iterate `is_safe_to_skip_review`
# shared `_REVIEW_EVIDENCE_RE` verbatim, so the legacy
# `[^/]*-external-[^/]*review[^/]*\.json` shape (unanchored, any depth) was
# ALSO skip-safe — external code review (glm) caught this spec-narrative
# gap. Anchored to exactly one run-directory segment (no bare top-level
# file, no deeper nesting) — never the shape the tool writes.
#
# Round 3 of external plan review (openai, high severity, after Round 2's
# hide-side tightening) on iterate-2026-09-11-pr-review-evidence-filter-gap:
# an earlier version of this fix ALSO added the closed
# `{spec,code,doubt}_review_reply.json` set here, reasoning it was exact and
# tool-adjacent enough to match `reviews.json`'s existing treatment. openai
# correctly identified this as an unforced, unjustified expansion: an EXACT
# basename is not PROVENANCE — nothing stops an attacker from hand-crafting
# a file with one of these three names, in a self-chosen run directory, with
# forged `SHIPWRIGHT_VERDICT: approve` content, and the PR's only changed
# file being that one forgery would then skip review with zero model call.
# Critically, this was never *needed*: the origin bug (PR #722's BLOCK) was
# entirely about the REVIEWER SEEING these files, i.e. the hide side
# (`is_generated_path` / `_REVIEW_EVIDENCE_RE_RUN_ANCHORED`) — nothing in
# this iterate's scope required the reply-file family to also be skip-safe.
# Reverted: the reply files now get the SAME treatment
# `external-*review*` files already had — hidden from the model, but a PR
# whose only changed file is one of them still goes through a real (if
# trivial) review call rather than an automatic skip. This is the simpler,
# more conservative fix openai suggested, and it leaves
# `_REVIEW_EVIDENCE_SKIP_RE` matching ONLY `reviews.json` — narrower than
# even its pre-iterate shape (see the narrowing note just above).
#
# code-reviewer (high): this pattern and `_REVIEW_EVIDENCE_RE_RUN_ANCHORED`
# were `re.IGNORECASE`, contradicting "EXACT basenames, zero wildcards" —
# `REVIEWS.JSON` (never produced by the real tool) would borrow skip-safety
# on a case-sensitive CI runner. Removed from both; see the pinning test.
_REVIEW_EVIDENCE_SKIP_RE = re.compile(
    re.escape(_REVIEW_EVIDENCE_PREFIX) + r"[^/]+/reviews\.json$"
)


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

    Strictly narrower than `is_generated_path`, in three ways (1-2 from
    Stage-3 doubt review on iterate-2026-09-10-pr-review-generated-only,
    3 added by this iterate):

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
    `.shipwright/agent_docs/runtime/`, `CHANGELOG-unreleased.d/`) stay as-is:
    they are directory-anchored structured artifacts, not the free-form
    agent-instruction surface the exclusion above targets.

    3. Uses `_REVIEW_EVIDENCE_SKIP_RE`, NOT `_REVIEW_EVIDENCE_RE` /
       `_REVIEW_EVIDENCE_RE_RUN_ANCHORED`, for review evidence. Internal Plan
       Review, high-severity finding on
       iterate-2026-09-11-pr-review-evidence-filter-gap: `is_generated_path`'s
       run-anchored regex matches `*_reply.json` / `external-...review....json`
       basenames — reusing it here would let a PR whose only changed file is
       an attacker-chosen name skip review entirely. `_REVIEW_EVIDENCE_SKIP_RE`
       is a run-directory-anchored match on `reviews.json` ONLY (see its own
       comment — Round 3 of external plan review found that even the closed
       `{spec,code,doubt}_review_reply.json` set this function used to also
       include was an unforced expansion of the same bypass, since an exact
       basename is not provenance). Every review-evidence file besides
       `reviews.json` — the reply family AND `external-*review*` — is hidden
       from the model but NOT skip-safe: a PR touching only one still goes
       through a real (if trivial) review call rather than an automatic
       skip. `self-review-payload.json` stays un-skippable too, being
       unmatched by every regex.
    """
    p = (path or "").strip()
    if any(p.startswith(pre) for pre in _GENERATED_PREFIXES):
        return True
    if _REVIEW_EVIDENCE_SKIP_RE.match(p):
        return True
    return p in _SKIP_REVIEW_CANONICAL_BASENAME_PATHS
