"""Pin Tier-5 doc preservation (sub-iterate F, fix #2 from external review).

External review caught: `setup_adopt.existing_artifacts` reported any file
adopt would touch — except the new Tier-5 docs (design_tokens.md,
guideline.md). And `visual_docs_generator` overwrote them with no backup.
A user who hand-edits guideline.md between adopt runs would silently lose
those edits.
"""

from __future__ import annotations

from pathlib import Path

from lib.visual_docs_generator import generate_visual_docs


def _make_min_frontend(tmp_path: Path) -> None:
    (tmp_path / "src" / "components").mkdir(parents=True)
    (tmp_path / "src" / "components" / "X.tsx").write_text(
        "export const X = () => null;\n", encoding="utf-8",
    )


def test_existing_design_tokens_md_is_preserved_before_overwrite(tmp_path: Path) -> None:
    _make_min_frontend(tmp_path)
    agent_docs = tmp_path / "agent_docs"
    agent_docs.mkdir()
    hand_edited = "# Design Tokens\n\nHAND-EDITED-CONTENT\n"
    (agent_docs / "design_tokens.md").write_text(hand_edited, encoding="utf-8")

    generate_visual_docs(tmp_path)

    backup = tmp_path / ".shipwright" / "adopt" / "backups" / "agent_docs" / "design_tokens.md.preserved"
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == hand_edited


def test_existing_guideline_md_is_preserved_before_overwrite(tmp_path: Path) -> None:
    _make_min_frontend(tmp_path)
    agent_docs = tmp_path / "agent_docs"
    agent_docs.mkdir()
    hand_edited = "# Visual Guideline\n\nHAND-EDITED-DESIGN-NOTES\n"
    (agent_docs / "guideline.md").write_text(hand_edited, encoding="utf-8")

    generate_visual_docs(tmp_path)

    backup = tmp_path / ".shipwright" / "adopt" / "backups" / "agent_docs" / "guideline.md.preserved"
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == hand_edited


def test_preservation_log_records_visual_doc_actions(tmp_path: Path) -> None:
    """The preservation_log.json should capture both visual-doc backups too —
    consistent with how CLAUDE.md / decision_log are logged."""
    import json as _json

    _make_min_frontend(tmp_path)
    agent_docs = tmp_path / "agent_docs"
    agent_docs.mkdir()
    (agent_docs / "design_tokens.md").write_text("# old tokens\n", encoding="utf-8")
    (agent_docs / "guideline.md").write_text("# old guideline\n", encoding="utf-8")

    generate_visual_docs(tmp_path)

    log = _json.loads((tmp_path / ".shipwright" / "adopt" / "preservation_log.json").read_text(encoding="utf-8"))
    files = {e["file"] for e in log["entries"]}
    assert "agent_docs/design_tokens.md" in files
    assert "agent_docs/guideline.md" in files


def test_no_backup_when_visual_docs_absent(tmp_path: Path) -> None:
    """First-run case: no existing files, no backup needed."""
    _make_min_frontend(tmp_path)
    generate_visual_docs(tmp_path)
    assert (tmp_path / "agent_docs" / "design_tokens.md").exists()
    backup_dir = tmp_path / ".shipwright" / "adopt" / "backups" / "agent_docs"
    assert not (backup_dir / "design_tokens.md.preserved").exists()
    assert not (backup_dir / "guideline.md.preserved").exists()


def test_setup_adopt_lists_visual_docs_in_existing_artifacts(tmp_path: Path) -> None:
    """The pre-flight should report the Tier-5 docs alongside the older ones."""
    import subprocess as _sp

    from checks.setup_adopt import run_preflight

    _sp.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    _sp.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit",
             "--allow-empty", "-m", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "agent_docs").mkdir()
    (tmp_path / "agent_docs" / "design_tokens.md").write_text("x", encoding="utf-8")
    (tmp_path / "agent_docs" / "guideline.md").write_text("x", encoding="utf-8")

    report = run_preflight(tmp_path, [])
    artifacts = set(report["existing_artifacts"])
    assert "agent_docs/design_tokens.md" in artifacts
    assert "agent_docs/guideline.md" in artifacts
