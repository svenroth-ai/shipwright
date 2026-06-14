"""Drift guard: the agent-doc entry-budget gate is wired into run_all_checks.

Kept in its own file (not test_verify_iterate_finalization.py, which is over its
bloat baseline). Asserts a future refactor can't silently drop the repo-agnostic
enforcement, and that the check fail-soft SKIPs on a non-git tmp dir.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from tools.verifiers.agent_doc_budget_check import check_agent_doc_budget  # noqa: E402
from tools.verifiers.iterate_checks import run_all_checks  # noqa: E402


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