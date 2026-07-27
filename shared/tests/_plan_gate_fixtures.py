"""Planning-split fixtures shared by the plan-gate test modules.

``test_verifiers_plan_gates.py`` pins what each gate decides;
``test_verifiers_plan_gates_wiring.py`` pins that phase completion runs them.
Both need the same seeded split, and neither owns it.
"""

from pathlib import Path

#: A section in the shape the gates require.
WELL_FORMED = (
    "# Section: {name}\n\n"
    "Requirements: {frs}\n\n"
    "## Overview\nDoes the thing.\n\n"
    "## Implementation Steps\n1. one\n2. two\n\n"
    "## Tests First\n- a unit test\n"
)

#: What a section written before any of this looked like: the old template's
#: headings, and no requirement field.
LEGACY = (
    "# Section: {name}\n\n"
    "## Overview\nDoes the thing.\n\n"
    "## Implementation Steps\n1. one\n2. two\n\n"
    "## Tests First\n- a unit test\n"
)


def seed(
    tmp_path: Path,
    *,
    manifest: str,
    sections: dict[str, str],
    frs: tuple[str, ...] = ("FR-01.01",),
    split: str = "01-auth",
) -> Path:
    """Write one planning split (spec + plan + sections) and return the root."""
    split_dir = tmp_path / ".shipwright" / "planning" / split
    (split_dir / "sections").mkdir(parents=True, exist_ok=True)
    rows = "\n".join(f"| {fr} | {fr} description | Must |" for fr in frs)
    (split_dir / "spec.md").write_text(
        f"# Spec\n\n| ID | Requirement | Priority |\n{rows}\n", encoding="utf-8"
    )
    (split_dir / "plan.md").write_text(
        f"# Plan\n\n<!-- SECTION_MANIFEST\n{manifest}\nEND_MANIFEST -->\n", encoding="utf-8"
    )
    for name, body in sections.items():
        (split_dir / "sections" / f"{name}.md").write_text(body, encoding="utf-8")
    return tmp_path
