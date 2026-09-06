"""Full-FR-catalogue `spec.md` enumeration (Tier-3 PR review round 3, PR #679,
iterate-2026-09-06-fr-hygiene-touched-rows).

Split out of ``fr_hygiene.py`` (which crossed the 300-line guideline again):
this half answers "every `spec.md` path in the tree at a given ref" — a
`git ls-tree` walk, since duplicate-FR-id detection needs the WHOLE catalogue,
not just this run's touched files (a new row colliding with an id in an
UNCHANGED spec.md elsewhere in the catalogue is exactly as real a defect as
one split across two touched files) — while ``fr_hygiene.py`` keeps the
touched-diff orchestration. No I/O beyond the one git call each function
makes.
"""

from __future__ import annotations

import re
from pathlib import Path

from .git_helpers import _run_git

#: A `spec.md` path under any split, expressed as a pattern so it can be
#: matched against a git diff's/tree's path list instead of walking the disk.
#: `group_i_rows.scan_specs` walks the same tree but explicitly excludes
#: `iterate/` (S2b pass C2: that split holds per-run iterate specs, not the FR
#: catalogue) — this pattern does not carry that exclusion, but it is a
#: distinction without a difference here: files under `iterate/` are named
#: `{date}-{slug}.md`, never literally `spec.md`, so the two walks agree on
#: every real path in practice.
_SPEC_PATH_RE = re.compile(r"^\.shipwright/planning/[^/]+/spec\.md$")


def spec_paths_matching(paths: list[str]) -> list[str]:
    """The subset of ``paths`` that are a catalogue `spec.md`, normalised to
    forward slashes. Shared by "which of this diff's changed files are a
    spec.md" (`fr_hygiene.py`) and "which paths does `git ls-tree` list"
    (:func:`catalog_spec_paths_at`) — one pattern, one normalisation, for
    both questions."""
    hits: set[str] = set()
    for path in paths:
        norm = path.replace("\\", "/").strip()
        if _SPEC_PATH_RE.match(norm):
            hits.add(norm)
    return sorted(hits)


def catalog_spec_paths_at(project_root: Path, ref: str) -> list[str] | None:
    """Every `.shipwright/planning/*/spec.md` path that exists in the tree at
    `ref`, discovered via `git ls-tree` rather than a filesystem walk — the
    BASE commit's catalog must be read even though the worktree is currently
    checked out at HEAD, not at base: pooling only touched paths made a new
    row's one occurrence look unique whenever the untouched file carrying the
    other occurrence was never read at all.

    `None` on any git failure — fails closed, matching every other git call
    in this module family. A pathspec matching nothing (e.g.
    `.shipwright/planning` does not exist at an old base commit) is a normal
    empty result, not a failure: `git ls-tree` exits 0 either way."""
    rc, out, _ = _run_git(
        project_root, "ls-tree", "-r", "--name-only", ref,
        "--", ".shipwright/planning", timeout=15.0,
    )
    if rc != 0:
        return None
    return spec_paths_matching([ln.strip() for ln in out.splitlines() if ln.strip()])


__all__ = ["catalog_spec_paths_at", "spec_paths_matching"]
