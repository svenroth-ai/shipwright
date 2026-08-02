#!/usr/bin/env python3
"""Git plumbing for the post-Build risk re-check: what did this unit change?

Extracted from :mod:`diff_risk_recheck` so both stay under the 300-line source
limit, mirroring how ``risk_detectors`` was split out of ``classify_complexity``.
The seam is real, not cosmetic: everything here talks to git and is exercised by
monkeypatching :func:`_git`, while the decision logic next door is pure.

**The change set is the WORKING TREE.** The campaign runner commits at F6, well
after Step 3.4 runs, so a committed range (``base...HEAD``) is EMPTY at that
point and a re-check built on it would silently report "no flags" for every unit
— reproducing the exact blindness Step 3.4 exists to remove. Three sources are
unioned:

* ``git diff --numstat --no-renames -z <fork-point>`` — committed + staged +
  unstaged.
* ``git ls-files --others --exclude-standard --full-name -z`` — untracked,
  because a brand-new hook file appears in no diff at all.
* The fork point itself, not the ref's tip (see :func:`resolve_base`).

``--no-renames`` is load-bearing. With rename detection on, moving
``.github/workflows/security.yml`` to ``security.yml.disabled`` emits ONE record
carrying only the NEW path, so disabling a security workflow raises no CI flag.
Verified against real git: detection on yields the single combined path
``.github/workflows/{security.yml => security.yml.disabled}``, which fails the
``\\.ya?ml$`` anchor. With it off the move is a delete plus an add, and the old
path is seen.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _count(field: str) -> int:
    """numstat counts; binary files report `-`."""
    return int(field) if field.isdigit() else 0


def parse_numstat_z(raw: str) -> tuple[list[str], int]:
    """Parse `git diff --numstat --no-renames -z` into (paths, added+deleted).

    `-z` so a newline in a filename is data, not a record separator.
    ``--no-renames`` is assumed, making every record ``added TAB deleted TAB path
    NUL``; the rename shape (``… TAB NUL old NUL new NUL``, reporting ONLY the new
    path) cannot occur. An empty path therefore means rename detection was left on
    — which hides a workflow moved OUT of the CI boundary — so this raises."""
    paths: list[str] = []
    total = 0
    for token in raw.split("\0"):
        if not token:
            continue
        parts = token.split("\t", 2)
        if len(parts) < 2:
            continue
        total += _count(parts[0]) + _count(parts[1])
        path = parts[2] if len(parts) > 2 else ""
        if not path:
            raise ValueError(
                "numstat record has no path — rename detection appears to be on; "
                "this parser requires --no-renames so both sides of a move are seen"
            )
        paths.append(path)
    return paths, total


def parse_untracked_z(raw: str) -> list[str]:
    """Parse `git ls-files --others --exclude-standard -z` output."""
    return [t for t in raw.split("\0") if t]


def _git(root: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(  # noqa: S603 — argument array, never shell=True
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout


def resolve_base(root: Path, base_ref: str) -> str:
    """Resolve the FORK POINT, not the ref's tip.

    ``base_branch`` is ``origin/main`` in serial mode, which equals the fork point
    only until something fetches. Anything advancing it mid-Build would make
    upstream files read as changed in reverse — an unrelated upstream workflow edit
    would then STRICT-STOP the campaign citing `ci_paths` this unit never touched.
    Falls back to the ref when there is no common ancestor."""
    rc, out = _git(root, "merge-base", "HEAD", base_ref)
    if rc == 0 and out.strip():
        return out.strip()
    rc, out = _git(root, "rev-parse", "--verify", "--quiet", f"{base_ref}^{{commit}}")
    sha = out.strip()
    if rc != 0 or not sha:
        raise RuntimeError(f"cannot resolve base ref {base_ref!r}")
    return sha


def untracked_loc(root: Path, paths: list[str]) -> int:
    """Added-line count for untracked files.

    `git diff --numstat` does not see untracked files at all, so counting only its
    output would report `diff_loc: 0` for a unit whose whole change is new files —
    and Step 3.5's `> 100 LOC` arm would never fire for exactly the change shape
    that has no prior art to review against. An untracked file is entirely added,
    so its line count IS its added count.

    Binary files contribute 0, matching numstat's `-` convention. Unreadable or
    vanished files are skipped rather than raising: this is a review-sizing
    heuristic, and failing the run over one odd file would be worse than a
    slightly low count (the path itself is still detected either way).
    """
    total = 0
    for rel in paths:
        try:
            blob = (root / rel).read_bytes()
        except OSError:
            continue
        if b"\0" in blob:
            continue  # binary — numstat reports `-`, i.e. 0
        total += blob.count(b"\n") + (0 if blob.endswith(b"\n") or not blob else 1)
    return total


def collect_change_set(root: Path, base_ref: str) -> tuple[list[str], int]:
    """Working-tree change set vs the fork point, plus its added+deleted count.

    Resolving to a SHA first also means the value handed to `git diff` can never be
    mistaken for an option — the portable form of `--end-of-options`."""
    sha = resolve_base(root, base_ref)
    rc, out = _git(root, "diff", "--numstat", "--no-renames", "-z", sha, "--")
    if rc != 0:
        raise RuntimeError(f"git diff against {sha[:8]} failed")
    paths, loc = parse_numstat_z(out)
    # `--full-name` keeps untracked paths repo-root-relative like the diff half, so
    # the coordinate systems cannot diverge if project_root is a subdirectory. A
    # failure here must RAISE: untracked is the leg that sees a brand-new hook
    # file, so passing on an empty result reproduces the silent stand-down.
    rc, out = _git(root, "ls-files", "--others", "--exclude-standard", "--full-name", "-z")
    if rc != 0:
        raise RuntimeError("git ls-files --others failed — untracked files unknown")
    untracked = parse_untracked_z(out)
    paths.extend(untracked)
    return paths, loc + untracked_loc(root, untracked)
