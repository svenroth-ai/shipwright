"""Tests for the CI workflow scaffolder used by /shipwright-adopt.

The scaffolder mirrors the established `security_workflow_scaffolder.py`
contract (Auto-write on absence + Never overwrite + Structured ScaffoldResult).
The CI scaffolder additionally accepts a profile_name argument: profile is
loaded by `generate_adoption_artifacts.py` from snapshot.json and passed
explicitly (external-review #O1 — single source of truth at the caller).

Three reason codes distinguish failure modes (external-review #O12):
- ``scaffolded`` — wrote=True; template copied to target.
- ``already_exists`` — wrote=False; pre-existing target file preserved.
- ``no_template_for_profile`` — wrote=False; profile recognized but no
  template registered for it (e.g. early-stage profile, future profile
  added without template yet).
- ``profile_unresolved`` — wrote=False; profile_name is None / empty /
  malformed (distinct from "registered profile without template" to
  surface genuine snapshot-parsing failures upstream).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.ci_workflow_scaffolder import scaffold_ci_workflow


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Empty target-repo skeleton — no .github/, no anything."""
    return tmp_path


# ---------------------------------------------------------------------------
# CI scaffolder — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.13/AC01")
class TestCIScaffolderWritesWhenAbsent:
    @pytest.mark.parametrize(
        "profile_name",
        ["supabase-nextjs", "vite-hono", "python-plugin-monorepo"],
    )
    def test_writes_when_absent(self, tmp_project: Path, profile_name: str) -> None:
        result = scaffold_ci_workflow(tmp_project, profile_name=profile_name)

        assert result["wrote"] is True
        assert result["reason"] == "scaffolded"
        workflow = tmp_project / ".github" / "workflows" / "ci.yml"
        assert workflow.exists(), f"profile {profile_name}: scaffolder didn't write the file"
        assert result["path"] == str(workflow)

    def test_creates_parent_dirs(self, tmp_project: Path) -> None:
        # External-review #G4 + #O3 — explicit "no .github/" case.
        assert not (tmp_project / ".github").exists()

        scaffold_ci_workflow(tmp_project, profile_name="vite-hono")

        assert (tmp_project / ".github" / "workflows").is_dir()

    @pytest.mark.parametrize(
        "profile_name",
        ["supabase-nextjs", "vite-hono", "python-plugin-monorepo"],
    )
    def test_content_matches_template(
        self, tmp_project: Path, profile_name: str
    ) -> None:
        scaffold_ci_workflow(tmp_project, profile_name=profile_name)

        written = (
            tmp_project / ".github" / "workflows" / "ci.yml"
        ).read_text(encoding="utf-8")

        # Read the matching template from the monorepo. The scaffolder
        # must copy byte-for-byte so the drift test's guarantees carry
        # forward to the adopted repo.
        repo_root = Path(__file__).resolve().parents[3]
        template_map = {
            "supabase-nextjs": "ci-supabase-nextjs.yml.template",
            "vite-hono": "ci-vite-hono.yml.template",
            "python-plugin-monorepo": "ci-python-plugin-monorepo.yml.template",
        }
        template = (
            repo_root / "shared" / "templates" / "github-actions"
            / template_map[profile_name]
        ).read_text(encoding="utf-8")
        assert written == template


# ---------------------------------------------------------------------------
# CI scaffolder — idempotency
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.13/AC01")
class TestCIScaffolderIdempotency:
    def test_existing_file_preserved(self, tmp_project: Path) -> None:
        workflow_dir = tmp_project / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        workflow = workflow_dir / "ci.yml"
        user_content = "# user-authored CI workflow — do not touch\n"
        workflow.write_text(user_content, encoding="utf-8")

        result = scaffold_ci_workflow(tmp_project, profile_name="vite-hono")

        assert result["wrote"] is False
        assert result["reason"] == "already_exists"
        # Critical: the user's file is untouched.
        assert workflow.read_text(encoding="utf-8") == user_content

    def test_second_call_is_noop(self, tmp_project: Path) -> None:
        first = scaffold_ci_workflow(tmp_project, profile_name="vite-hono")
        second = scaffold_ci_workflow(tmp_project, profile_name="vite-hono")

        assert first["wrote"] is True
        assert second["wrote"] is False
        assert second["reason"] == "already_exists"


# ---------------------------------------------------------------------------
# CI scaffolder — profile resolution edge cases
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.13/AC01")
class TestCIScaffolderProfileResolution:
    """External-review #O12: distinguish profile-unresolved from no-template."""

    def test_unknown_profile_returns_no_template(self, tmp_project: Path) -> None:
        # An ostensibly-valid profile name that has no template registered
        # in TEMPLATE_BY_PROFILE — graceful no-op, distinct reason code.
        result = scaffold_ci_workflow(
            tmp_project, profile_name="some-future-profile"
        )

        assert result["wrote"] is False
        assert result["reason"] == "no_template_for_profile"
        # No file written.
        assert not (tmp_project / ".github" / "workflows" / "ci.yml").exists()

    @pytest.mark.parametrize("bad_profile", [None, "", "   "])
    def test_missing_profile_returns_unresolved(
        self, tmp_project: Path, bad_profile: str | None
    ) -> None:
        # Distinct reason — surfaces snapshot-parsing failure upstream
        # rather than masking it as "no template".
        result = scaffold_ci_workflow(
            tmp_project, profile_name=bad_profile  # type: ignore[arg-type]
        )

        assert result["wrote"] is False
        assert result["reason"] == "profile_unresolved"
        assert not (tmp_project / ".github" / "workflows" / "ci.yml").exists()


# ---------------------------------------------------------------------------
# Claude-Review scaffolder — retired (decision 2026-10-10)
# ---------------------------------------------------------------------------


@pytest.mark.covers("FR-01.13/AC01")
def test_claude_review_scaffolder_is_retired() -> None:
    """Adopt writes no PR-review workflow: it needs an ANTHROPIC_API_KEY most
    adopted repos lack (red/pending check on every PR), and the independent
    review already runs inside each iterate."""
    scripts_lib = Path(__file__).resolve().parents[1] / "scripts" / "lib"
    assert not (scripts_lib / "claude_review_workflow_scaffolder.py").exists()
    templates = Path(__file__).resolve().parents[3] / "shared" / "templates" / "github-actions"
    assert not list(templates.glob("claude-review*.yml.template"))
    constants = (templates.parents[1] / "scripts" / "lib" / "ci_workflow.py").read_text(encoding="utf-8")
    assert "CLAUDE_REVIEW_" not in constants
