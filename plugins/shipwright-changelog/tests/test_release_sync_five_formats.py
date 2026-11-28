"""L1: ``release.py sync`` on a scratch git project moves all five manifest formats to one version (FINDINGS D111, FR-01.09).

The manifest step runs the real ``sync_release_manifests.py`` (by the interpreter, not ``uv run``: the scratch project's own
``pyproject.toml`` must not become uv's project); the fold and the evidence step are answered, they are not under test.
The root ``pyproject.toml`` and ``uv.lock`` are copies of this repository's real files, one written with CRLF, one with LF.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from lib import release_sync
from lib.release_runner import CmdResult, Recorder, subprocess_runner

REPO_ROOT = Path(__file__).resolve().parents[3]
VERSION = "0.99.0"
FORMATS = {"package.json": "package_json", ".claude-plugin/marketplace.json": "marketplace_json",
           "package-lock.json": "package_lock_json", "pyproject.toml": "pyproject_toml", "uv.lock": "uv_lock"}
TOML_EOL = {"pyproject.toml": b"\r\n", "uv.lock": b"\n"}


def _real(name: str) -> bytes:
    """The repository's real file with the given line ending, whatever the checkout's autocrlf did to it."""
    return (REPO_ROOT / name).read_bytes().replace(b"\r\n", b"\n").replace(b"\n", TOML_EOL[name])


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", check=True)
    return done.stdout


def _runner(key, argv, cwd, **opts) -> CmdResult:
    if key == "sync":
        assert argv[:2] == ["uv", "run"]
        return subprocess_runner(key, [sys.executable, *argv[2:]], cwd, **opts)
    answers = {"fold-events": {"status": "folded"}, "evidence": {"status": "ok", "evidence_pathspec": []}}
    return CmdResult(key, tuple(argv), 0, json.dumps(answers[key]))


def _verify(root: Path, plugin_root: Path) -> dict:
    tool = release_sync.release_paths.shared_root(plugin_root) / "scripts/tools/sync_release_manifests.py"
    done = subprocess.run([sys.executable, str(tool), "--project-root", ".", "--version", VERSION, "--verify-commit",
                           _git(root, "rev-parse", "HEAD").strip(), "--result-file", release_sync.MANIFEST_RESULT],
                          cwd=root, capture_output=True, text=True, encoding="utf-8")
    return json.loads(done.stdout)


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    root = tmp_path / "scratch"
    (root / ".claude-plugin").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    for key, value in (("user.email", "t@example.com"), ("user.name", "T"), ("core.autocrlf", "false")):
        _git(root, "config", key, value)
    (root / "package.json").write_text(json.dumps({"name": "acme", "version": "0.1.0"}, indent=2) + "\n", encoding="utf-8")
    (root / ".claude-plugin/marketplace.json").write_text(json.dumps(
        {"name": "acme", "version": "0.1.0", "plugins": [{"name": "p", "version": "0.1.0"}]}, indent=2) + "\n", encoding="utf-8")
    (root / "package-lock.json").write_text(json.dumps(
        {"name": "acme", "version": "0.1.0", "lockfileVersion": 3,
         "packages": {"": {"name": "acme", "version": "0.1.0"}, "node_modules/x": {"version": "0.1.0"}}}, indent=2) + "\n",
        encoding="utf-8")
    for name in TOML_EOL:
        (root / name).write_bytes(_real(name))
    (root / "shipwright_changelog_config.json").write_text(json.dumps(
        {"published_manifests": [{"path": p, "format": f} for p, f in FORMATS.items()]}), encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "chore: scratch project")
    return root


def _versions(root: Path) -> dict[str, object]:
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    market = json.loads((root / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    npm_lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))
    return {
        "package.json": json.loads((root / "package.json").read_text(encoding="utf-8"))["version"],
        "marketplace": {market["version"], *(p["version"] for p in market["plugins"])},
        "package-lock": {npm_lock["version"], npm_lock["packages"][""]["version"]},
        "pyproject": tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"],
        "uv.lock": {p["version"] for p in lock["package"] if p.get("source") == {"virtual": "."}},
    }


@pytest.mark.covers("FR-01.09/AC12")
def test_release_sync_moves_all_five_formats_to_one_version_and_the_commit_verifies(scratch, plugin_root):
    code, out = release_sync.sync(Recorder(_runner, scratch), plugin_root, version=VERSION)

    assert code == 0 and out["status"] == "ok", out
    assert sorted(out["manifests"]["pathspec"]) == sorted(FORMATS)
    assert _versions(scratch) == {"package.json": VERSION, "marketplace": {VERSION}, "package-lock": {VERSION},
                                  "pyproject": VERSION, "uv.lock": {VERSION}}
    for name in TOML_EOL:  # one version line each; every other byte, line endings included, as it was
        before, after = _real(name).split(b"\n"), (scratch / name).read_bytes().split(b"\n")
        assert len(before) == len(after) and sum(a != b for a, b in zip(before, after)) == 1
    assert json.loads((scratch / "package-lock.json").read_text(encoding="utf-8"))["packages"]["node_modules/x"]["version"] == "0.1.0"

    _git(scratch, "commit", "-q", "-m", f"chore(release): v{VERSION}")
    assert _verify(scratch, plugin_root)["status"] == "ok"


@pytest.mark.covers("FR-01.09/AC12")
@pytest.mark.parametrize("stale", list(TOML_EOL))
def test_verify_commit_names_a_toml_manifest_whose_committed_version_is_stale(scratch, plugin_root, stale):
    code, _ = release_sync.sync(Recorder(_runner, scratch), plugin_root, version=VERSION)
    assert code == 0
    _git(scratch, "reset", "-q", "--", stale)  # the write never reaches the release commit
    _git(scratch, "commit", "-q", "-m", f"chore(release): v{VERSION}")
    result = _verify(scratch, plugin_root)
    assert result["status"] == "verify_mismatch" and result.get("path") == stale, result
