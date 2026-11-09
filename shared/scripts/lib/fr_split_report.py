"""The operator-facing half of ``fr_split``: what a cut would do, in words, and the numbers other branches already took (atomic-frs U2b-prep).

Stdlib only, plus :func:`lib.fr_split_spec.taken_fr_numbers`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from lib.fr_split_spec import taken_fr_numbers

__all__ = ["origin_numbers", "origin_readable", "report"]


def origin_readable(root: Path) -> bool:
    """Whether ``origin/main`` exists as a ref here (the collision check against trunk can only run when it does)."""
    try:
        return subprocess.run(["git", "rev-parse", "--verify", "--quiet", "origin/main"], cwd=root, capture_output=True, check=False, timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def origin_numbers(root: Path, rels: list[str], major: str) -> set[int]:
    """FR numbers (under ``FR-<major>.``) that the spec files at ``origin/main`` (as last fetched; this does not fetch) already use.

    A parallel iterate may have minted the number this tree would pick next; reading the trunk's copy of each spec
    catches that before the cut, not at merge. Reads every ``.shipwright/planning/*/spec.md`` that ``origin/main`` lists (a spec
    file only trunk has too) plus ``rels``; a missing remote, ref or file reads as nothing (the local tree still guards).
    Run ``git fetch origin main`` first for a current answer."""
    taken: set[int] = set()
    try:
        ls = subprocess.run(["git", "ls-tree", "-r", "--name-only", "origin/main", "--", ".shipwright/planning"], cwd=root,
                            capture_output=True, check=False, timeout=60)
        listed = [x for x in ls.stdout.decode("utf-8", errors="replace").splitlines() if x.endswith("/spec.md")] if ls.returncode == 0 else []
    except (OSError, subprocess.SubprocessError):
        listed = []
    for rel in dict.fromkeys([*rels, *listed]):
        try:
            proc = subprocess.run(["git", "show", f"origin/main:{rel}"], cwd=root, capture_output=True, check=False, timeout=60)
        except (OSError, subprocess.SubprocessError):  # no git binary, or a hung git: reads as nothing, the local tree still guards
            continue
        if proc.returncode == 0:
            taken |= taken_fr_numbers(proc.stdout.decode("utf-8", errors="replace"), major)
    return taken


def _row(new_spec: str, fr: str) -> str:
    """The table row the cut writes for ``fr`` (its Priority / Basis / Layers are copied from the source row unless the grouping sets them)."""
    for line in new_spec.splitlines():
        if line.startswith(f"| {fr} ") or line.startswith(f"|{fr} "):
            return line.strip()
    return ""


def report(root: Path, grouping: dict, result: dict) -> str:
    src = grouping["source"]
    ids = result["new_ids"]
    lines = [f"fr_split {src}: {len(result['moves'])} criteria move into {len(ids)} new requirement(s)",
             f"  new ids (checked against this tree, the AC registry and origin/main): {', '.join(ids)}"
             if result.get("origin_ref", True) else
             f"  new ids (checked against this tree and the AC registry ONLY - origin/main is not readable here, run `git fetch origin main`): {', '.join(ids)}"]
    new_spec = next(iter(result["files"].values()))[1] if result["files"] else ""
    for fr, p in zip(ids, grouping["parts"]):
        lines.append(f"  {fr} {p['title']}: " + ", ".join(f"AC{int(a):02d}" for a in p["acs"]))
        lines.append(f"    description: {p['description']}")
        lines.append(f"    table row (Priority/Basis/Layers copied from {src} unless set): {_row(new_spec, fr)}")
    lines.append(f"  {src} keeps the other criteria; {result['tag_files']} test file(s) get their tags re-pointed")
    if result.get("fr_level_tags"):
        lines.append(f"  test files with a FR-level tag on {src} (stay on {src}, check they belong there): {', '.join(result['fr_level_tags'])}")
    lines += [f"note: {n}" for n in result["notes"]]
    lines += [f"PROBLEM: {x}" for x in result["problems"]]
    lines.append("conservation: " + ("FAILED" if result["problems"] else "ok (catalog, bindings, names, shared tests)"))
    return "\n".join(lines)
