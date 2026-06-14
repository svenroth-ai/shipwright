"""Format regression for ``write_decision_log._append_architecture_update``.

The release-folded ADR bullets in the always-loaded ``## Architecture Updates``
/ ``## Convention Updates`` sections must be flush (one ``\\n`` apart). The old
writer appended ``"\\n- …\\n"`` to a file already ending in ``"\\n"``, producing
a blank line before every bullet ("nicht schön formatiert"). Kept in its own
file so ``test_write_decision_log.py`` stays under the 300-line guideline.
"""

from __future__ import annotations

from pathlib import Path

from tools.write_decision_log import _append_architecture_update


def _seed_arch_doc(project_root: Path) -> Path:
    doc = project_root / ".shipwright" / "agent_docs"
    doc.mkdir(parents=True, exist_ok=True)
    arch = doc / "architecture.md"
    arch.write_text("# Architecture\n\n## Architecture Updates\n", encoding="utf-8")
    return arch


def test_no_blank_line_between_consecutive_bullets(tmp_path: Path):
    arch = _seed_arch_doc(tmp_path)
    _append_architecture_update(tmp_path, 1, "component", "first", entry_date="2026-06-14")
    _append_architecture_update(tmp_path, 2, "component", "second", entry_date="2026-06-14")
    content = arch.read_text(encoding="utf-8")
    assert "\n\n- **ADR-002**" not in content, content
    assert (
        "- **ADR-001** (2026-06-14): first\n- **ADR-002** (2026-06-14): second\n"
        in content
    )


def test_first_bullet_flush_under_header(tmp_path: Path):
    arch = _seed_arch_doc(tmp_path)
    _append_architecture_update(tmp_path, 1, "component", "first", entry_date="2026-06-14")
    content = arch.read_text(encoding="utf-8")
    # Header immediately followed by the bullet — no blank line in between.
    assert "## Architecture Updates\n- **ADR-001**" in content
