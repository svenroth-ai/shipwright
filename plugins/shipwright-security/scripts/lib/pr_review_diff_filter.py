"""Unified-diff parsing for the Tier-3 PR reviewer — the MECHANISM.

Where a file section begins and ends, which paths it touches, where the size cap
may cut, and which sections the generated-artifact policy drops. That policy —
*what counts as generated* — lives in `pr_review_generated`, because it changes
for a different reason (a new producer) and its over-reach is a security bug,
not a parsing bug.

The single definition of "a file boundary" lives here, so the generated filter
and the size cap can never disagree about where one file ends. It is LF-anchored:
git ends a diff line at LF and nothing else, and a parser that thinks otherwise
lets a PR forge a boundary from inside its own hunk (see `_split_sections`).

Split out of ``pr_review_lib`` so the diff-parsing cluster is its own cohesive,
unit-testable module and every file stays under the source-size guideline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The membership policy — re-exported so `pr_review_lib.is_generated_path` and
# every existing caller keep working. See that module for the governing rule.
from pr_review_generated import is_generated_path  # noqa: F401

__all__ = [
    "MAX_DIFF_CHARS", "ReviewedDiff", "count_sections",
    "filter_generated_paths", "is_generated_path", "truncate_diff_at_boundary",
]

# Over this, the diff is reviewed on a boundary-truncated copy and the gate
# FAILS CLOSED — a large diff must not bypass review by size (B4.5,
# iterate-2026-06-17-pr-review-truncation-failclosed).
#
# CHARACTERS, not tokens: ~250-285k input tokens at a full cap, against the
# review model's reported 1M-token context (~4x margin). Raised from 200_000
# by iterate-2026-07-27-pr-review-diff-cap, where the old cap failed ordinary
# large PRs closed (#447: 467,591 chars AFTER filtering).
MAX_DIFF_CHARS = 1_000_000

# Split boundary — a unified diff starts each file section with `diff --git `.
_DIFF_GIT_RE = re.compile(r"^diff --git a/(.+?) b/(.+?)\s*$")

# LF-anchored section boundary. Python's MULTILINE `^` matches at the start of
# the string and after a `\n` — and after nothing else — which is exactly git's
# notion of a line. `str.splitlines()` is NOT equivalent (see _split_sections).
_SECTION_SPLIT_RE = re.compile(r"(?m)^(?=diff --git )")


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
    # `split("\n")`, never `splitlines()` — the same LF-only rule as
    # `_split_sections`; otherwise a `\f`-borne fragment can present itself as a
    # `--- a/…` line and put a path into the list that the PR never touched.
    #
    # Stop at the first `@@`: inside a hunk, `---`/`+++` at column 0 are
    # ORDINARY git output (adding a line reading `++ b/x` emits `+++ b/x`), not
    # file headers — treating them as such let a PR mint paths it never touched.
    for ln in section.split("\n"):
        if ln.startswith("@@"):
            break
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

    **Split on LF only.** A content line in a unified diff carries a ``+``, ``-``
    or space prefix, so a header at the start of a *git* line is always a real
    header — but only once "line" means the same thing here as it does to git.
    ``str.splitlines()`` also breaks on ``\\v \\f \\r \\x1c \\x1d \\x1e \\x85
    \\u2028 \\u2029``, none of which git treats as a terminator, so it lets a PR
    manufacture a boundary from *inside* a hunk: the harmless half keeps the
    ``+`` prefix and the rest becomes a counterfeit section. If that counterfeit
    header names a generated path the filter drops it — silently taking the
    attacker's real lines with it, on a gate whose input is untrusted by
    definition. The fetch reads bytes for the same reason (``pr_review_gh``).
    """
    # `re.split` on a zero-width match always emits a leading element, so parts
    # is never empty and parts[0] is "" when the diff opens straight on a header
    # — no special-casing needed, and a guard for it would be unreachable.
    parts = _SECTION_SPLIT_RE.split(diff)
    return parts[0], parts[1:]


def count_sections(diff: str) -> int:
    """How many file sections a diff carries. Zero means nothing to review."""
    return len(_split_sections(diff)[1])


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
