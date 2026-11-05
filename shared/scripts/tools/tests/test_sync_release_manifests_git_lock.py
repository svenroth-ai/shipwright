"""Git-integration coverage for the ``package_lock_json`` format (sync +
``--verify-commit`` against the committed blob)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # shared/

from scripts.lib.manifest_sync_core import git  # noqa: E402
from scripts.tools.sync_release_manifests import sync, verify_commit  # noqa: E402

_ENTRY = [{"path": "package-lock.json", "format": "package_lock_json"}]


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    proc = git(root, *args)
    assert proc.returncode == 0, f"git {args} failed: {proc.stderr}"
    return proc


@pytest.fixture
def repo(tmp_path):
    _run(tmp_path, "init", "-q")
    _run(tmp_path, "config", "user.email", "test@example.com")
    _run(tmp_path, "config", "user.name", "Test")
    _run(tmp_path, "config", "core.autocrlf", "false")
    (tmp_path / ".gitkeep").write_text("", encoding="utf-8")
    _run(tmp_path, "add", ".gitkeep")
    _run(tmp_path, "commit", "-q", "-m", "init")
    (tmp_path / "shipwright_changelog_config.json").write_text(
        json.dumps({"published_manifests": _ENTRY}), encoding="utf-8"
    )
    return tmp_path


def _lock_text(top: str, root: str) -> str:
    body = {
        "name": "a", "version": top, "lockfileVersion": 3,
        "packages": {"": {"name": "a", "version": root}, "node_modules/x": {"version": "5.0.0"}},
    }
    return json.dumps(body, indent=2) + "\n"


def _commit_all(root: Path, message: str) -> str:
    _run(root, "add", "-A")
    _run(root, "commit", "-q", "-m", message)
    return _run(root, "rev-parse", "HEAD").stdout.strip()


@pytest.mark.covers("FR-01.09/AC13")
def test_sync_then_verify_commit_roundtrip(repo, tmp_path):
    (repo / "package-lock.json").write_text(_lock_text("0.1.0", "0.1.0"), encoding="utf-8")
    _commit_all(repo, "declare")

    sync_result = sync(repo, "0.3.0", dry_run=False, stage=True)
    assert sync_result["status"] == "ok"
    assert sync_result["manifests"][0]["reformatted"] is False
    result_file = tmp_path / "result.json"
    result_file.write_text(json.dumps(sync_result), encoding="utf-8")
    sha = _commit_all(repo, "release 0.3.0")

    assert verify_commit(repo, sha, "0.3.0", result_file)["status"] == "ok"
    committed = json.loads(_run(repo, "show", f"{sha}:package-lock.json").stdout)
    assert committed["version"] == "0.3.0"
    assert committed["packages"][""]["version"] == "0.3.0"
    assert committed["packages"]["node_modules/x"]["version"] == "5.0.0"


@pytest.mark.covers("FR-01.09/AC13")
def test_verify_commit_fails_when_root_package_is_stale(repo, tmp_path):
    (repo / "package-lock.json").write_text(_lock_text("0.3.0", "0.1.0"), encoding="utf-8")
    sha = _commit_all(repo, "stale root package")
    result_file = tmp_path / "result.json"
    result_file.write_text(
        json.dumps({"status": "ok", "version": "0.3.0", "manifests": _ENTRY}), encoding="utf-8"
    )
    result = verify_commit(repo, sha, "0.3.0", result_file)
    assert result["status"] == "verify_mismatch"
    assert "packages" in result["detail"]


@pytest.mark.covers("FR-01.09/AC13")
def test_sync_is_idempotent_when_already_current(repo):
    (repo / "package-lock.json").write_text(_lock_text("0.3.0", "0.3.0"), encoding="utf-8")
    _commit_all(repo, "declare")
    result = sync(repo, "0.3.0", dry_run=False, stage=False)
    assert result["manifests"][0]["changed"] is False
