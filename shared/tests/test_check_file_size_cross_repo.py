"""check_file_size.py (PostToolUse bloat recorder) must only govern files
INSIDE the current project root.

Bug (found 2026-06-04): the recorder wrote a per-session marker entry for ANY
edited file over the size limit, with no project-root check. When a session
whose cwd is repo A also edits files in a SIBLING repo B (a separate checkout
with its OWN bloat baseline), ``_rel_path`` fell back to the absolute path and
recorded repo B's file into repo A's marker. The Stop gate then blocked repo
A's Stop on repo B's files as "new crossings" — even though repo B's own
anti-ratchet was satisfied. An entire session's Stop was blocked ~40 times on
sibling-repo test files it did not own.

The recorder must skip (no marker entry, no nudge) any edited file that does
not resolve to within the project root. Advisory hooks never break the tool
flow, so the skip is a plain early return.

NB (iterate-2026-06-09): the membership guard is now repo-root-relative
(``main_repo_root_or(Path.cwd())``), not cwd-relative. These tests run the hook
in a NON-git ``tmp_path`` so the resolver fails soft to cwd — behavior is
identical to the old cwd guard. The sibling-repo rejection holds for independent
git roots; a sibling that shares an ENCLOSING repo would now be governed (the
intended "whole main repo" semantic).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "hooks"
_CFS = HOOKS_DIR / "check_file_size.py"


def _env() -> dict:
    env = os.environ.copy()
    env.pop("SHIPWRIGHT_SESSION_ID", None)
    return env


def _run(cwd: Path, payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_CFS)],
        input=json.dumps(payload), capture_output=True, text=True,
        encoding="utf-8", errors="replace", cwd=str(cwd), env=_env(),
    )


def _oversize(path: Path) -> None:
    path.write_text("x\n" * 420, encoding="utf-8")  # 420 > 300 source limit


def _markers(proj: Path) -> list[Path]:
    locks = proj / ".shipwright" / "locks"
    return list(locks.glob("bloat_pending.*.json")) if locks.is_dir() else []


def test_out_of_project_edit_writes_no_marker_and_no_nudge(tmp_path):
    """A file edited OUTSIDE cwd (sibling repo) must NOT pollute this project's
    marker and must NOT emit a nudge."""
    proj = tmp_path / "proj"
    proj.mkdir()
    other_repo = tmp_path / "other_repo"
    other_repo.mkdir()
    big = other_repo / "huge.test.tsx"
    _oversize(big)

    payload = {"tool_name": "Write", "session_id": "S-X",
               "tool_input": {"file_path": str(big)}}
    result = _run(proj, payload)

    assert not _markers(proj), (
        f"out-of-project edit must write NO marker under {proj}; "
        f"found {[p.name for p in _markers(proj)]}"
    )
    assert result.stdout.strip() == "", (
        f"out-of-project edit must emit NO nudge; got: {result.stdout!r}"
    )


def test_in_project_oversize_edit_still_records_and_nudges(tmp_path):
    """Regression guard: an oversize file INSIDE cwd still records a marker
    entry AND emits the advisory nudge (behavior unchanged by the fix)."""
    proj = tmp_path / "proj"
    proj.mkdir()
    big = proj / "huge.py"
    _oversize(big)

    payload = {"tool_name": "Write", "session_id": "S-Y",
               "tool_input": {"file_path": str(big)}}
    result = _run(proj, payload)

    marker = proj / ".shipwright" / "locks" / "bloat_pending.S-Y.json"
    assert marker.is_file(), "in-project oversize edit must still record a marker"
    doc = json.loads(marker.read_text(encoding="utf-8"))
    paths = [e.get("path") for e in doc.get("entries", [])]
    assert paths and all("huge.py" in p for p in paths), (
        f"marker must record the in-project file relatively; got {paths}"
    )
    assert result.stdout.strip(), "in-project crossing must still emit a nudge"
