"""Tests for ``anti_ratchet_check.py`` — staged mode + CLI surface +
drift-protection marker.

Companion to ``test_anti_ratchet_check.py`` (core rule + worktree mode).
Split to keep each file under the 300-LOC bloat baseline this iterate
defends.
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
    _git(repo, "add", "a.py")
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


def test_staged_mode_ignores_unstaged_changes(tmp_path):
    """Working tree may bloat, but if nothing is staged, --staged exits 0."""
    repo = _init_repo(tmp_path)
    _write_baseline(repo, [
        {"path": "a.py", "limit": 300, "current": 310,
         "state": "grandfathered", "adr": None},
    ])
    (repo / "a.py").write_text("\n".join(f"line{i}" for i in range(500)) + "\n")
    res = _run_check(repo, "--staged")
    assert res.returncode == 0, f"unstaged bloat must NOT block: {res.stderr}"


def test_staged_mode_blocks_staged_ratchet(tmp_path):
    """Staged bloat above current → block."""
    repo = _init_repo(tmp_path)
    _write_baseline(repo, [
        {"path": "a.py", "limit": 300, "current": 310,
         "state": "grandfathered", "adr": None},
    ])
    (repo / "a.py").write_text("\n".join(f"line{i}" for i in range(500)) + "\n")
    _git(repo, "add", "a.py")
    res = _run_check(repo, "--staged")
    assert res.returncode == 1, res.stderr


def test_default_mode_is_staged(tmp_path):
    """No flag → behaves identically to --staged."""
    repo = _init_repo(tmp_path)
    _write_baseline(repo, [
        {"path": "a.py", "limit": 300, "current": 310,
         "state": "grandfathered", "adr": None},
    ])
    (repo / "a.py").write_text("\n".join(f"line{i}" for i in range(500)) + "\n")
    # NOT staged.
    res = _run_check(repo)
    assert res.returncode == 0


def test_help_lists_modes(tmp_path):
    res = _run_check(tmp_path, "--help")
    assert res.returncode == 0
    assert "--staged" in res.stdout
    assert "--worktree" in res.stdout


def test_explicit_baseline_path(tmp_path):
    """--baseline can point to a non-default path."""
    repo = _init_repo(tmp_path)
    (repo / "a.py").write_text("\n".join(f"line{i}" for i in range(400)) + "\n")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-q", "-m", "bump")
    alt = repo / "custom-baseline.json"
    alt.write_text(json.dumps({"version": 1, "entries": [
        {"path": "a.py", "limit": 300, "current": 310,
         "state": "grandfathered", "adr": None},
    ]}) + "\n", encoding="utf-8")
    res = _run_check(repo, "--worktree", "--baseline", str(alt))
    assert res.returncode == 1


def test_json_output_mode(tmp_path):
    """--json emits structured output for CI consumers."""
    repo = _init_repo(tmp_path)
    (repo / "a.py").write_text("\n".join(f"line{i}" for i in range(400)) + "\n")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-q", "-m", "bump")
    _write_baseline(repo, [
        {"path": "a.py", "limit": 300, "current": 310,
         "state": "grandfathered", "adr": None},
    ])
    res = _run_check(repo, "--worktree", "--json")
    assert res.returncode == 1
    doc = json.loads(res.stdout)
    assert doc["status"] == "block"
    assert isinstance(doc["ratchets"], list)
    assert any(r["path"] == "a.py" for r in doc["ratchets"])
    assert doc["ratchets"][0]["baseline_current"] == 310
    assert doc["ratchets"][0]["measured"] >= 400


def test_json_clean_run(tmp_path):
    """--json on a clean run reports status=ok."""
    repo = _init_repo(tmp_path)
    _write_baseline(repo, [
        {"path": "a.py", "limit": 300, "current": 310,
         "state": "grandfathered", "adr": None},
    ])
    res = _run_check(repo, "--worktree", "--json")
    assert res.returncode == 0
    doc = json.loads(res.stdout)
    assert doc["status"] == "ok"
    assert doc["ratchets"] == []


def test_anti_ratchet_check_carries_source_hash_marker():
    """Source carries an explicit drift-protection marker so the webui
    vendored copy can pin its hash. Marker form:
    ``# source-hash-canonical: <sha256>`` on one line."""
    src = _SCRIPT.read_text(encoding="utf-8")
    assert "# source-hash-canonical:" in src, (
        "anti_ratchet_check.py MUST carry a "
        "`# source-hash-canonical: <sha256>` marker for the webui "
        "vendored-copy drift check."
    )
