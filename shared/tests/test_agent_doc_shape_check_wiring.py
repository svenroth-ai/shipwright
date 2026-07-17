"""Drift guard + end-to-end proof: the agent-doc SHAPE gate is wired into
run_all_checks and blocks a new non-canonical bullet forward-only.

Kept in its own file (test_verify_iterate_finalization.py is over its bloat
baseline). Asserts a future refactor can't silently drop the gate, that it
fail-soft SKIPs on a non-git tmp dir, and that it composes into the F11
orchestrator against a real git base.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from tools.verifiers.agent_doc_shape_check import check_agent_doc_shape  # noqa: E402
from tools.verifiers.iterate_checks import run_all_checks  # noqa: E402

_HEADER = "## Architecture Updates"
_CANON = (
    "- **iterate-2026-07-17-new-thing** (2026-07-17): "
    "Component — added a new thing. → decision_log (Run-ID)"
)
_NONCANON = "- **Campaign New Thing** (2026-07-17): added a thing. → decision_log (Run-ID)"


def test_agent_doc_shape_in_run_all_checks(tmp_path: Path):
    names = [r.name.lower() for r in run_all_checks(tmp_path, "r1", commit_hash="abc1234")]
    assert any("shape" in n for n in names), (
        f"agent-doc shape check missing from run_all_checks; got: {names}"
    )


def test_check_fail_soft_skips_without_git_base(tmp_path: Path):
    r = check_agent_doc_shape(tmp_path, "r1")
    assert r.ok is True and r.is_skipped


def _repo(tmp_path: Path, base_body: str, head_body: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (("init", "-q"), ("config", "user.email", "t@t"), ("config", "user.name", "t")):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    ad = repo / ".shipwright" / "agent_docs"
    ad.mkdir(parents=True)
    (ad / "architecture.md").write_text(f"# A\n\n{_HEADER}\n{base_body}", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "base"], check=True, capture_output=True
    )
    (ad / "architecture.md").write_text(f"# A\n\n{_HEADER}\n{head_body}", encoding="utf-8")
    return repo


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_verifier_blocks_new_noncanonical(tmp_path: Path):
    repo = _repo(tmp_path, base_body="", head_body=f"{_NONCANON}\n")
    r = check_agent_doc_shape(repo, "r1")
    assert r.ok is False and "non-canonical" in r.detail


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_verifier_passes_new_canonical(tmp_path: Path):
    repo = _repo(tmp_path, base_body="", head_body=f"{_CANON}\n")
    r = check_agent_doc_shape(repo, "r1")
    assert r.ok is True


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_verifier_ignores_legacy_untouched_noncanonical(tmp_path: Path):
    # A legacy non-canonical entry present at BOTH base and head is forward-only
    # exempt — only the newly-added canonical entry differs.
    repo = _repo(tmp_path, base_body=f"{_NONCANON}\n", head_body=f"{_NONCANON}\n{_CANON}\n")
    r = check_agent_doc_shape(repo, "r1")
    assert r.ok is True
