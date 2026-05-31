"""Drift-protection for the Test Completeness Ledger gate in SKILL.md.

iterate-2026-05-30-test-completeness-gate.

Split out of test_skill_phase_matrix.py so that grandfathered file stays
net-zero under the bloat anti-ratchet. Asserts the SKILL.md Phase Matrix
carries a 'Test Completeness Ledger' row graduated as
trivial=n/a / small=medium=large=always (the structural pin for the
operator's "every merge" requirement), and that Override Classes lists it.
"""

from pathlib import Path

SKILL_PATH = (
    Path(__file__).resolve().parent.parent
    / "skills" / "iterate" / "SKILL.md"
)


def _section(heading_substr: str) -> str:
    """Return the H2 section whose heading contains ``heading_substr``."""
    lines = SKILL_PATH.read_text(encoding="utf-8").splitlines()
    start = next(
        (i for i, ln in enumerate(lines)
         if ln.startswith("## ") and heading_substr in ln.lower()),
        None,
    )
    assert start is not None, f"section '{heading_substr}' not found"
    end = next(
        (j for j in range(start + 1, len(lines)) if lines[j].startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _matrix_row(label: str) -> list[str] | None:
    for line in _section("phase matrix").splitlines():
        if not line.startswith("|"):
            continue
        inner = line.strip().strip("|")
        cells = [c.strip() for c in inner.split("|")]
        if cells and cells[0].lower() == label.lower():
            return cells
    return None


def test_phase_matrix_has_test_completeness_row():
    cells = _matrix_row("Test Completeness Ledger")
    assert cells is not None, "Phase Matrix missing 'Test Completeness Ledger' row"
    assert len(cells) >= 5, f"too few cells: {cells!r}"
    trivial, small, medium, large = (c.lower() for c in cells[1:5])
    assert "n/a" in trivial, f"trivial expected 'n/a', got {trivial!r}"
    assert "always" in small, f"small expected 'always', got {small!r}"
    assert "always" in medium, f"medium expected 'always', got {medium!r}"
    assert "always" in large, f"large expected 'always', got {large!r}"


def test_override_classes_has_test_completeness_ledger():
    assert "test completeness ledger" in _section("override classes").lower(), (
        "Override Classes missing 'Test Completeness Ledger' entry"
    )
