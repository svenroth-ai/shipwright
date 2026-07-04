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

__all__ = ["is_generated_path", "filter_generated_paths"]

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

# Split boundary — a unified diff starts each file section with `diff --git `.
_DIFF_GIT_RE = re.compile(r"^diff --git a/(.+?) b/(.+?)\s*$")


def is_generated_path(path: str) -> bool:
    """True iff ``path`` is a producer-generated artifact (not reviewable code)."""
    p = (path or "").strip()
    if any(p.startswith(pre) for pre in _GENERATED_PREFIXES):
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
    lines = diff.splitlines(keepends=True)
    preamble: list[str] = []
    sections: list[list[str]] = []
    cur: list[str] | None = None
    for ln in lines:
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

    if not sections:
        return diff, []

    kept: list[str] = list(preamble)
    excluded: set[str] = set()
    for sec in sections:
        text = "".join(sec)
        paths = _section_paths(text)
        if paths and all(is_generated_path(p) for p in paths):
            excluded.update(paths)
        else:
            kept.append(text)  # any real-source side keeps the whole section
    return "".join(kept), sorted(excluded)
