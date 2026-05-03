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
    """The iterate spec template must include the 4 calibration bullets per spec."""
    text = _read()
    # Per spec AC, the template Confidence Calibration section must include
    # bullets with these keywords (in any order):
    required_bullets = [
        "boundaries touched",
        "empirical probes",
        "edge cases not probed",
        "confidence-pattern check",
    ]
    low = text.lower()
    missing = [b for b in required_bullets if b not in low]
    assert not missing, (
        f"Iterate spec template missing calibration bullet keywords: {missing}"
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
