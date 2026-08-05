"""S4/S9/S10 (`spec_checks.py`) — the shared ``_skip_unless_work_tree`` git-context
guard, migrated off ``git_helpers._git_available`` in trg-4183acd3.

Unlike the F11 ERROR gates this migration also touches, these three are Tier-2
WARN-only (module docstring; ``test_spec_checks.py`` pins S10 never returns
``STATUS_FAIL``), so there is no ERROR state to escalate a git fault into — BOTH
``not_git`` and a real git subprocess fault SKIP here. This file exists
separately from ``test_spec_checks.py`` (bloat-baselined at its exact current
size) rather than growing it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.phase_quality import STATUS_SKIP  # noqa: E402
from tools.verifiers import spec_checks as sc  # noqa: E402


def test_not_a_git_repo_skips(tmp_path):
    guard = sc._skip_unless_work_tree(tmp_path, "S4", sc.S4_NAME)
    assert guard is not None
    assert guard["status"] == STATUS_SKIP
    assert "partial checkout" in guard["evidence"]


def test_a_git_fault_inside_a_repo_still_skips_not_errors(tmp_path, monkeypatch):
    """The Tier-2 ceiling: a real infra fault degrades to SKIP too — there is no
    ERROR path available at this tier — but the message must not claim the
    directory is not a repository."""
    monkeypatch.setattr(sc, "git_context", lambda root: "git_error")
    guard = sc._skip_unless_work_tree(tmp_path, "S9", sc.S9_NAME)
    assert guard is not None
    assert guard["status"] == STATUS_SKIP
    detail = guard["evidence"].lower()
    assert "not a git" not in detail
    assert "wedged" in detail or "safe.directory" in detail


def test_an_unrecognised_git_context_still_skips(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "git_context", lambda root: "something_new")
    guard = sc._skip_unless_work_tree(tmp_path, "S10", sc.S10_NAME)
    assert guard is not None
    assert guard["status"] == STATUS_SKIP


def test_a_real_work_tree_proceeds(git_origin_repo):
    root, _o = git_origin_repo
    assert sc._skip_unless_work_tree(root, "S4", sc.S4_NAME) is None


# --- each public check really routes through the shared guard -------------------


def test_s4_skips_on_git_fault_via_the_shared_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "git_context", lambda root: "git_error")
    finding = sc.check_s4_fr_preservation(tmp_path)
    assert finding["status"] == STATUS_SKIP
    assert finding["id"] == "S4"


def test_s9_skips_on_git_fault_via_the_shared_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "git_context", lambda root: "git_error")
    finding = sc.check_s9_readme_freshness(tmp_path, "some-run")
    assert finding["status"] == STATUS_SKIP
    assert finding["id"] == "S9"


def test_s10_skips_on_git_fault_via_the_shared_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "git_context", lambda root: "git_error")
    finding = sc.check_s10_claude_md_sync(tmp_path, "some-run")
    assert finding["status"] == STATUS_SKIP
    assert finding["id"] == "S10"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
