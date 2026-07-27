"""Generated-artifact exclusion for the Tier-3 PR reviewer.

Root fix for the truncation false-positive (triage trg-e1c554d9). A medium+
shipwright PR regenerates many producer-owned artifacts (compliance MDs,
agent-docs, lockfiles, append-log state files) that carry NO reviewable logic
but dominate the diff — measured ~82% of chars on PR #310. `filter_generated_paths`
drops those file-sections from a unified diff BEFORE the truncation check, so the
reviewer stays under the size cap and sees only real code. The excluded list is
surfaced by the caller in the PR meta + comment (transparent, never silent).

NOTE: these paths are producer-regenerated and non-executable; a human still
reviews the full PR when the `skip-pr-review` label path is taken, and the
compliance detective audit covers the artifacts themselves.

Split out of ``pr_review_lib`` so the diff-parsing cluster is its own
cohesive, unit-testable module and both files stay under the source-size
guideline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "ReviewedDiff",
    "filter_generated_paths",
    "is_generated_path",
    "truncate_diff_at_boundary",
]

_GENERATED_PREFIXES = (
    ".shipwright/compliance/",     # regenerated dashboard / RTM / SBOM / test-evidence / change-history
    ".shipwright/agent_docs/",     # regenerated build dashboard, session handoff, iterate entries
    "CHANGELOG-unreleased.d/",     # per-run changelog drop files
)
_GENERATED_BASENAMES = frozenset({
    "shipwright_test_results.json",  # latest-run test state (regenerated each run)
    "shipwright_events.jsonl",       # append-only event log (union-merged)
    "triage.jsonl",                  # append-only triage backlog
    "triage.outbox.jsonl",           # triage outbox staging
    "uv.lock", "poetry.lock", "Cargo.lock", "yarn.lock",  # dependency lockfiles
    "package-lock.json", "pnpm-lock.yaml",
})

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

# Split boundary — a unified diff starts each file section with `diff --git `.
_DIFF_GIT_RE = re.compile(r"^diff --git a/(.+?) b/(.+?)\s*$")


@dataclass(frozen=True)
class ReviewedDiff:
    """What the reviewer actually sees, and what it is missing.

    A record rather than a tuple on purpose: the gate reads one field and the
    message reads the others, so no caller can silently bind the wrong
    positional element as this contract grows. Positional unpacking of the old
    2-tuple fails loudly instead of quietly mis-reading.

    Attributes:
        text: the diff handed to the model. Never longer than the cap.
        incomplete: **the authoritative fail-closed signal** — True whenever any
            content was dropped. Deliberately NOT derived from the path lists: a
            diff with no parseable header yields no paths at all and must still
            fail the gate.
        omitted: files with no content in ``text``.
        partial: the at-most-one file supplied cut mid-hunk, as context only.
        unidentified: sections left out — or supplied only in part — whose path
            could not be parsed, so a short list is never mistaken for a
            complete one.
    """

    text: str
    incomplete: bool
    omitted: tuple[str, ...] = ()
    partial: tuple[str, ...] = ()
    unidentified: int = 0


def is_generated_path(path: str) -> bool:
    """True iff ``path`` is a producer-generated artifact (not reviewable code)."""
    p = (path or "").strip()
    if any(p.startswith(pre) for pre in _GENERATED_PREFIXES):
        return True
    if p.startswith(_REVIEW_EVIDENCE_PREFIX) and _REVIEW_EVIDENCE_RE.search(p):
        return True
    return p.rsplit("/", 1)[-1] in _GENERATED_BASENAMES


def _clean_diff_path(rest: str) -> str:
    """Normalize a `+++ b/…` / `--- a/…` remainder to a repo-relative path.

    Returns "" for `/dev/null` (add/delete side) or empty input."""
    rest = (rest or "").strip()
    if not rest or rest == "/dev/null":
        return ""
    if rest.startswith(("a/", "b/")):
        rest = rest[2:]
    return rest.split("\t", 1)[0]  # git appends a tab+meta on some diffs


def _section_paths(section: str) -> list[str]:
    """Every repo-relative path a diff section touches (source AND destination).

    For a normal edit both sides are the same path; for a **rename** they differ
    (`diff --git a/old b/new`). Collected from the ``--- a/`` / ``+++ b/`` lines
    and the ``diff --git`` header (the header also covers rename-only / binary /
    mode-only sections that carry no ``---``/``+++`` lines). The header is always
    included so a rename's BOTH ends are considered — see
    :func:`filter_generated_paths` for why that matters.
    """
    paths: list[str] = []
    for ln in section.splitlines():
        if ln.startswith(("+++ ", "--- ")):
            p = _clean_diff_path(ln[4:])
            if p:
                paths.append(p)
        elif ln.startswith("diff --git "):
            m = _DIFF_GIT_RE.match(ln)
            if m:
                paths.extend((m.group(1), m.group(2)))
    return paths


def _split_sections(diff: str) -> tuple[str, list[str]]:
    """Split a unified diff into ``(preamble, [file section, ...])``.

    A section starts at a ``diff --git `` header and runs to the next one. Text
    before the first header is the preamble. This is the single definition of
    "a file boundary" — both the generated-artifact filter and the size cap cut
    on it, so they can never disagree about where one file ends.

    A ``diff --git`` line *inside* a hunk cannot false-match: every content line
    in a unified diff carries a ``+``, ``-`` or space prefix, so a bare header at
    column 0 is always a real header.
    """
    preamble: list[str] = []
    sections: list[list[str]] = []
    cur: list[str] | None = None
    for ln in diff.splitlines(keepends=True):
        if ln.startswith("diff --git "):
            if cur is not None:
                sections.append(cur)
            cur = [ln]
        elif cur is None:
            preamble.append(ln)
        else:
            cur.append(ln)
    if cur is not None:
        sections.append(cur)
    return "".join(preamble), ["".join(s) for s in sections]


def _dropped_paths(sections: list[str]) -> tuple[list[str], int]:
    """``(paths, unidentified_count)`` for sections left out of a review.

    A section whose header form ``_section_paths`` does not recognise (Git quotes
    paths containing spaces or non-ASCII) contributes no name. Those are COUNTED
    rather than ignored: an under-reported list must never read as a complete
    one.
    """
    paths: list[str] = []
    unidentified = 0
    for sec in sections:
        found = _section_paths(sec)
        if found:
            paths.extend(found)
        else:
            unidentified += 1
    return paths, unidentified


def truncate_diff_at_boundary(diff: str, max_chars: int) -> ReviewedDiff:
    """Cut an over-cap diff at a file boundary and say what fell outside.

    The returned text is **never** longer than ``max_chars``, for any input.
    ``incomplete`` is set by construction on every path that drops content — it
    is never derived from whether any filename could be parsed, because the one
    input where parsing fails (a diff with no recognisable header) is exactly
    the input that must still fail the gate.
    """
    if max_chars <= 0:
        raise ValueError(f"max_chars must be positive, got {max_chars}")
    if len(diff) <= max_chars:
        return ReviewedDiff(diff, False)

    preamble, sections = _split_sections(diff)
    if not sections:
        # No boundary to cut on. Still fails closed; we simply cannot name what
        # went unreviewed, and say so rather than implying nothing was lost.
        return ReviewedDiff(diff[:max_chars], True)

    if len(preamble) >= max_chars:
        # Pathological: the header block alone fills the budget, so no file
        # content survives at all.
        paths, unknown = _dropped_paths(sections)
        return ReviewedDiff(
            preamble[:max_chars], True, tuple(sorted(set(paths))), (), unknown)

    budget = max_chars - len(preamble)
    kept: list[str] = []
    dropped: list[str] = []
    for sec in sections:
        if len(sec) <= budget:
            kept.append(sec)
            budget -= len(sec)
        else:
            dropped.append(sec)

    if not kept:
        # Not one whole file fits. Hand over the first one cut mid-hunk — the
        # single place that happens — so the reviewer has material to work with,
        # and label it `partial`: supplied as context, never reviewed.
        paths, unknown = _dropped_paths(sections[1:])
        first = _section_paths(sections[0])
        if not first:
            # The partial file's own header is unparseable. Counting it here is
            # what stops the caller reporting "no parseable file headers" when a
            # boundary WAS found — that message belongs to a different input.
            unknown += 1
        return ReviewedDiff(
            (preamble + sections[0])[:max_chars], True,
            tuple(sorted(set(paths))), tuple(sorted(set(first))), unknown,
        )

    paths, unknown = _dropped_paths(dropped)
    return ReviewedDiff(
        preamble + "".join(kept), True, tuple(sorted(set(paths))), (), unknown)


def filter_generated_paths(diff: str) -> tuple[str, list[str]]:
    """Drop generated file-sections from a unified diff.

    A section is excluded only when it touches at least one path AND **every**
    path it touches is generated. Requiring *all* sides to be generated means a
    rename that moves real source into (or out of) a generated dir — e.g.
    ``plugins/x/real.py → .shipwright/compliance/real.py`` — is NEVER silently
    dropped; the real code stays in the reviewed diff.

    Returns ``(filtered_diff, excluded_paths)`` — sorted + deduped. A diff with
    no ``diff --git`` header (unexpected) is returned unchanged with an empty
    excluded list, so a parse surprise never silently blanks the review.
    """
    preamble, sections = _split_sections(diff)
    if not sections:
        return diff, []

    kept: list[str] = [preamble]
    excluded: set[str] = set()
    for text in sections:
        paths = _section_paths(text)
        if paths and all(is_generated_path(p) for p in paths):
            excluded.update(paths)
        else:
            kept.append(text)  # any real-source side keeps the whole section
    return "".join(kept), sorted(excluded)
