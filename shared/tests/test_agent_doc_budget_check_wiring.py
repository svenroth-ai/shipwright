"""Drift guard: the agent-doc entry-budget gate is wired into run_all_checks.

Kept in its own file (not test_verify_iterate_finalization.py, which is over its
bloat baseline). Asserts a future refactor can't silently drop the repo-agnostic
enforcement, and that the check fail-soft SKIPs on a non-git tmp dir.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.agent_doc_budget import CLAUDE_MD_MAX_NEW_LINES  # noqa: E402
from tools.verifiers.agent_doc_budget_check import check_agent_doc_budget  # noqa: E402
from tools.verifiers.iterate_checks import run_all_checks  # noqa: E402
from test_hygiene import skip_or_fail_on_missing_binary  # noqa: E402

_GIT_HINT = "git not on PATH — CI provisions it via actions/checkout"


def test_agent_doc_budget_in_run_all_checks(tmp_path: Path):
    results = run_all_checks(tmp_path, "r1", commit_hash="abc1234")
    names = [r.name.lower() for r in results]
    assert any("entry budget" in n for n in names), (
        f"agent-doc entry-budget check missing from run_all_checks; got: {names}"
    )


def test_check_fail_soft_skips_without_git_base(tmp_path: Path):
    # A non-git tmp dir → no base resolvable → skip (ok, non-blocking).
    r = check_agent_doc_budget(tmp_path, "r1")
    assert r.ok is True and r.is_skipped


# --- CLAUDE.md net-growth gate through the verifier --------------------------


def _growth_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (
        ("init", "-q"),
        ("config", "user.email", "t@t"),
        ("config", "user.name", "t"),
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    (repo / "CLAUDE.md").write_text("line\n" * 10, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "base"],
        check=True, capture_output=True,
    )
    (repo / "CLAUDE.md").write_text(
        "line\n" * (10 + CLAUDE_MD_MAX_NEW_LINES + 5), encoding="utf-8"
    )
    return repo


def test_verifier_blocks_claude_md_over_growth(tmp_path: Path, monkeypatch):
    skip_or_fail_on_missing_binary("git", _GIT_HINT)
    monkeypatch.delenv("SHIPWRIGHT_CLAUDE_MD_GROWTH_OK", raising=False)
    r = check_agent_doc_budget(_growth_repo(tmp_path), "r1")
    assert r.ok is False and "CLAUDE.md" in r.detail


def test_verifier_env_override_skips_growth_but_stays_green(tmp_path: Path, monkeypatch):
    skip_or_fail_on_missing_binary("git", _GIT_HINT)
    # The override is a SUCCESS with a visible note — never a violation.
    monkeypatch.setenv("SHIPWRIGHT_CLAUDE_MD_GROWTH_OK", "1")
    r = check_agent_doc_budget(_growth_repo(tmp_path), "r1")
    assert r.ok is True and "SHIPWRIGHT_CLAUDE_MD_GROWTH_OK" in r.detail