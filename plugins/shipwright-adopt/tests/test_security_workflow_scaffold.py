"""Tests for the security-workflow scaffolder used by /shipwright-adopt.

The scaffolder copies ``shared/templates/github-actions/security.yml.template``
into ``<project>/.github/workflows/security.yml`` for adopted brownfield
repos. Two non-negotiable invariants:

1. **Auto-write on absence** — adopt's whole point is to land Shipwright CI
   in the target repo. If the file is missing, the scaffolder writes it
   without prompting.
2. **Never overwrite** — pre-existing security.yml files (whether shipwright
   templates from a prior adopt run, hand-rolled CodeQL workflows, or
   anything else) are preserved untouched. Idempotency, not destruction.

The scaffolder also creates intermediate ``.github/workflows/`` directories
when missing (a freshly-cloned repo with no GitHub configuration yet) and
returns a structured result so the adopt handoff banner can surface what
happened.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.security_workflow_scaffolder import scaffold_security_workflow


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Empty target-repo skeleton — no .github/, no anything."""
    return tmp_path


def test_writes_when_absent(tmp_project: Path) -> None:
    result = scaffold_security_workflow(tmp_project)

    assert result["wrote"] is True
    assert result["reason"] == "scaffolded"
    workflow = tmp_project / ".github" / "workflows" / "security.yml"
    assert workflow.exists(), "scaffolder did not write the workflow file"
    assert result["path"] == str(workflow)


def test_creates_parent_dirs(tmp_project: Path) -> None:
    # No .github/ at all — scaffolder must create both intermediate dirs.
    assert not (tmp_project / ".github").exists()

    scaffold_security_workflow(tmp_project)

    assert (tmp_project / ".github" / "workflows").is_dir()


def test_content_matches_template(tmp_project: Path) -> None:
    scaffold_security_workflow(tmp_project)

    written = (tmp_project / ".github" / "workflows" / "security.yml").read_text(
        encoding="utf-8"
    )
    # Template lives in the shipwright monorepo; the scaffolder must copy
    # it byte-for-byte (modulo encoding) so the drift test's guarantees
    # carry forward to the adopted repo.
    repo_root = Path(__file__).resolve().parents[3]
    template = (
        repo_root
        / "shared"
        / "templates"
        / "github-actions"
        / "security.yml.template"
    ).read_text(encoding="utf-8")
    assert written == template


def test_idempotent_existing_file_preserved(tmp_project: Path) -> None:
    workflow_dir = tmp_project / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    workflow = workflow_dir / "security.yml"
    user_content = "# user-authored CodeQL workflow — do not touch\n"
    workflow.write_text(user_content, encoding="utf-8")

    result = scaffold_security_workflow(tmp_project)

    assert result["wrote"] is False
    assert result["reason"] == "already_exists"
    # Critical: the user's file is untouched.
    assert workflow.read_text(encoding="utf-8") == user_content


def test_idempotent_when_called_twice(tmp_project: Path) -> None:
    first = scaffold_security_workflow(tmp_project)
    second = scaffold_security_workflow(tmp_project)

    assert first["wrote"] is True
    assert second["wrote"] is False
    assert second["reason"] == "already_exists"
    # Second call must not have rewritten the file (mtime would change).
    workflow = tmp_project / ".github" / "workflows" / "security.yml"
    assert workflow.exists()
