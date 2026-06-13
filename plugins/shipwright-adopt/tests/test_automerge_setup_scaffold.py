"""Tests for the AUTOMERGE_SETUP.md scaffolder used by /shipwright-adopt.

End-to-end: scaffold the four workflows (ci / security / codeql / claude-review)
with the real adopt scaffolders, THEN render the doc — so the test exercises the
same ordering the orchestrator uses and proves the doc lists the check names the
deployed workflows actually declare.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.automerge_setup_scaffolder import scaffold_automerge_setup
from lib.ci_workflow_scaffolder import scaffold_ci_workflow
from lib.claude_review_workflow_scaffolder import scaffold_claude_review_workflow
from lib.codeql_workflow_scaffolder import scaffold_codeql_workflow
from lib.security_workflow_scaffolder import scaffold_security_workflow

PROFILES = ["python-plugin-monorepo", "supabase-nextjs", "vite-hono"]
CODEQL_LANG = {
    "python-plugin-monorepo": "python",
    "supabase-nextjs": "javascript-typescript",
    "vite-hono": "javascript-typescript",
}


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    return tmp_path


def _scaffold_workflows(project: Path, profile: str) -> None:
    scaffold_ci_workflow(project, profile_name=profile)
    scaffold_security_workflow(project)
    scaffold_codeql_workflow(project, profile_name=profile)
    scaffold_claude_review_workflow(project)


def _doc(project: Path) -> Path:
    return project / "AUTOMERGE_SETUP.md"


# ---------------------------------------------------------------------------
# Happy path — per profile
# ---------------------------------------------------------------------------


class TestAutomergeSetupScaffolder:
    @pytest.mark.parametrize("profile", PROFILES)
    def test_writes_doc_after_workflows(self, tmp_project: Path, profile: str) -> None:
        _scaffold_workflows(tmp_project, profile)
        result = scaffold_automerge_setup(tmp_project, profile_name=profile)

        assert result["wrote"] is True
        assert result["reason"] == "scaffolded"
        assert _doc(tmp_project).exists()
        assert result["path"] == str(_doc(tmp_project))
        assert result["required_checks"], "expected a non-empty required-check list"

    @pytest.mark.parametrize("profile", PROFILES)
    def test_doc_lists_real_check_names(self, tmp_project: Path, profile: str) -> None:
        _scaffold_workflows(tmp_project, profile)
        result = scaffold_automerge_setup(tmp_project, profile_name=profile)
        content = _doc(tmp_project).read_text(encoding="utf-8")

        # Every derived check name is in the doc...
        for name in result["required_checks"]:
            assert name in content
        # ...including the concrete per-profile codeql + security + advisory.
        assert f"Analyze ({CODEQL_LANG[profile]})" in content
        assert "Shipwright Security Scan" in content
        assert "claude-review" in content
        # Profile label rendered.
        assert profile in content

    @pytest.mark.parametrize("profile", PROFILES)
    def test_doc_flags_dormant_vs_active(self, tmp_project: Path, profile: str) -> None:
        _scaffold_workflows(tmp_project, profile)
        scaffold_automerge_setup(tmp_project, profile_name=profile)
        content = _doc(tmp_project).read_text(encoding="utf-8")
        # ci/security/codeql ship dormant; claude-review is active.
        assert "| dormant |" in content
        assert "| active |" in content


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestAutomergeSetupIdempotency:
    def test_existing_doc_preserved(self, tmp_project: Path) -> None:
        _scaffold_workflows(tmp_project, "vite-hono")
        user_content = "# my own automerge notes — keep\n"
        _doc(tmp_project).write_text(user_content, encoding="utf-8")

        result = scaffold_automerge_setup(tmp_project, profile_name="vite-hono")

        assert result["wrote"] is False
        assert result["reason"] == "already_exists"
        assert _doc(tmp_project).read_text(encoding="utf-8") == user_content

    def test_second_call_is_noop(self, tmp_project: Path) -> None:
        _scaffold_workflows(tmp_project, "vite-hono")
        first = scaffold_automerge_setup(tmp_project, profile_name="vite-hono")
        second = scaffold_automerge_setup(tmp_project, profile_name="vite-hono")
        assert first["wrote"] is True
        assert second["wrote"] is False
        assert second["reason"] == "already_exists"


# ---------------------------------------------------------------------------
# Degenerate repo — no workflows present
# ---------------------------------------------------------------------------


def test_writes_even_with_no_workflows(tmp_project: Path) -> None:
    result = scaffold_automerge_setup(
        tmp_project, profile_name="python-plugin-monorepo"
    )
    assert result["wrote"] is True
    assert result["required_checks"] == []
    assert "no Shipwright workflows found" in _doc(tmp_project).read_text(
        encoding="utf-8"
    )


def test_profile_none_still_renders(tmp_project: Path) -> None:
    _scaffold_workflows(tmp_project, "python-plugin-monorepo")
    result = scaffold_automerge_setup(tmp_project, profile_name=None)
    assert result["wrote"] is True
    content = _doc(tmp_project).read_text(encoding="utf-8")
    assert "Analyze (python)" in content  # checks still derived from workflows
