"""Read the traceability manifest being committed: the INDEX, then ``HEAD``, then the working tree.

Split out of ``rtm_manifest_coverage`` (which re-exports these names). The local
pipeline regenerates the working-tree copy fail-closed (every link ``not_run``),
so the commit gate never trusts it first. The staged (index) copy is what the
commit records -- committing a corrected or regenerated manifest is measured on
that copy; unchanged, the index equals ``HEAD``. Only a path absent from the index
(e.g. a staged ``git rm --cached``) falls through to ``HEAD``. When the git read
fails for a reason other than "not a git repo" / "no such file in git" (git
missing, a timeout, an unborn HEAD, ...) the working-tree fallback is announced as
a note instead of being taken silently -- one note, never one per git read.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

MANIFEST_RELPATH = Path(".shipwright") / "compliance" / "test-traceability.json"
_GIT_TIMEOUT_S = 5
# git's own words with LC_ALL=C: the path is not staged, so HEAD is consulted next
_INDEX_MISSES = ("but not in the index", "nor in the index", "but not at stage 0")
# the cases where the working tree IS the answer
_EXPECTED_MISSES = (
    ("not a git repository", "not a git repo"),
    ("does not exist in 'HEAD'", "HEAD has no such file"),
    ("exists on disk, but not in 'HEAD'", "HEAD has no such file"),
)
EXPECTED_REASONS = frozenset(reason for _, reason in _EXPECTED_MISSES)
_UNBORN = "HEAD has no commit yet"


def _git_blob(project_root: str | Path, spec: str, what: str) -> tuple[bytes | None, str]:
    """``(blob, "")`` or ``(None, stderr-or-reason)``; *what* names the read in a reason.

    List args, no shell: nothing for MSYS path conversion to rewrite. ``LC_ALL=C``
    keeps git's messages classifiable on a localized machine.
    """
    env = {**os.environ, "LC_ALL": "C", "LANGUAGE": "C"}
    try:
        out = subprocess.run(
            ["git", "-C", str(project_root), "cat-file", "blob", spec],
            capture_output=True, timeout=_GIT_TIMEOUT_S, check=False, env=env,
        )
    except subprocess.TimeoutExpired:
        return None, f"reading {what} timed out after {_GIT_TIMEOUT_S} s"
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"git is not runnable ({type(exc).__name__})"
    if out.returncode == 0:
        return out.stdout, ""
    stderr = (out.stderr or b"").decode("utf-8", "replace").strip()
    return None, stderr or f"exit {out.returncode}"


def _classify(stderr: str, what: str) -> str:
    """A short reason for a failed ``git cat-file`` (already-short reasons pass through)."""
    if stderr.startswith(("git is not runnable", "reading ")):
        return stderr
    for needle, reason in _EXPECTED_MISSES:
        if needle in stderr:
            return reason
    if "invalid object name 'HEAD'" in stderr or "bad revision 'HEAD'" in stderr:
        return _UNBORN
    first = stderr.splitlines()[0][:160]
    return f"reading {what} failed ({first})"


def _committed_bytes(project_root: str | Path) -> tuple[bytes | None, str | None]:
    """``(staged-or-HEAD copy, None)`` or ``(None, reason)`` -- why the git read failed.

    ``:./<path>`` / ``HEAD:./<path>`` resolve relative to ``-C`` (a subdirectory
    project works). ``HEAD`` is read only when the index has no such path; any other
    index failure (git missing, timeout, not a repo) would fail on ``HEAD`` alike,
    so it is reported once.
    """
    rel = MANIFEST_RELPATH.as_posix()
    raw, stderr = _git_blob(project_root, f":./{rel}", "the index")
    if raw is not None:
        return raw, None
    if not any(needle in stderr for needle in _INDEX_MISSES):
        return None, _classify(stderr, "the index")
    raw, stderr = _git_blob(project_root, f"HEAD:./{rel}", "HEAD")
    return (raw, None) if raw is not None else (None, _classify(stderr, "HEAD"))


def read_manifest_noted(
    project_root: str | Path,
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    """Like :func:`read_manifest`, plus notes for a working-tree read taken unexpectedly.

    With no working-tree copy either, an unexpected git failure still returns the
    note ``committed manifest unreadable: <why>`` (an unborn HEAD with nothing
    staged is simply no manifest).
    """
    label = MANIFEST_RELPATH.as_posix()
    notes: list[str] = []
    raw, why = _committed_bytes(project_root)
    if raw is None:
        unexpected = bool(why) and why not in EXPECTED_REASONS
        path = Path(project_root) / MANIFEST_RELPATH
        if not path.is_file():
            if unexpected and why != _UNBORN:
                notes.append(f"committed manifest unreadable: {why}")
            return None, None, notes
        if unexpected:
            notes.append(f"reading working-tree manifest: {why}")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            return None, f"cannot read {label}: {type(exc).__name__}", notes
    else:
        label = f"committed {label}"
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except ValueError as exc:
        return None, f"cannot read {label}: {type(exc).__name__}", notes
    if not isinstance(data, dict):
        return None, f"{label} is not a JSON object", notes
    return data, None, notes


def read_manifest(project_root: str | Path) -> tuple[dict[str, Any] | None, str | None]:
    """``(manifest, None)``, ``(None, None)`` when absent, ``(None, reason)`` when unreadable.

    Staged (index) copy first, then HEAD; the working-tree file only as the fallback.
    """
    data, problem, _notes = read_manifest_noted(project_root)
    return data, problem
