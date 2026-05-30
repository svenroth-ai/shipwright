"""Drift-protection test for SKILL.md Phase Matrix (Section 6).

Sub-Iterate B — Confidence Calibration Phase (campaign iterate-skill-hardening).

Asserts that:
  - Phase Matrix table contains a "Boundary Probe" row (added by Sub-Iterate A)
  - Phase Matrix table contains a "Confidence Calibration" row (added by B)
  - Override Classes table contains a "Confidence Calibration" entry
  - Path A Step 7.5 (Confidence Calibration) exists between Step 7 and Step 8
  - Iterate spec template includes the 4 Confidence Calibration bullets

Parser is loose: case-insensitive line containment + table-row pattern.
This catches accidental row removal but tolerates prose / formatting edits.
"""

from pathlib import Path

SKILL_PATH = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "iterate"
    / "SKILL.md"
)


def _read() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _phase_matrix_section() -> str:
    """Return the text of '## 6. Phase Matrix by Complexity' up to next H2."""
    text = _read()
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and "phase matrix" in line.lower():
            start = i
            break
    assert start is not None, "Phase Matrix section heading not found"
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return "\n".join(lines[start:end])


def _override_classes_section() -> str:
    """Return the text of '## Override Classes' up to next H2."""
    text = _read()
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and "override classes" in line.lower():
            start = i
            break
    assert start is not None, "Override Classes section heading not found"
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return "\n".join(lines[start:end])


def test_skill_md_exists():
    assert SKILL_PATH.exists(), f"SKILL.md missing at {SKILL_PATH}"


def test_phase_matrix_has_boundary_probe_row():
    """Sub-Iterate A added Boundary Probe to the matrix; assert still there."""
    section = _phase_matrix_section().lower()
    # Match `| boundary probe |` as a table-row leading cell.
    rows = [line for line in section.splitlines() if line.startswith("|")]
    matches = [r for r in rows if "boundary probe" in r]
    assert matches, (
        "Phase Matrix missing 'Boundary Probe' row "
        "(should have been added by Sub-Iterate A)"
    )


def test_phase_matrix_has_confidence_calibration_row():
    """Sub-Iterate B adds Confidence Calibration row to the matrix."""
    section = _phase_matrix_section().lower()
    rows = [line for line in section.splitlines() if line.startswith("|")]
    matches = [r for r in rows if "confidence calibration" in r]
    assert matches, "Phase Matrix missing 'Confidence Calibration' row"


def _parse_matrix_row(section_text: str, row_label: str) -> list[str] | None:
    """Find a Phase Matrix row by its first cell label (case-insensitive).

    Returns the list of cells (with the label cell at index 0) or None.
    """
    label_lower = row_label.lower()
    for line in section_text.splitlines():
        if not line.startswith("|"):
            continue
        # Strip leading/trailing pipes, split.
        inner = line.strip()[1:-1] if line.strip().endswith("|") else line.strip()[1:]
        cells = [c.strip() for c in inner.split("|")]
        if cells and cells[0].lower() == label_lower:
            return cells
    return None


def test_phase_matrix_confidence_calibration_cells_explicit():
    """E spec MEDIUM-B2: cell-level assert for the Confidence Calibration row.

    Expected cells: Phase | trivial | small | medium | large | escalation
    With trivial=skip, small=if-flag (touches_io_boundary), medium=always,
    large=always.
    """
    section = _phase_matrix_section()
    cells = _parse_matrix_row(section, "Confidence Calibration")
    assert cells is not None, (
        "Phase Matrix missing a row whose first cell == 'Confidence Calibration'"
    )
    # Phase | trivial | small | medium | large | escalation  → 6 cells.
    assert len(cells) >= 5, (
        f"Confidence Calibration row has too few cells: {cells!r}"
    )
    trivial, small, medium, large = cells[1].lower(), cells[2].lower(), cells[3].lower(), cells[4].lower()
    assert "skip" in trivial, f"trivial cell expected 'skip', got {trivial!r}"
    # small must be flag-conditional (NOT 'always', NOT 'skip').
    assert (
        "touches_io_boundary" in small or "if" in small
    ), f"small cell expected flag-conditional, got {small!r}"
    assert "always" in medium, f"medium cell expected 'always', got {medium!r}"
    assert "always" in large, f"large cell expected 'always', got {large!r}"


def test_phase_matrix_boundary_probe_cells_explicit():
    """E spec MEDIUM-B2: cell-level assert for the Boundary Probe row.

    Expected: trivial=skip, small=if-flag, medium=if-flag, large=—.
    """
    section = _phase_matrix_section()
    cells = _parse_matrix_row(section, "Boundary Probe")
    assert cells is not None, (
        "Phase Matrix missing a row whose first cell == 'Boundary Probe'"
    )
    assert len(cells) >= 5, (
        f"Boundary Probe row has too few cells: {cells!r}"
    )
    trivial, small, medium, large = cells[1].lower(), cells[2].lower(), cells[3].lower(), cells[4].lower()
    assert "skip" in trivial, f"trivial cell expected 'skip', got {trivial!r}"
    assert "touches_io_boundary" in small or "if" in small, (
        f"small cell expected flag-conditional, got {small!r}"
    )
    assert "touches_io_boundary" in medium or "if" in medium, (
        f"medium cell expected flag-conditional, got {medium!r}"
    )
    # large='—' (em-dash) means N/A — not 'always'/'skip'/'if'.
    assert "—" in large or "-" in large or "n/a" in large, (
        f"large cell expected '—' / N/A, got {large!r}"
    )


def test_override_classes_has_confidence_calibration_in_all_three_classifications():
    """E spec MEDIUM-A3: Confidence Calibration must appear in Mandatory,
    Safety-enforced, AND Advisory rows. The original Override Classes
    table only had Mandatory + Safety-enforced cells; the Advisory case
    was implicit-by-omission.
    """
    section = _override_classes_section().lower()
    # Find each row by its category label.
    row_lines = [line for line in section.splitlines() if line.startswith("|")]
    by_category: dict[str, str] = {}
    for line in row_lines:
        inner = line.strip("|").strip()
        cells = [c.strip() for c in inner.split("|")]
        if not cells:
            continue
        # The category is in the first cell, often wrapped in **bold**.
        label = cells[0].replace("*", "").strip()
        by_category[label] = line

    # Find the three categories (case-insensitive substring).
    matches = {}
    for cat in ("mandatory", "safety-enforced", "advisory"):
        for label, row in by_category.items():
            if cat in label:
                matches[cat] = row
                break

    missing = [c for c in ("mandatory", "safety-enforced", "advisory") if c not in matches]
    assert not missing, f"Override Classes table missing categories: {missing}"

    for cat in ("mandatory", "safety-enforced", "advisory"):
        assert "confidence calibration" in matches[cat], (
            f"Override Classes '{cat}' row missing 'Confidence Calibration': "
            f"{matches[cat]!r}"
        )


def test_override_classes_has_boundary_probe():
    """Sub-Iterate A added Boundary Probe to Override Classes."""
    section = _override_classes_section().lower()
    assert "boundary probe" in section, (
        "Override Classes missing 'Boundary Probe' entry "
        "(should have been added by Sub-Iterate A)"
    )


def test_override_classes_has_confidence_calibration():
    """Sub-Iterate B adds Confidence Calibration to Override Classes."""
    section = _override_classes_section().lower()
    assert "confidence calibration" in section, (
        "Override Classes missing 'Confidence Calibration' entry"
    )


def test_path_a_has_step_7_5():
    """Step 7.5: Confidence Calibration must exist in Path A between 7 and 8."""
    text = _read()
    # Look for the heading. Allow either '### Step 7.5' or '#### Step 7.5'.
    has_step = any(
        ("step 7.5" in line.lower() and "confidence calibration" in line.lower())
        for line in text.splitlines()
        if line.lstrip().startswith("#")
    )
    assert has_step, (
        "Path A Step 7.5 (Confidence Calibration) heading not found"
    )


def test_step_7_5_between_step_7_and_step_8():
    """Step 7.5 must appear between Step 7 (Self-Review) and Step 8 (Full Code Review)."""
    text = _read()
    lines = text.splitlines()
    pos7 = None
    pos75 = None
    pos8 = None
    for i, line in enumerate(lines):
        low = line.lower()
        if line.lstrip().startswith("#"):
            if pos7 is None and "step 7:" in low and "self-review" in low:
                pos7 = i
            elif (
                pos75 is None
                and "step 7.5" in low
                and "confidence calibration" in low
            ):
                pos75 = i
            elif (
                pos8 is None
                and "step 8:" in low
                and "full code review" in low
            ):
                pos8 = i
    assert pos7 is not None, "Step 7 (Self-Review) heading not found"
    assert pos75 is not None, "Step 7.5 (Confidence Calibration) heading not found"
    assert pos8 is not None, "Step 8 (Full Code Review) heading not found"
    assert pos7 < pos75 < pos8, (
        f"Step 7.5 must be between Step 7 and Step 8 "
        f"(positions: 7={pos7}, 7.5={pos75}, 8={pos8})"
    )


def test_iterate_spec_template_has_calibration_section():
    """Iterate spec template (Path A Step 1) must include Confidence Calibration block."""
    text = _read()
    # The template includes '## Confidence Calibration' inside a fenced
    # markdown block. Look for the heading literally — it appears verbatim
    # in the template body.
    assert "## Confidence Calibration" in text, (
        "Iterate spec template missing '## Confidence Calibration' heading"
    )


def test_iterate_spec_template_has_four_calibration_bullets():
    """The iterate spec template must include the 4 calibration bullets per spec.

    E spec MEDIUM-B1: scope the search to the fenced ```markdown ... ```
    block under "### Step 1: Iterate Spec" in Path A. The original test
    searched the entire SKILL.md, but those keywords also appear in the
    Step 7.5 prose — so the test would still pass even if the fenced
    template block were deleted. This version asserts the bullets live
    INSIDE the template fence.
    """
    text = _read()
    lines = text.splitlines()
    # Find the Step 1 heading.
    step1_idx = None
    for i, line in enumerate(lines):
        low = line.lower()
        if line.lstrip().startswith("#") and (
            "step 1:" in low and "iterate spec" in low
        ):
            step1_idx = i
            break
    assert step1_idx is not None, (
        "Path A 'Step 1: Iterate Spec' heading not found"
    )

    # Find the first ```markdown fence after Step 1.
    fence_start = None
    for i in range(step1_idx + 1, len(lines)):
        if lines[i].strip().startswith("```markdown"):
            fence_start = i
            break
        # Don't cross out of Path A by mistake — bail at next H2.
        if lines[i].startswith("## "):
            break
    assert fence_start is not None, (
        "Iterate Spec template ```markdown fence not found after Step 1"
    )

    # Find the matching closing fence.
    fence_end = None
    for j in range(fence_start + 1, len(lines)):
        if lines[j].strip() == "```":
            fence_end = j
            break
    assert fence_end is not None, (
        "Iterate Spec template fence has no closing ``` line"
    )

    fenced_block = "\n".join(lines[fence_start + 1:fence_end]).lower()
    required_bullets = [
        "boundaries touched",
        "empirical probes",
        "test completeness",  # was "edge cases not probed" (escape hatch removed)
        "confidence-pattern check",
    ]
    missing = [b for b in required_bullets if b not in fenced_block]
    assert not missing, (
        f"Iterate spec template (fenced block under Path A Step 1) missing "
        f"calibration bullet keywords: {missing}. The bullets must live "
        f"INSIDE the template fence so deleting the template fails this "
        f"test (drift protection)."
    )


def test_path_b_cross_references_step_7_5():
    """Path B (CHANGE) must cross-reference Step 7.5."""
    text = _read()
    lines = text.splitlines()
    # Find Path B section.
    path_b_start = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and "path b" in line.lower():
            path_b_start = i
            break
    assert path_b_start is not None, "Path B section not found"
    path_b_end = len(lines)
    for j in range(path_b_start + 1, len(lines)):
        if lines[j].startswith("## "):
            path_b_end = j
            break
    section = "\n".join(lines[path_b_start:path_b_end]).lower()
    assert "step 7.5" in section or "confidence calibration" in section, (
        "Path B does not cross-reference Step 7.5 / Confidence Calibration"
    )


def test_path_c_cross_references_step_7_5():
    """Path C (BUG) must cross-reference Step 7.5."""
    text = _read()
    lines = text.splitlines()
    path_c_start = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and "path c" in line.lower():
            path_c_start = i
            break
    assert path_c_start is not None, "Path C section not found"
    path_c_end = len(lines)
    for j in range(path_c_start + 1, len(lines)):
        if lines[j].startswith("## "):
            path_c_end = j
            break
    section = "\n".join(lines[path_c_start:path_c_end]).lower()
    assert "step 7.5" in section or "confidence calibration" in section, (
        "Path C does not cross-reference Step 7.5 / Confidence Calibration"
    )
