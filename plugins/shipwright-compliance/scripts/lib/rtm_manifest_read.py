"""Read the traceability manifest as committed at ``HEAD`` (working tree only as fallback).

Split out of ``rtm_manifest_coverage`` (which re-exports these names). The local
pipeline regenerates the working-tree copy fail-closed (every link ``not_run``),
so the committed copy is the one the commit gate trusts. When the committed read
fails for a reason other than "not a git repo" / "HEAD has no such file" (git
missing, a timeout, an unborn HEAD, ...) the working-tree fallback is announced as
a note instead of being taken silently.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

MANIFEST_RELPATH = Path(".shipwright") / "compliance" / "test-traceability.json"
_GIT_TIMEOUT_S = 5
# git's own words with LC_ALL=C; the two cases where the working tree IS the answer
_EXPECTED_MISSES = (
    ("not a git repository", "not a git repo"),
    ("does not exist in 'HEAD'", "HEAD has no such file"),
    ("exists on disk, but not in 'HEAD'", "HEAD has no such file"),
)
EXPECTED_REASONS = frozenset(reason for _, reason in _EXPECTED_MISSES)


def _committed_bytes(project_root: str | Path) -> tuple[bytes | None, str | None]:
    """``(HEAD's copy, None)`` or ``(None, reason)`` -- why the committed read failed.

    ``HEAD:./<path>`` resolves relative to ``-C`` (a subdirectory project works).
    List args, no shell: nothing for MSYS path conversion to rewrite. ``LC_ALL=C``
    keeps git's messages classifiable on a localized machine.
    """
    env = {**os.environ, "LC_ALL": "C", "LANGUAGE": "C"}
    try:
        out = subprocess.run(
            ["git", "-C", str(project_root), "show",
             f"HEAD:./{MANIFEST_RELPATH.as_posix()}"],
            capture_output=True, timeout=_GIT_TIMEOUT_S, check=False, env=env,
        )
    except subprocess.TimeoutExpired:
        return None, f"git show HEAD timed out after {_GIT_TIMEOUT_S} s"
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"git is not runnable ({type(exc).__name__})"
    if out.returncode == 0:
        return out.stdout, None
    stderr = (out.stderr or b"").decode("utf-8", "replace")
    for needle, reason in _EXPECTED_MISSES:
        if needle in stderr:
            return None, reason
    if "invalid object name 'HEAD'" in stderr or "bad revision 'HEAD'" in stderr:
        return None, "HEAD has no commit yet"
    first = stderr.strip().splitlines()[0][:160] if stderr.strip() else f"exit {out.returncode}"
    return None, f"git show HEAD failed ({first})"


def read_manifest_noted(
    project_root: str | Path,
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    """Like :func:`read_manifest`, plus notes for a working-tree read taken unexpectedly."""
    label = MANIFEST_RELPATH.as_posix()
    notes: list[str] = []
    raw, why = _committed_bytes(project_root)
    if raw is None:
        path = Path(project_root) / MANIFEST_RELPATH
        if not path.is_file():
            return None, None, notes
        if why and why not in EXPECTED_REASONS:
            notes.append(f"reading working-tree manifest: {why}")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            return None, f"cannot read {label}: {type(exc).__name__}", notes
    else:
        label = f"HEAD:{label}"
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except ValueError as exc:
        return None, f"cannot read {label}: {type(exc).__name__}", notes
    if not isinstance(data, dict):
        return None, f"{label} is not a JSON object", notes
    return data, None, notes


def read_manifest(project_root: str | Path) -> tuple[dict[str, Any] | None, str | None]:
    """``(manifest, None)``, ``(None, None)`` when absent, ``(None, reason)`` when unreadable.

    Committed (HEAD) copy first; the working-tree file only as the fallback.
    """
    data, problem, _notes = read_manifest_noted(project_root)
    return data, problem
