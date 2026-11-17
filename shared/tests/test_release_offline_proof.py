"""A scratch project passes ``--verify-commit --release-audit`` with no network (an offline-consistency check).

Proof, not a seam: the release audit's only external dependency is ``uv run --with
pyyaml``, and uv serves that from its own cache under ``UV_OFFLINE``. The scratch
project is the minimal valid project with a stamped evidence commit; the process
environment carries no API key, an unreachable proxy and ``UV_OFFLINE=1``, so a
network attempt by uv or by a proxy-aware client fails the run instead of passing quietly
(a client that ignores proxy variables is not caught; this is not network isolation).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "shared" / "testkit"))
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts"))

import minimal_valid_project as mvp  # noqa: E402
from test_hygiene import is_ci  # noqa: E402

_REFRESH = _REPO_ROOT / "shared" / "scripts" / "tools" / "refresh_compliance_docs.py"
_KEYS = ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GH_TOKEN", "GITHUB_TOKEN",
         "SHIPWRIGHT_ROOT")


def _offline_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("GIT_", "SHIPWRIGHT_TEST_")) and k not in _KEYS
           and k.upper() != "NO_PROXY"}
    dead = "http://127.0.0.1:9"
    env.update(UV_OFFLINE="1", HTTP_PROXY=dead, HTTPS_PROXY=dead, http_proxy=dead, https_proxy=dead)
    return env


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
         "-c", "commit.gpgsign=false", *args],
        cwd=root, env=_offline_env(), check=True, capture_output=True, text=True, timeout=60,
    ).stdout.strip()


def _refresh(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_REFRESH), "--project-root", str(root), *args],
                          env=_offline_env(), capture_output=True, text=True, timeout=300,
                          cwd=root)  # the skill's call site: cwd is the target project


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    probe_cmd = ["uv", "run", "--with", "pyyaml", "python", "-c", "import yaml"]
    try:
        probe = subprocess.run(probe_cmd, env=_offline_env(), capture_output=True, text=True,
                               timeout=120, cwd=tmp_path)
    except FileNotFoundError:  # no uv on PATH: same branch as an unprovisionable cache
        probe = subprocess.CompletedProcess(probe_cmd, 127, "", "uv is not on PATH")
    if probe.returncode != 0 and probe.returncode != 127:
        # Provision BEFORE the offline phase: one online resolve fills uv's cache, and the
        # offline phase below then proves nothing else is fetched.
        online = {k: v for k, v in os.environ.items() if k != "UV_OFFLINE"}
        subprocess.run(probe_cmd, env=online, capture_output=True, text=True, timeout=300, cwd=tmp_path)
        probe = subprocess.run(probe_cmd, env=_offline_env(), capture_output=True, text=True,
                               timeout=120, cwd=tmp_path)
    if probe.returncode != 0:
        msg = f"pyyaml could not be provisioned into uv's cache: {probe.stderr.strip()[-200:]}"
        if is_ci():
            pytest.fail(msg, pytrace=False)  # the offline proof must run in CI, never skip
        pytest.skip(msg)
    root = tmp_path / "scratch"
    root.mkdir()
    for phase, split in (("project", None), ("design", None), ("plan", "01-core"),
                         ("build", "01-core"), ("test", "01-core"), ("changelog", None)):
        mvp.write_phase(root, phase, split)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "chore: phases")
    return root


@pytest.mark.covers("FR-01.09/AC14")
def test_scratch_project_passes_verify_commit_and_release_audit_offline(scratch: Path):
    staged = _refresh(scratch, "--stage", "--release", "v0.1.0")
    assert staged.returncode == 0, staged.stdout + staged.stderr
    pathspec = json.loads(staged.stdout)["evidence_pathspec"]
    _git(scratch, "commit", "-q", "-m", "chore(release): v0.1.0", "--", *pathspec)
    # The event writer leaves its lock file untracked; the release audit refuses a dirty tree.
    (scratch / "shipwright_events.jsonl.lock").unlink(missing_ok=True)
    # The staging step recorded an event: in the monolithic layout it appended to
    # shipwright_events.jsonl, in the drops layout it wrote a new file under
    # .shipwright/events/drops/. Either is part of the release commit in the skill.
    _git(scratch, "add", "-A")
    if _git(scratch, "status", "--porcelain", "--untracked-files=no"):
        _git(scratch, "commit", "-q", "-m", "chore(release): record event")
    head = _git(scratch, "rev-parse", "HEAD")

    verified = _refresh(scratch, "--verify-commit", head, "--release-audit")

    assert verified.returncode == 0, verified.stdout + verified.stderr
    report = json.loads(verified.stdout)
    assert report["status"] == "verified"
    assert report["release_compliance_audit"]["ran"] is True
