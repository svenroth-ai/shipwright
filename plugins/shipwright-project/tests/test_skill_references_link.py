"""Meta-test for the Kern SKILL.md <-> references/*.md producer/consumer
boundary (campaign B1.project, 2026-05-26).

After the 612-LOC SKILL.md is split into a thin Kern (<=300 LOC) +
references/step-*.md per-step docs + topical references, two things
must hold structurally:

1. Every `references/...` link inside Kern SKILL.md resolves to an
   existing file on disk.
2. Every reference file produced by this split is linked from Kern
   SKILL.md. Orphan reference files = dead documentation, since the
   agent only loads what Kern points at.

Modeled after `plugins/shipwright-design/tests/test_skill_references_link.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

SKILL_PATH = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "project"
    / "SKILL.md"
)
REFERENCES_DIR = SKILL_PATH.parent / "references"

# Step-level / topical references this iterate produces (one per long
# Step or section in the original SKILL.md procedure).
EXPECTED_STEP_REFERENCES = {
    "first-actions.md",
    "step-0-context-recovery.md",
    "step-1-interview.md",
    "step-4-confirmation.md",
    "step-5-create-dirs.md",
    "step-6-spec-gen.md",
    "step-7-scaffolding.md",
    "step-8-completion.md",
    "error-handling.md",
}

# Pre-existing topical references (kept after the split, must remain
# linked from Kern). All 5 already exist before this split.
EXPECTED_PREEXISTING_REFERENCES = {
    "interview-protocol.md",
    "split-heuristics.md",
    "project-manifest.md",
    "spec-generation.md",
    "project-scaffolding.md",
}

LINK_PATTERN = re.compile(r"references/([A-Za-z0-9_.+\-]+\.md)")


def _kern_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _linked_references() -> set[str]:
    """Extract every `references/<filename>.md` link from Kern."""
    return set(LINK_PATTERN.findall(_kern_text()))


def test_skill_md_exists() -> None:
    assert SKILL_PATH.is_file(), f"Kern SKILL.md missing at {SKILL_PATH}"


def test_references_dir_exists() -> None:
    assert REFERENCES_DIR.is_dir(), f"references dir missing at {REFERENCES_DIR}"


def test_every_kern_link_resolves() -> None:
    """Every `references/X.md` mentioned in Kern must exist on disk."""
    missing: list[str] = []
    for name in _linked_references():
        if not (REFERENCES_DIR / name).is_file():
            missing.append(name)
    assert not missing, (
        "Kern SKILL.md links to references that don't exist on disk: "
        f"{sorted(missing)}"
    )


def test_every_expected_step_reference_exists_and_is_linked() -> None:
    """Each step reference file from EXPECTED_STEP_REFERENCES must
    exist AND be linked from Kern.
    """
    linked = _linked_references()
    missing_on_disk = sorted(
        name for name in EXPECTED_STEP_REFERENCES
        if not (REFERENCES_DIR / name).is_file()
    )
    assert not missing_on_disk, (
        f"Expected step reference files missing on disk: {missing_on_disk}"
    )
    not_linked = sorted(EXPECTED_STEP_REFERENCES - linked)
    assert not not_linked, (
        f"Step references exist on disk but Kern does not link them: "
        f"{not_linked}. Either remove the file or link it from Kern."
    )


def test_every_expected_preexisting_reference_exists_and_is_linked() -> None:
    linked = _linked_references()
    missing_on_disk = sorted(
        name for name in EXPECTED_PREEXISTING_REFERENCES
        if not (REFERENCES_DIR / name).is_file()
    )
    assert not missing_on_disk, (
        f"Expected pre-existing reference files missing on disk: {missing_on_disk}"
    )
    not_linked = sorted(EXPECTED_PREEXISTING_REFERENCES - linked)
    assert not not_linked, (
        f"Pre-existing references exist on disk but Kern does not link them: "
        f"{not_linked}"
    )


def test_every_new_reference_under_loc_budget() -> None:
    """Every NEW reference file produced by this split must be <= 400 LOC
    (runtime-prompt budget). The pre-existing references are covered by
    the bloat baseline; this test enforces the no-fresh-grandfathered
    rule for the files this iterate creates.
    """
    over: list[tuple[str, int]] = []
    for name in EXPECTED_STEP_REFERENCES:
        path = REFERENCES_DIR / name
        if not path.is_file():
            continue
        loc = sum(1 for _ in path.read_text(encoding="utf-8").splitlines())
        if loc > 400:
            over.append((name, loc))
    assert not over, (
        f"Reference files exceed the 400-LOC runtime-prompt budget: {over}. "
        f"Split them further before committing."
    )


def test_kern_skill_md_under_300_loc() -> None:
    """The Kern SKILL.md MUST be <= 300 LOC after the split (campaign
    cleanup-invariant rule (a)). 612 -> ~250 was the spec target.
    """
    loc = sum(1 for _ in _kern_text().splitlines())
    assert loc <= 300, (
        f"Kern SKILL.md is {loc} LOC, must be <= 300 after split. "
        f"Move more content into references/."
    )
