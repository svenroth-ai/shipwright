"""The section writer quotes a brief requirement instead of rewording it (run 27: 'every 3 seconds' became 'within 3 seconds')."""

from pathlib import Path

WRITER = Path(__file__).resolve().parents[1] / "agents" / "section-writer.md"


def test_section_writer_copies_the_briefs_wording():
    text = WRITER.read_text(encoding="utf-8")
    assert "A brief requirement is quoted, never reworded" in text
    assert "every 3 seconds" in text and "within 3 seconds" in text
