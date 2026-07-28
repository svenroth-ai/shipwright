"""A mid-phase handoff must not erase the canon marker a closure recorded.

`build` Step 11 writes a mid-split handoff to the SAME tracked
`session_handoff.md` that the split-level C3 closure marked, deliberately
without `--canon-marker` (it is not a canon closure). Before
iterate-2026-07-27-c3-phase-history-join that write DROPPED the marker, so Canon
C3 reported "no canon marker" for every phase until the next split closed — a
routine housekeeping step silently invalidating a completed split's evidence.

The fix is opt-in on purpose: preserving unconditionally would let a marker
outlive the run that wrote it, which is the staleness C3 exists to detect.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WRITER = REPO_ROOT / "shared" / "scripts" / "tools" / "generate_session_handoff.py"

sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.canon_frontmatter import parse_canon_frontmatter  # noqa: E402

RUN = "build-20260727-101500-core"


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / ".shipwright" / "agent_docs").mkdir(parents=True)
    (root / "shipwright_run_config.json").write_text(
        '{"status": "complete", "pipeline": [], "completed_steps": []}', encoding="utf-8"
    )
    (root / ".shipwright" / "agent_docs" / "session_handoff.md").write_text(
        f'---\ncanon_generated: true\nrun_id: "{RUN}"\nphase: "build"\n'
        f'reason: "build phase complete: split 1"\n'
        f'timestamp: "2026-07-27T10:15:00+00:00"\n---\n\n# Session Handoff\n',
        encoding="utf-8",
    )
    return root


def _run(root: Path, *extra: str) -> None:
    proc = subprocess.run(
        [sys.executable, str(WRITER), "--project-root", str(root),
         "--reason", "mid-build handoff: section 3 in_progress", *extra],
        capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, proc.stderr


def _marker(root: Path) -> dict | None:
    return parse_canon_frontmatter(
        (root / ".shipwright" / "agent_docs" / "session_handoff.md").read_text(
            encoding="utf-8"
        )
    )


def test_a_mid_phase_handoff_keeps_the_marker_when_asked(tmp_path):
    root = _project(tmp_path)

    _run(root, "--preserve-canon-marker")

    marker = _marker(root)
    assert marker is not None, "the split-level canon marker was erased"
    assert marker["run_id"] == RUN
    assert marker["phase"] == "build"
    assert marker["timestamp"] == "2026-07-27T10:15:00+00:00"


def test_the_body_is_still_regenerated(tmp_path):
    """Preserving the marker must not turn the write into a no-op — the point of
    a mid-build handoff is the fresh body underneath it."""
    root = _project(tmp_path)

    _run(root, "--preserve-canon-marker")

    text = (root / ".shipwright" / "agent_docs" / "session_handoff.md").read_text(
        encoding="utf-8"
    )
    assert "mid-build handoff: section 3 in_progress" in text


def test_without_the_flag_behaviour_is_unchanged(tmp_path):
    """The regression itself, pinned: the default still drops the marker, so the
    flag is what changed and nothing else."""
    root = _project(tmp_path)

    _run(root)

    assert _marker(root) is None


def test_the_flag_invents_nothing_when_there_is_no_marker(tmp_path):
    root = _project(tmp_path)
    (root / ".shipwright" / "agent_docs" / "session_handoff.md").write_text(
        "# Session Handoff\n", encoding="utf-8"
    )

    _run(root, "--preserve-canon-marker")

    assert _marker(root) is None


def test_the_flag_is_harmless_when_the_handoff_does_not_exist(tmp_path):
    root = _project(tmp_path)
    (root / ".shipwright" / "agent_docs" / "session_handoff.md").unlink()

    _run(root, "--preserve-canon-marker")

    assert (root / ".shipwright" / "agent_docs" / "session_handoff.md").is_file()
    assert _marker(root) is None


def test_a_degraded_canon_write_does_not_resurrect_the_old_marker(tmp_path, monkeypatch):
    """`--canon-marker` with no `SHIPWRIGHT_RUN_ID` degrades: it warns and writes
    the handoff WITHOUT frontmatter. If preservation also fired there, that write
    would come back carrying the PREVIOUS run's marker — a write that just failed
    to earn a marker, laundered into one. Preservation is for writes that never
    asked for a marker, not for writes that asked and missed."""
    root = _project(tmp_path)
    monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)

    proc = subprocess.run(
        [sys.executable, str(WRITER), "--project-root", str(root),
         "--reason", "canon closure", "--phase", "build",
         "--canon-marker", "--preserve-canon-marker"],
        capture_output=True, text=True, timeout=180,
        env={k: v for k, v in os.environ.items() if k != "SHIPWRIGHT_RUN_ID"},
    )

    assert proc.returncode == 0, proc.stderr
    assert "SHIPWRIGHT_RUN_ID is unset" in proc.stderr
    assert _marker(root) is None, "a degraded canon write must not inherit a marker"
