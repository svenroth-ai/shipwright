"""Tests for ``anti_ratchet_check.py`` — core rule + worktree mode.

Sister-file ``test_anti_ratchet_check_staged.py`` covers staged-mode +
CLI surface + drift-protection marker, keeping each test module under
the 300-LOC bloat baseline.

The check is the pre-commit + CI gate that blocks anti-ratchet on the
bloat baseline. Block rule: for every entry in baseline, if measured-LOC
> entry.current, exit 1. New files outside baseline are advisory.
Missing baseline = fail-open exit 0. Stale entries = advisory.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "shared" / "scripts" / "hooks" / "anti_ratchet_check.py"


def _git(cwd: Path, *args: str) -> str:
    res = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )
    return res.stdout


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    (repo / "a.py").write_text("\n".join(f"line{i}" for i in range(310)) + "\n")
    (repo / "b.py").write_text("short\n")
    _git(repo, "add", "a.py", "b.py")
    _git(repo, "commit", "-q", "-m", "initial")
    return repo


def _write_baseline(repo: Path, entries: list[dict]) -> Path:
    target = repo / "shipwright_bloat_baseline.json"
    target.write_text(
        json.dumps({"version": 1, "entries": entries}, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def _run_check(repo: Path, *extra: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--project-root", str(repo), *extra],
        capture_output=True,
        text=True,
        env=env,
    )


def test_no_baseline_file_fails_open(tmp_path):
    """Missing baseline → exit 0 (fail-open) with stderr diagnostic."""
    repo = _init_repo(tmp_path)
    res = _run_check(repo, "--worktree")
    assert res.returncode == 0
    assert "baseline" in res.stderr.lower()


def test_baseline_in_sync_passes(tmp_path):
    """File at exactly `current` → no ratchet, exit 0."""
    repo = _init_repo(tmp_path)
    _write_baseline(repo, [
        {"path": "a.py", "limit": 300, "current": 310,
         "state": "grandfathered", "adr": None},
    ])
    res = _run_check(repo, "--worktree")
    assert res.returncode == 0, res.stderr


def test_ratchet_above_current_blocks(tmp_path):
    """File grew past entry.current → exit 1."""
    repo = _init_repo(tmp_path)
    (repo / "a.py").write_text("\n".join(f"line{i}" for i in range(400)) + "\n")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-q", "-m", "bump")
    _write_baseline(repo, [
        {"path": "a.py", "limit": 300, "current": 310,
         "state": "grandfathered", "adr": None},
    ])
    res = _run_check(repo, "--worktree")
    assert res.returncode == 1
    assert "a.py" in res.stdout + res.stderr


def test_block_regardless_of_state(tmp_path):
    """Anti-ratchet rule is state-agnostic — exception entries block too."""
    repo = _init_repo(tmp_path)
    (repo / "a.py").write_text("\n".join(f"line{i}" for i in range(400)) + "\n")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-q", "-m", "bump")
    _write_baseline(repo, [
        {"path": "a.py", "limit": 300, "current": 310,
         "state": "exception", "adr": "ADR-999"},
    ])
    res = _run_check(repo, "--worktree")
    assert res.returncode == 1


def test_new_crossing_is_advisory_only(tmp_path):
    """File outside baseline that exceeds limit → exit 0 + stderr note."""
    repo = _init_repo(tmp_path)
    (repo / "b.py").write_text("\n".join(f"x{i}" for i in range(350)) + "\n")
    _git(repo, "add", "b.py")
    _git(repo, "commit", "-q", "-m", "bump-b")
    _write_baseline(repo, [
        {"path": "a.py", "limit": 300, "current": 310,
         "state": "grandfathered", "adr": None},
    ])
    res = _run_check(repo, "--worktree")
    assert res.returncode == 0
    assert "new" in res.stderr.lower() or "advisory" in res.stderr.lower()
    assert "b.py" in res.stderr


def test_stale_entry_is_advisory_only(tmp_path):
    """Baseline entry whose file no longer exists → exit 0 + stale note."""
    repo = _init_repo(tmp_path)
    _write_baseline(repo, [
        {"path": "gone.py", "limit": 300, "current": 500,
         "state": "grandfathered", "adr": None},
        {"path": "a.py", "limit": 300, "current": 310,
         "state": "grandfathered", "adr": None},
    ])
    res = _run_check(repo, "--worktree")
    assert res.returncode == 0
    assert "stale" in res.stderr.lower() or "gone.py" in res.stderr


def test_malformed_baseline_fails_open(tmp_path):
    """Malformed JSON → exit 0 with diagnostic."""
    repo = _init_repo(tmp_path)
    (repo / "shipwright_bloat_baseline.json").write_text("{ bad json", encoding="utf-8")
    res = _run_check(repo, "--worktree")
    assert res.returncode == 0


def test_ratchet_diagnostic_includes_block_table(tmp_path):
    """Block output must contain a structured table the PR comment parses."""
    repo = _init_repo(tmp_path)
    (repo / "a.py").write_text("\n".join(f"line{i}" for i in range(400)) + "\n")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-q", "-m", "bump")
    _write_baseline(repo, [
        {"path": "a.py", "limit": 300, "current": 310,
         "state": "grandfathered", "adr": None},
    ])
    res = _run_check(repo, "--worktree")
    combined = res.stdout + res.stderr
    assert "ANTI-RATCHET" in combined.upper()
    assert "a.py" in combined
    assert "310" in combined
    assert ("400" in combined) or ("401" in combined)
