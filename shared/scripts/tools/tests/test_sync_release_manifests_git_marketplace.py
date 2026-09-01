"""Git-integration coverage for the ``marketplace_json`` format — split out
of test_sync_release_manifests_git.py, which keeps the format-agnostic
verify-commit gate coverage and the original package_json cases, so
neither file grows past the project's 300-line guideline.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # shared/

from scripts.lib.manifest_sync_core import git  # noqa: E402
from scripts.tools.sync_release_manifests import sync, verify_commit  # noqa: E402


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    proc = git(root, *args)
    assert proc.returncode == 0, f"git {args} failed: {proc.stderr}"
    return proc


@pytest.fixture
def repo(tmp_path):
    _run(tmp_path, "init", "-q")
    _run(tmp_path, "config", "user.email", "test@example.com")
    _run(tmp_path, "config", "user.name", "Test")
    (tmp_path / ".gitkeep").write_text("", encoding="utf-8")
    _run(tmp_path, "add", ".gitkeep")
    _run(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def _write_config(root: Path, entries: list[dict]) -> None:
    (root / "shipwright_changelog_config.json").write_text(
        json.dumps({"published_manifests": entries}), encoding="utf-8"
    )


def _write_marketplace_manifest(path: Path, version: str = "0.1.0") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"name": "acme", "version": version, "plugins": [{"name": "a", "version": version}]}
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")


def _commit_all(root: Path, message: str) -> str:
    _run(root, "add", "-A")
    _run(root, "commit", "-q", "-m", message)
    return _run(root, "rev-parse", "HEAD").stdout.strip()


def test_verify_commit_passes_marketplace_json_when_write_landed_in_commit(repo, tmp_path):
    """Same gate as test_verify_commit_passes_when_write_landed_in_commit
    (package_json), for the marketplace_json format: the COMMITTED blob's
    root + every plugins[].version entry must all read back as the
    released version."""
    _write_config(repo, [{"path": "marketplace.json", "format": "marketplace_json"}])
    _write_marketplace_manifest(repo / "marketplace.json", version="0.1.0")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-q", "-m", "declare")

    result_file = tmp_path / "result.json"
    sync_result = sync(repo, "0.3.0", dry_run=False, stage=True)
    result_file.write_text(json.dumps(sync_result), encoding="utf-8")
    sha = _commit_all(repo, "release 0.3.0")

    verify = verify_commit(repo, sha, "0.3.0", result_file)
    assert verify["status"] == "ok"
    committed = json.loads(_run(repo, "show", f"{sha}:marketplace.json").stdout)
    assert committed["version"] == "0.3.0"
    assert committed["plugins"][0]["version"] == "0.3.0"


def test_verify_commit_fails_when_root_matches_but_a_plugin_entry_is_stale(repo, tmp_path):
    """Regression: the committed blob's root can equal the released version
    while a nested plugins[] entry is stranded at an older one (a hand-edit
    landed straight in the commit, bypassing sync() entirely). verify_commit
    must catch this — comparing only the root would pass a release gate over
    exactly the drift this format exists to close."""
    _write_config(repo, [{"path": "marketplace.json", "format": "marketplace_json"}])
    body = {
        "name": "acme", "version": "0.3.0",
        "plugins": [{"name": "a", "version": "0.3.0"}, {"name": "b", "version": "0.2.0"}],
    }
    (repo / "marketplace.json").write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")

    result_file = tmp_path / "result.json"
    result_file.write_text(
        json.dumps({
            "status": "ok", "version": "0.3.0", "dry_run": False,
            "manifests": [{"path": "marketplace.json", "format": "marketplace_json"}],
        }),
        encoding="utf-8",
    )
    sha = _commit_all(repo, "hand-edited release 0.3.0")

    verify = verify_commit(repo, sha, "0.3.0", result_file)
    assert verify["status"] == "verify_mismatch"
    assert "b" in verify["detail"]
