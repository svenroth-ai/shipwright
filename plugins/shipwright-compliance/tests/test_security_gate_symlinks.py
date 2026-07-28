"""Symlink resolution in the ``check_security_scan`` gate's summary reader.

Split from ``test_security_gate.py`` at the 300-line cap.

`os.stat` FOLLOWS symlinks, so exactly one mode is ever tested and it is always
the target's. The PR-review of #492 read the earlier `lstat`-then-rebind form as
testing an unresolved mode — it did not, but a security branch a careful reader
can misread is not clear enough, so `read_security_summary` was restructured and
these pin the resulting behaviour. A dangling symlink is the interesting case:
present and broken is NOT "never scanned", so it blocks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).parent.parent / "scripts" / "hooks"
DEPLOY = {"tool_input": {"command": "deploy to jelastic"}}
SUMMARY_REL = Path(".shipwright") / "compliance" / "ci-security.json"


def _run_hook(cwd: Path) -> int:
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "check_security_scan.py")],
        input=json.dumps(DEPLOY), capture_output=True, text=True, cwd=str(cwd),
    ).returncode


def _summary_bytes(critical: int) -> str:
    return json.dumps({
        "schema": 1, "scan_date": "2026-07-28T07:51:37Z", "source": "security.yml#1",
        "by_severity": {"critical": critical, "high": 0, "medium": 0, "low": 0},
        "total": critical, "open_high_critical": critical,
        "critical_gate": "fail" if critical > 0 else "pass",
        "prompt_injection": 0, "degraded": False,
    }, indent=2, sort_keys=True)


def _symlink(src: Path, dst: Path, *, dir_target: bool = False) -> None:
    """Create a symlink, or skip. Windows needs Developer Mode/admin; no CI job
    runs on Windows (trg-80e3b3cd), so CI must never take the skip silently."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(src, dst, target_is_directory=dir_target)
    except (OSError, NotImplementedError) as exc:
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail(
                f"symlink creation failed in CI ({exc!r}); this suite must "
                "exercise the symlink branch of read_security_summary. Run on a "
                "filesystem/user that permits symlinks.")
        pytest.skip(f"symlinks not permitted on this host ({exc!r})")


def test_symlink_to_a_clean_summary_is_followed_and_allows(tmp_path: Path):
    real = tmp_path / "real-ci-security.json"
    real.write_text(_summary_bytes(0), encoding="utf-8")
    _symlink(real, tmp_path / SUMMARY_REL)
    assert _run_hook(tmp_path) == 0


def test_symlink_to_a_dirty_summary_is_followed_and_blocks(tmp_path: Path):
    real = tmp_path / "real-ci-security.json"
    real.write_text(_summary_bytes(4), encoding="utf-8")
    _symlink(real, tmp_path / SUMMARY_REL)
    assert _run_hook(tmp_path) == 2


def test_symlink_to_a_directory_blocks(tmp_path: Path):
    target = tmp_path / "some-dir"
    target.mkdir()
    _symlink(target, tmp_path / SUMMARY_REL, dir_target=True)
    assert _run_hook(tmp_path) == 2


def test_a_dangling_symlink_blocks_rather_than_reading_as_absent(tmp_path: Path):
    _symlink(tmp_path / "gone.json", tmp_path / SUMMARY_REL)
    assert _run_hook(tmp_path) == 2
