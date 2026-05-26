"""Meta-test for the Kern SKILL.md <-> references/*.md producer/consumer
boundary (campaign B1.build, 2026-05-25).

After the 1162-LOC build SKILL.md is split into a thin Kern (<= 300 LOC)
+ references/*.md topical and step files, two things must hold
structurally:

1. Every `references/...` link inside Kern SKILL.md resolves to an
   existing file on disk.
2. Every NEW topical reference produced by this split is linked from
   Kern SKILL.md. Orphan reference files = dead documentation, since
   the agent only loads what Kern points at.

The set of "expected" references is intentionally minimal — we only
assert membership for the topical references this iterate produces.
The pre-existing references (`implementation-loop.md`,
`migration-safety.md`, `git-operations.md`, etc.) are covered by the
link-resolution arm.
"""

from __future__ import annotations

import re
from pathlib import Path

SKILL_PATH = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "build"
    / "SKILL.md"
)
REFERENCES_DIR = SKILL_PATH.parent / "references"

# NEW topical references this iterate produces. The names mirror SKILL.md
# section anchors so a future reader can grep both sides.
EXPECTED_NEW_REFERENCES = {
    "tdd-tests.md",
    "migrations-apply.md",
    "browser-verify.md",
    "code-review.md",
    "section-state.md",
    "autonomous-loop.md",
    "error-handling.md",
    "first-actions.md",
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


def test_every_expected_new_reference_exists_and_is_linked() -> None:
    """Each NEW topical reference file from EXPECTED_NEW_REFERENCES must
    exist AND be linked from Kern.
    """
    linked = _linked_references()
    missing_on_disk = sorted(
        name for name in EXPECTED_NEW_REFERENCES
        if not (REFERENCES_DIR / name).is_file()
    )
    assert not missing_on_disk, (
        f"Expected new reference files missing on disk: {missing_on_disk}"
    )
    not_linked = sorted(EXPECTED_NEW_REFERENCES - linked)
    assert not not_linked, (
        f"New references exist on disk but Kern does not link them: "
        f"{not_linked}. Either remove the file or link it from Kern."
    )


def test_every_new_reference_under_loc_budget() -> None:
    """Every NEW reference file produced by this split must be <= 400 LOC
    (runtime-prompt budget). The pre-existing references are covered by
    the bloat baseline; this test enforces the no-fresh-grandfathered
    rule for the files this iterate creates.
    """
    over: list[tuple[str, int]] = []
    for name in EXPECTED_NEW_REFERENCES:
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
    cleanup-invariant rule (a)). 1162 -> ~250 was the spec target.
    """
    loc = sum(1 for _ in _kern_text().splitlines())
    assert loc <= 300, (
        f"Kern SKILL.md is {loc} LOC, must be <= 300 after split. "
        f"Move more content into references/."
    )
