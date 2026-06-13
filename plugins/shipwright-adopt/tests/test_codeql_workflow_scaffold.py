"""Tests for the CodeQL workflow scaffolder used by /shipwright-adopt.

Unlike the pure-copy CI / Claude-Review scaffolders, this one RENDERS the
`${SHIPWRIGHT_CODEQL_LANGUAGES}` placeholder for the detected profile's
language list before writing. It mirrors the same structured-result contract:

- ``scaffolded`` — wrote=True; rendered template written.
- ``already_exists`` — wrote=False; pre-existing target preserved.
- ``no_codeql_for_profile`` — wrote=False; profile recognized but no CodeQL
  language mapping registered.
- ``profile_unresolved`` — wrote=False; profile_name None / empty / malformed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

from lib.codeql_workflow_scaffolder import (  # noqa: E402
    LANGUAGES_PLACEHOLDER,
    scaffold_codeql_workflow,
)

# Profile → expected rendered CodeQL languages (kept independent of the SSoT
# module so a silent change to CODEQL_LANGUAGES_BY_PROFILE is caught here).
EXPECTED_LANGUAGES = {
    "python-plugin-monorepo": ["python"],
    "supabase-nextjs": ["javascript-typescript"],
    "vite-hono": ["javascript-typescript"],
}


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    return tmp_path


def _workflow(project: Path) -> Path:
    return project / ".github" / "workflows" / "codeql.yml"


# ---------------------------------------------------------------------------
# Happy paths — render per profile
# ---------------------------------------------------------------------------


class TestCodeqlScaffolderWritesWhenAbsent:
    @pytest.mark.parametrize("profile_name", list(EXPECTED_LANGUAGES))
    def test_writes_when_absent(self, tmp_project: Path, profile_name: str) -> None:
        result = scaffold_codeql_workflow(tmp_project, profile_name=profile_name)

        assert result["wrote"] is True
        assert result["reason"] == "scaffolded"
        assert _workflow(tmp_project).exists()
        assert result["path"] == str(_workflow(tmp_project))
        assert result["languages"] == EXPECTED_LANGUAGES[profile_name]

    def test_creates_parent_dirs(self, tmp_project: Path) -> None:
        assert not (tmp_project / ".github").exists()
        scaffold_codeql_workflow(tmp_project, profile_name="vite-hono")
        assert (tmp_project / ".github" / "workflows").is_dir()

    @pytest.mark.parametrize("profile_name", list(EXPECTED_LANGUAGES))
    def test_rendered_matrix_languages(
        self, tmp_project: Path, profile_name: str
    ) -> None:
        scaffold_codeql_workflow(tmp_project, profile_name=profile_name)
        written = _workflow(tmp_project).read_text(encoding="utf-8")

        # Placeholder must be fully substituted...
        assert LANGUAGES_PLACEHOLDER not in written
        # ...and the rendered YAML must parse with the expected language list.
        parsed = yaml.safe_load(written)
        matrix = parsed["jobs"]["analyze"]["strategy"]["matrix"]
        assert matrix["language"] == EXPECTED_LANGUAGES[profile_name]

    @pytest.mark.parametrize("profile_name", list(EXPECTED_LANGUAGES))
    def test_rendered_is_dormant(self, tmp_project: Path, profile_name: str) -> None:
        # The render must NOT accidentally activate auto-triggers.
        scaffold_codeql_workflow(tmp_project, profile_name=profile_name)
        parsed = yaml.safe_load(_workflow(tmp_project).read_text(encoding="utf-8"))
        triggers = parsed.get("on") or parsed.get(True) or {}
        assert "workflow_dispatch" in triggers
        assert "pull_request" not in triggers
        assert "push" not in triggers


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestCodeqlScaffolderIdempotency:
    def test_existing_file_preserved(self, tmp_project: Path) -> None:
        wf_dir = tmp_project / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        user_content = "# hand-rolled CodeQL config — do not touch\n"
        (wf_dir / "codeql.yml").write_text(user_content, encoding="utf-8")

        result = scaffold_codeql_workflow(
            tmp_project, profile_name="python-plugin-monorepo"
        )

        assert result["wrote"] is False
        assert result["reason"] == "already_exists"
        assert _workflow(tmp_project).read_text(encoding="utf-8") == user_content

    def test_second_call_is_noop(self, tmp_project: Path) -> None:
        first = scaffold_codeql_workflow(tmp_project, profile_name="vite-hono")
        second = scaffold_codeql_workflow(tmp_project, profile_name="vite-hono")
        assert first["wrote"] is True
        assert second["wrote"] is False
        assert second["reason"] == "already_exists"


# ---------------------------------------------------------------------------
# Profile resolution edge cases
# ---------------------------------------------------------------------------


class TestCodeqlScaffolderProfileResolution:
    def test_unknown_profile_returns_no_codeql(self, tmp_project: Path) -> None:
        result = scaffold_codeql_workflow(
            tmp_project, profile_name="some-future-profile"
        )
        assert result["wrote"] is False
        assert result["reason"] == "no_codeql_for_profile"
        assert result["languages"] == []
        assert not _workflow(tmp_project).exists()

    @pytest.mark.parametrize("bad_profile", [None, "", "   "])
    def test_missing_profile_returns_unresolved(
        self, tmp_project: Path, bad_profile: str | None
    ) -> None:
        result = scaffold_codeql_workflow(
            tmp_project, profile_name=bad_profile  # type: ignore[arg-type]
        )
        assert result["wrote"] is False
        assert result["reason"] == "profile_unresolved"
        assert not _workflow(tmp_project).exists()

    def test_unresolved_profile_takes_precedence_over_existing(
        self, tmp_project: Path
    ) -> None:
        # A missing profile must surface its own diagnostic even if a file is
        # already there (snapshot-parsing failure should not be masked).
        wf_dir = tmp_project / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "codeql.yml").write_text("# existing\n", encoding="utf-8")

        result = scaffold_codeql_workflow(tmp_project, profile_name=None)
        assert result["reason"] == "profile_unresolved"
