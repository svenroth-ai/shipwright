"""Meta-test for the Kern SKILL.md <-> references/*.md producer/consumer
boundary (campaign B1.iterate, 2026-05-25).

After the 1709-LOC SKILL.md is split into a thin Kern (~250 LOC) +
references/F*.md per-phase docs + topical references, two things must
hold structurally:

1. Every `references/...` link inside Kern SKILL.md resolves to an
   existing file on disk.
2. Every `references/F*.md` (per-phase reference) and every topical
   reference produced by this split is linked from Kern SKILL.md.
   Orphan reference files = dead documentation, since the agent only
   loads what Kern points at.

The set of "expected" references is intentionally minimal — we only
assert membership for the F-phase + topical references this iterate
produces. The pre-existing references (`boundary-probes.md`,
`round-trip-tests.md`, etc.) are covered by the link-resolution arm.
"""

from __future__ import annotations

import re
from pathlib import Path

SKILL_PATH = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "iterate"
    / "SKILL.md"
)
REFERENCES_DIR = SKILL_PATH.parent / "references"

# F-phase references this iterate produces. The names mirror SKILL.md
# section anchors so a future reader can grep both sides.
EXPECTED_F_REFERENCES = {
    "F0.md",
    "F0.5.md",
    "F1.md",
    "F2.md",
    "F3.md",
    "F3a.md",
    "F4.md",
    "F5.md",
    "F5b.md",
    "F5c.md",
    "F6.md",
    "F6.5.md",
    "F7.md",
    "F7b.md",
    "F11.md",
    "F12.md",
}

# Topical references this iterate produces.
EXPECTED_TOPICAL_REFERENCES = {
    "context-loading.md",
    "campaign-mode.md",
    "mid-flight-escalation.md",
    "escape-hatch.md",
    "artifact-ownership.md",
    "degraded-mode.md",
    "error-handling.md",
    "path-a-feature.md",
    "path-b-change.md",
    "path-c-bug.md",
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


def test_every_expected_f_reference_exists_and_is_linked() -> None:
    """Each F-phase reference file from EXPECTED_F_REFERENCES must
    exist AND be linked from Kern.
    """
    linked = _linked_references()
    missing_on_disk = sorted(
        name for name in EXPECTED_F_REFERENCES
        if not (REFERENCES_DIR / name).is_file()
    )
    assert not missing_on_disk, (
        f"Expected F-phase reference files missing on disk: {missing_on_disk}"
    )
    not_linked = sorted(EXPECTED_F_REFERENCES - linked)
    assert not not_linked, (
        f"F-phase references exist on disk but Kern does not link them: "
        f"{not_linked}. Either remove the file or link it from Kern."
    )


def test_every_expected_topical_reference_exists_and_is_linked() -> None:
    linked = _linked_references()
    missing_on_disk = sorted(
        name for name in EXPECTED_TOPICAL_REFERENCES
        if not (REFERENCES_DIR / name).is_file()
    )
    assert not missing_on_disk, (
        f"Expected topical reference files missing on disk: {missing_on_disk}"
    )
    not_linked = sorted(EXPECTED_TOPICAL_REFERENCES - linked)
    assert not not_linked, (
        f"Topical references exist on disk but Kern does not link them: "
        f"{not_linked}"
    )


def test_every_new_reference_under_loc_budget() -> None:
    """Every NEW reference file produced by this split must be <= 400 LOC
    (runtime-prompt budget). The pre-existing references are covered by
    the bloat baseline; this test enforces the no-fresh-grandfathered
    rule for the files this iterate creates.
    """
    over: list[tuple[str, int]] = []
    candidates = EXPECTED_F_REFERENCES | EXPECTED_TOPICAL_REFERENCES
    for name in candidates:
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
    cleanup-invariant rule (a)). 1709 -> ~250 was the spec target.
    """
    loc = sum(1 for _ in _kern_text().splitlines())
    assert loc <= 300, (
        f"Kern SKILL.md is {loc} LOC, must be <= 300 after split. "
        f"Move more content into references/."
    )
