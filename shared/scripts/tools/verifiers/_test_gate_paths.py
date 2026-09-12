"""Shared path-safety helpers for the FR-01.06/FR-01.07 test-phase gates
(sub-iterate ``e3-checks-test-security``). Split out of ``_test_gate_extras.py``
the moment it crossed 300 lines a second time (round 5, Tier-3 CI review on
PR #748 added the escape/absence distinction below) — the same reason
``_test_gate_specs.py`` and ``_test_gate_fidelity.py`` were split out of it
originally.
"""

from __future__ import annotations

import os
from pathlib import Path


def _is_within(root: Path, candidate: Path) -> bool:
    """Whether ``candidate``'s RESOLVED location stays inside ``root``'s
    RESOLVED location. ``os.path.commonpath`` (not ``str.startswith``,
    not ``Path.is_relative_to`` alone) so drive-letter/case normalization on
    Windows and a POSIX symlink both resolve to the same true answer."""
    try:
        resolved_root = str(root.resolve())
        common = os.path.commonpath([resolved_root, str(candidate.resolve())])
    except (OSError, ValueError):
        return False
    return common == resolved_root


def _safe_project_file(project_root: Path, relative_name: str) -> Path | None:
    """Resolve ``project_root / relative_name``, returning it only when it
    exists, is a regular file, and its RESOLVED location stays inside the
    RESOLVED project root.

    A project-controlled fixed-name artifact (``e2e-results.json``,
    ``shipwright_test_results.json``, ``design-fidelity-report.json``) could
    be committed as a symlink pointing outside the project tree — the same
    escape class PR #729 round 9 fixed for a plugin's own fixed candidate
    paths. Treated identically to "missing" (``None``) rather than raising,
    so a caller's existing SKIP-on-absence branch handles it for free.

    A caller that needs to tell "genuinely absent" apart from "present but
    escaping" — because the latter must FAIL rather than SKIP, or an
    attacker-controlled symlink could suppress the whole gate — should use
    :func:`_project_file_or_escape` instead.
    """
    path, _escaped = _project_file_or_escape(project_root, relative_name)
    return path


def _project_file_or_escape(project_root: Path, relative_name: str) -> tuple[Path | None, bool]:
    """Like :func:`_safe_project_file`, but also reports whether a file
    exists at ``relative_name`` yet resolves outside the project root, so a
    caller for whom that distinction matters can FAIL an escaping artifact
    instead of treating it the same as an honestly absent one (Tier-3 CI
    review, PR #748: a symlinked ``design-fidelity-report.json`` pointing
    outside the tree was silently read as "nothing to recompute" and let the
    whole gate SKIP rather than FAIL).

    Returns ``(path, escaped)``: ``(Path, False)`` when present and safe,
    ``(None, False)`` when genuinely absent or unreadable, ``(None, True)``
    when a file exists at that name but its resolved location escapes the
    project root **or** the entry is a symlink that does not resolve to a
    regular file at all (dangling, or pointing at a directory) — Tier-3 CI
    review, PR #748, round 5: a dangling symlink used to fold into the same
    ``(None, False)`` "genuinely absent" result via a plain ``is_file()``
    check, even though a symlink dirent existing at all is itself the same
    class of tamper signal an escaping symlink already is (a legitimate
    build never leaves a broken symlink where an evidence file belongs).
    """
    candidate = project_root / relative_name
    try:
        is_symlink = candidate.is_symlink()
        exists = candidate.is_file()
    except OSError:
        return None, False
    if not exists:
        return (None, True) if is_symlink else (None, False)
    if _is_within(project_root, candidate):
        return candidate, False
    return None, True


__all__ = [
    "_is_within",
    "_safe_project_file",
    "_project_file_or_escape",
]
