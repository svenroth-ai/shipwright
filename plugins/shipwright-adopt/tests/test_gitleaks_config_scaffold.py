"""Tests for the gitleaks-config scaffolder used by /shipwright-adopt.

The scaffolder copies ``shared/templates/github-actions/gitleaks.toml.template``
into ``<project>/.gitleaks.toml`` for adopted brownfield repos. The deployed
``security.yml`` runs ``gitleaks detect --no-git`` with **no** ``--config``, so
gitleaks auto-loads ``.gitleaks.toml`` from the repo root when present. Without
this file, every adopted repo's first Security Scan goes RED on the built-in
``sidekiq-secret`` rule false-matching the magic-hex placeholder
``cafebabe:deadbeef`` (proven on leadwright 2026-06-07: run 27086046885 red →
27086178138 green after the file was added). The allowlist suppresses that one
self-evident placeholder while keeping every real secret rule live.

Two non-negotiable invariants (mirror the security-workflow scaffolder):

1. **Auto-write on absence** — adopt's whole point is to land working CI in
   the target repo, so a missing ``.gitleaks.toml`` is the default case.
2. **Never overwrite** — a pre-existing ``.gitleaks.toml`` (whether a prior
   adopt run or a hand-rolled allowlist) is preserved bit-for-bit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.gitleaks_config_scaffolder import scaffold_gitleaks_config


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Empty target-repo skeleton."""
    return tmp_path


def test_writes_when_absent(tmp_project: Path) -> None:
    result = scaffold_gitleaks_config(tmp_project)

    assert result["wrote"] is True
    assert result["reason"] == "scaffolded"
    config = tmp_project / ".gitleaks.toml"
    assert config.exists(), "scaffolder did not write the .gitleaks.toml file"
    assert result["path"] == str(config)


def test_content_matches_template(tmp_project: Path) -> None:
    scaffold_gitleaks_config(tmp_project)

    written = (tmp_project / ".gitleaks.toml").read_text(encoding="utf-8")
    # Template lives in the shipwright monorepo; the scaffolder must copy it
    # byte-for-byte (modulo encoding) so the drift test's guarantees carry
    # forward to the adopted repo.
    repo_root = Path(__file__).resolve().parents[3]
    template = (
        repo_root
        / "shared"
        / "templates"
        / "github-actions"
        / "gitleaks.toml.template"
    ).read_text(encoding="utf-8")
    assert written == template


def test_written_content_has_cafebabe_allowlist(tmp_project: Path) -> None:
    scaffold_gitleaks_config(tmp_project)

    written = (tmp_project / ".gitleaks.toml").read_text(encoding="utf-8")
    # The whole point: the magic-hex placeholder is allowlisted so the
    # sidekiq-secret false positive cannot redden the adopted repo's scan.
    assert "useDefault = true" in written
    assert "cafebabe:deadbeef" in written
    assert "cafebabe" in written and "deadbeef" in written


def test_idempotent_existing_file_preserved(tmp_project: Path) -> None:
    config = tmp_project / ".gitleaks.toml"
    user_content = "# user-authored gitleaks allowlist — do not touch\n"
    config.write_text(user_content, encoding="utf-8")

    result = scaffold_gitleaks_config(tmp_project)

    assert result["wrote"] is False
    assert result["reason"] == "already_exists"
    # Critical: the user's file is untouched.
    assert config.read_text(encoding="utf-8") == user_content


def test_idempotent_when_called_twice(tmp_project: Path) -> None:
    first = scaffold_gitleaks_config(tmp_project)
    second = scaffold_gitleaks_config(tmp_project)

    assert first["wrote"] is True
    assert second["wrote"] is False
    assert second["reason"] == "already_exists"
    assert (tmp_project / ".gitleaks.toml").exists()


def test_raises_loudly_when_template_missing(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A convention-lock path that doesn't resolve is a development-time bug,
    # not a target-project condition — the scaffolder must fail loud, not
    # write an empty allowlist that silently re-opens the red-first-run gap.
    import lib.gitleaks_config_scaffolder as mod

    monkeypatch.setattr(mod, "_REPO_ROOT", tmp_project / "no-such-tree")
    with pytest.raises(FileNotFoundError, match="gitleaks config template missing"):
        scaffold_gitleaks_config(tmp_project)
    # Failing loud means NOT leaving a half-written config behind.
    assert not (tmp_project / ".gitleaks.toml").exists()
