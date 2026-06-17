"""Core logic for the bloat anti-ratchet gate.

Consumed by ``shared/scripts/hooks/anti_ratchet_check.py`` (CLI shim).
Encapsulates the block rule, the staged-vs-worktree measurement, and
the Iron-Law diagnostic body — independent of argument parsing.

Block rule (state-agnostic, Campaign A.defense):

    For every entry in ``shipwright_bloat_baseline.json``:
        if measured-LOC(path) > entry.current → RATCHET (block).

Files outside the baseline that exceed their limit are advisory; stale
entries (file gone) are advisory. ``load_baseline_override`` returns
``None`` for both an absent and a malformed baseline; the CLI consumer
fails open on an absent baseline but fails closed on a present-but-corrupt
one (a corrupt baseline must not silently disable the gate).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from . import bloat_baseline as _bb


def measure_worktree(project_root: Path, rel_path: str) -> int | None:
    p = project_root / rel_path
    if not p.is_file():
        return None
    try:
        with p.open("rb") as fh:
            return fh.read().count(b"\n")
    except OSError:
        return None


def measure_staged(project_root: Path, rel_path: str) -> int | None:
    """Return staged LOC for ``rel_path`` or None if not staged / unknown."""
    try:
        res = subprocess.run(
            ["git", "show", f":{rel_path}"],
            cwd=str(project_root),
            capture_output=True,
        )
    except FileNotFoundError:
        return None
    if res.returncode != 0:
        return None
    return res.stdout.count(b"\n")


def staged_paths(project_root: Path) -> set[str]:
    try:
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return set()
    if res.returncode != 0:
        return set()
    return {p.strip() for p in res.stdout.splitlines() if p.strip()}


def classify_entries(
    project_root: Path, entries: list[dict], mode: str
) -> tuple[list[dict], list[dict]]:
    """Return ``(ratchets, stale)`` from comparing ``entries`` against
    the on-disk (worktree) or staged content under ``project_root``."""
    ratchets: list[dict] = []
    stale: list[dict] = []
    staged: set[str] | None = staged_paths(project_root) if mode == "staged" else None

    for entry in entries:
        path = entry.get("path")
        current = entry.get("current")
        if not isinstance(path, str) or not isinstance(current, int):
            continue

        if mode == "staged":
            if staged is None or path not in staged:
                continue
            measured = measure_staged(project_root, path)
            if measured is None:
                stale.append({"path": path, "reason": "staged-delete"})
                continue
        else:
            measured = measure_worktree(project_root, path)
            if measured is None:
                stale.append({"path": path, "reason": "missing"})
                continue

        if measured > current:
            ratchets.append({
                "path": path,
                "baseline_current": current,
                "measured": measured,
                "state": entry.get("state", "grandfathered"),
                "adr": entry.get("adr"),
            })
    return ratchets, stale


def scan_new_crossings(project_root: Path, entries: list[dict]) -> list[dict]:
    """Files exceeding their limit that are NOT in the baseline."""
    known = {e.get("path") for e in entries if isinstance(e.get("path"), str)}
    return [e for e in _bb.scan(project_root) if e["path"] not in known]


def load_baseline_override(project_root: Path, override: str | None) -> dict | None:
    """Load ``shipwright_bloat_baseline.json`` (default) or ``override``."""
    if override is None:
        return _bb.load(project_root)
    target = Path(override)
    if not target.is_file():
        print(
            f"anti_ratchet: baseline not found at {target} — fail-open",
            file=sys.stderr,
        )
        return None
    try:
        doc = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"anti_ratchet: baseline unreadable ({exc!r}) — fail-open",
            file=sys.stderr,
        )
        return None
    if not isinstance(doc, dict):
        return None
    entries = doc.get("entries")
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("path"), str):
            entry["path"] = _bb.normalize_path(entry["path"])
    return doc


def emit_iron_law_block(ratchets: list[dict], stream) -> None:
    """Print the Iron-Law block body.

    Style adapted from ``obra/superpowers``
    verification-before-completion (MIT, © Jesse Vincent)."""
    print("=" * 72, file=stream)
    print("ANTI-RATCHET BLOCK — bloat baseline violation", file=stream)
    print("=" * 72, file=stream)
    print(
        "Iron Law: a file's measured LOC must not exceed its baseline "
        "`current` value.",
        file=stream,
    )
    print("", file=stream)
    header = f"{'path':<60}  {'baseline':>10}  {'measured':>10}"
    print(header, file=stream)
    print(f"{'-' * 60}  {'-' * 10}  {'-' * 10}", file=stream)
    for r in ratchets:
        print(
            f"{r['path']:<60}  {r['baseline_current']:>10}  "
            f"{r['measured']:>10}",
            file=stream,
        )
    print("", file=stream)
    print("Remediations (pick one):", file=stream)
    print("  1. Shrink the file below baseline `current` (preferred).", file=stream)
    print("  2. Split the file, refresh baseline via adopt baseline-generator.", file=stream)
    print(
        "  3. Write a bloat-exception ADR via "
        ".shipwright/planning/adr/_template-bloat-exception.md",
        file=stream,
    )
    print("     and bump `current` deliberately in the same commit.", file=stream)
    print("", file=stream)
    print(
        "Rationalizations to refuse: 'just one more line', 'temporary',",
        file=stream,
    )
    print(
        "'will refactor next iterate', 'tests don't count'. They count.",
        file=stream,
    )
    print("=" * 72, file=stream)
