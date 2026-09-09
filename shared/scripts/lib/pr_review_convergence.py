"""Is the PR-review gate stuck repeating itself? (trg-ac24ec5b, PR #690)

F11's `checks_failed` exit (2) tells the operator to "diagnose, FIX, re-push, then
re-run delivery" — sound advice when each round's `PR Review` BLOCK names a new,
distinct defect. It stops being sound advice when round after round names the
SAME defect in different words: PR #690 pushed ten times over ~7h40m, blocked by
the Tier-3 `PR Review` gate every time, nine of twelve verdicts restating one
finding ("promotion trusts coverage/tests without establishing the evidence came
from a CI run bound to the current commit"). No fix in scope could satisfy that
demand, and nothing noticed — the loop is wall-clock, not token, cost, so a
spend-keyed guard stays quiet through the whole thing.

This module answers exactly one question: do the two most recent `PR Review`
BLOCK comments on a PR name a recurring finding? It is deliberately NOT a memory
for the gate itself (scope guard, trg-ac24ec5b): `pr_review.py` stays stateless
per commit, and reads nothing here. The only reader is `tools/deliver_pr.py`,
which asks this AFTER the gate has already failed twice, purely to decide whether
"re-push and try again" is worth suggesting a third time.

**Loose on text, strict on location.** The reviewer restates one objection in
different words every round (nine variants on #690) and the line numbers it
cites drift as the code shifts underneath it. So a finding "recurs" when two
BLOCK verdicts share a FILE PATH (exact — the one strict axis) and a claim whose
significant vocabulary overlaps past a threshold (loose — normalised text,
never string equality, which would never fire on reworded prose). Two
consecutive BLOCKs is the trigger; three is not required — a count is the wrong
predicate here (SKILL.md's brief for this unit explains why: a count halts a run
that is genuinely converging through a list of distinct real findings, the GOOD
and common case; sameness does not).

Threshold provenance: tuned against PR #690's own round-1/round-2 comment
bodies (the fixture in `shared/tests/_pr690_review_fixtures.py` — real
bytes, not paraphrased), which share 9 significant tokens at an overlap
coefficient of 0.32 on the file both rounds actually blocked. `MIN_SHARED_TOKENS`
and `MIN_CLAIM_OVERLAP` sit comfortably below that measurement with margin,
not above a guess.

**Two more preconditions** (added after review found the text-only match
alone insufficient for a TERMINAL outcome): the BLOCK comments must be
authored by the real reviewer, and must bind to two DISTINCT commits, the
current one matching the PR's actual head — both live in the sibling module
`lib.pr_review_verdict_provenance` (split out to keep each file under the
300-line source limit; see that module's docstring for the full reasoning).
The commit binding prefers GitHub's own `commit.oid` stamp off the PR's
`reviews` array over a `commits[]`/`committedDate` guess (doubt-reviewer,
Stage 3) — `non_converging` accepts `reviews` as an optional third binding
input for exactly that reason.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from lib.pr_review_verdict_provenance import is_authentic, verdicts_span_distinct_commits

__all__ = [
    "MIN_CLAIM_OVERLAP", "MIN_SHARED_TOKENS", "REVIEW_COMMENT_MARKER",
    "claim_overlap", "extract_blocking_findings", "findings_recur",
    "is_block_verdict", "non_converging", "normalized_tokens",
    "two_most_recent_block_verdicts",
]

#: Present in every comment `pr_review_render.render_comment` produces — the
#: filter that separates this bot's verdicts from every other PR comment.
REVIEW_COMMENT_MARKER = "Shipwright PR Review"
#: The exact badge text `render_comment` emits for a block decision.
_BLOCK_BADGE = "🔴 BLOCK"

_BLOCKING_HEADING_RE = re.compile(r"^#{1,6}\s*.*Blocking issues", re.IGNORECASE)
_HEADING_RE = re.compile(r"^#{1,6}\s")
_BULLET_RE = re.compile(r"^-\s+(.*)")

#: Extensions this repo's reviewer plausibly cites. Bounding the set keeps
#: `_FILE_RE` from reading prose abbreviations ("e.g.", "i.e.") as file paths —
#: any two-or-three-letter suffix would match those too.
_CODE_EXTENSIONS = (
    "py", "js", "ts", "tsx", "jsx", "md", "json", "yml", "yaml", "toml",
    "sh", "ps1", "cfg", "ini", "txt", "html", "css",
)
_FILE_RE = re.compile(
    r"`?([A-Za-z0-9_][\w./-]*\.(?:" + "|".join(_CODE_EXTENSIONS) + r"))`?(?::[\d,\-]+)?"
)

#: Two categories, both excluded because neither carries the signal this
#: predicate looks for: ordinary grammatical function words, PLUS the
#: review-boilerplate verbs every BLOCK claim shares regardless of subject
#: ("add", "require(s)", "return(s)", "tracking", "follow", "instead",
#: "rather" — "add a test", "require provenance" — code-reviewer, Stage 2:
#: the prior comment here undersold this second category). Domain nouns the
#: reviewer actually repeats across rounds ("fingerprint", "coverage",
#: "promotion", "manifest", "current") stay IN, because they ARE the signal.
_STOPWORDS = frozenset("""
a an the is are was were be been being this that these those to of in on at by
for with from as or and not no but so than then when while before after once
only still prior instead rather tracking follow add make require requires
return returns without into any all each every other another same some such
per via whose which who what where how do does did can could should would
must may might will shall if unless because since until though although
however therefore thus hence its it their they he she we you also more most
less least many much few very new old high low first last next about above
below over under between within out down off again further here there own too
just now
""".split())


def extract_blocking_findings(comment_body: str) -> list[dict]:
    """The `### Blocking issues` section's bullets, each as
    ``{"raw": str, "files": frozenset[str], "tokens": frozenset[str]}``.

    Only the Blocking issues section — `### Comments` (non-blocking) is not the
    gate and is not read here. A comment with no such section (approve/comment
    decisions, or a block whose `blocking` list happened to be empty) yields `[]`.
    """
    lines = comment_body.splitlines()
    findings: list[dict] = []
    in_section = False
    for line in lines:
        if _BLOCKING_HEADING_RE.match(line):
            in_section = True
            continue
        if in_section and _HEADING_RE.match(line):
            break
        if not in_section:
            continue
        match = _BULLET_RE.match(line)
        if not match:
            continue
        raw = match.group(1).strip()
        if not raw:
            continue
        files = frozenset(_FILE_RE.findall(raw))
        findings.append({"raw": raw, "files": files, "tokens": normalized_tokens(raw)})
    return findings


def normalized_tokens(text: str) -> frozenset[str]:
    """Significant-vocabulary tokens: file paths and code spans stripped (they
    are matched separately, exactly, via ``files``), lowercased, stopworded,
    short tokens (line numbers, "ok", "id") dropped.
    """
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = _FILE_RE.sub(" ", text)
    words = re.findall(r"[A-Za-z]+", text.lower())
    return frozenset(w for w in words if len(w) >= 4 and w not in _STOPWORDS)


#: An overlap coefficient (shared / smaller claim's own vocabulary) rather than
#: Jaccard: two claims of very different length — one terse, one elaborated —
#: describing the same defect should not be penalised for the elaboration.
MIN_CLAIM_OVERLAP = 0.2
#: A ratio alone lets two three-word claims "match" on one shared word. This is
#: the floor that keeps the predicate meaningful at any claim length.
MIN_SHARED_TOKENS = 4


def claim_overlap(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def findings_recur(
    current: Sequence[Mapping], previous: Sequence[Mapping], *,
    min_overlap: float = MIN_CLAIM_OVERLAP, min_shared: int = MIN_SHARED_TOKENS,
) -> tuple[dict, dict] | None:
    """The first ``(current_finding, previous_finding)`` pair that names the
    same file and a claim whose vocabulary overlaps past the threshold, or
    ``None``. Strict on file (exact path match — one recomputed per round from
    drifting line numbers, so the path is the stable half); loose on claim.
    """
    for cur in current:
        for prev in previous:
            if not (cur["files"] & prev["files"]):
                continue
            shared = cur["tokens"] & prev["tokens"]
            if len(shared) < min_shared:
                continue
            if claim_overlap(cur["tokens"], prev["tokens"]) < min_overlap:
                continue
            return (dict(cur), dict(prev))
    return None


def is_block_verdict(comment_body: str) -> bool:
    """Is this comment a Shipwright PR Review verdict, and was it BLOCK?

    Text-only, deliberately — the author check lives separately in
    :func:`two_most_recent_block_verdicts`, so this stays a pure predicate on
    what the comment says, testable without a comment's metadata.
    """
    return REVIEW_COMMENT_MARKER in comment_body and _BLOCK_BADGE in comment_body


def two_most_recent_block_verdicts(comments: Sequence[Mapping]) -> tuple[dict, dict] | None:
    """The two most recent, authentically-authored `PR Review` BLOCK comments,
    oldest first, or ``None`` if fewer than two exist.

    Filtered to BLOCK only — an approve/comment verdict in between two BLOCKs
    does not reset the count: it means the gate went green and then found
    something new (or the same thing) to block on, and "the last two BLOCKs
    agree" is still the right question to ask. Comments with an unreadable or
    missing `createdAt` sort first (oldest), never last — an unreadable
    timestamp must not be mistaken for "just posted" and treated as the most
    recent, authoritative verdict. Also filtered to `is_authentic` — a
    forged BLOCK-shaped comment from any other author is not a verdict.
    """
    blocks = [c for c in comments
              if is_block_verdict(str(c.get("body") or "")) and is_authentic(c)]
    blocks.sort(key=lambda c: str(c.get("createdAt") or ""))
    if len(blocks) < 2:
        return None
    previous, current = blocks[-2], blocks[-1]
    return (previous, current)


def non_converging(
    comments: Sequence[Mapping], *,
    commits: Sequence[Mapping] = (),
    head_sha: str = "",
    reviews: Sequence[Mapping] = (),
) -> dict | None:
    """Do the PR's two most recent `PR Review` BLOCK verdicts recur?

    ``comments`` is the ``comments`` array of a `gh pr view --json comments`
    payload. ``head_sha`` (the PR's current `headRefOid`) plus ``reviews``
    (its `reviews` array, preferred — each carries a GitHub-stamped
    `commit.oid`) or ``commits`` (its `commits` array, fallback approximation
    by `committedDate`) bind the pair to distinct, current code — pass
    `head_sha` and at least one of the two or the predicate fails open (see
    :func:`lib.pr_review_verdict_provenance.verdicts_span_distinct_commits`).
    Returns ``None`` on fewer than two authentic BLOCK verdicts, an
    unparseable section on either, no recurring (file, claim) pair, or an
    unbindable/stale/duplicate/unauthenticated-by-review commit pair — every
    one of those is "not proven non-converging", and the caller's existing
    `checks_failed` (exit 2) path must survive unchanged. Returns, on a
    match:
    ``{"previous_comment", "current_comment", "previous_finding", "current_finding"}``
    — the two comments (with their own `url`/`createdAt`) and the specific
    finding pair that recurred, for F11 to quote side by side.
    """
    pair = two_most_recent_block_verdicts(comments)
    if pair is None:
        return None
    previous_comment, current_comment = pair
    previous_findings = extract_blocking_findings(str(previous_comment.get("body") or ""))
    current_findings = extract_blocking_findings(str(current_comment.get("body") or ""))
    if not previous_findings or not current_findings:
        return None
    match = findings_recur(current_findings, previous_findings)
    if match is None:
        return None
    if not verdicts_span_distinct_commits(
        commits, head_sha, previous_comment, current_comment, reviews=reviews,
    ):
        return None
    current_finding, previous_finding = match
    return {
        "previous_comment": dict(previous_comment),
        "current_comment": dict(current_comment),
        "previous_finding": previous_finding,
        "current_finding": current_finding,
    }
