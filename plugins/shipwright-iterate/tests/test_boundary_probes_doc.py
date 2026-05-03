"""Drift-protection test for references/boundary-probes.md.

Sub-Iterate A — Boundary Tests Foundation (campaign iterate-skill-hardening).

Asserts that the canonical 8 probe categories appear as level-2 markdown
headings in the reference doc. Loose enough to allow prose edits, strict
enough to catch accidental category drops.
"""

from pathlib import Path

import pytest

DOC_PATH = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "iterate"
    / "references"
    / "boundary-probes.md"
)

# Required probe categories. Match against case-insensitive substring of
# any heading line (## ... or ### ...). Keep the keywords short so prose
# edits like "UTF-8 BOM (Byte-Order Mark)" still match.
REQUIRED_CATEGORIES = [
    "utf-8 bom",
    "crlf",
    "non-ascii",
    "export",            # POSIX `export KEY=value` prefix
    "inline",            # inline `# comment`
    "leading whitespace",  # `#` without leading whitespace inside a value
    "quoted",            # quoted values containing `#`
    "empty",             # empty values (`KEY=`, `KEY=""`)
]


def _load_headings() -> list[str]:
    text = DOC_PATH.read_text(encoding="utf-8")
    return [
        line.strip().lower()
        for line in text.splitlines()
        if line.lstrip().startswith("#")
    ]


def test_doc_exists():
    assert DOC_PATH.exists(), f"boundary-probes.md missing at {DOC_PATH}"


def test_doc_not_empty():
    assert DOC_PATH.read_text(encoding="utf-8").strip(), (
        "boundary-probes.md is empty"
    )


@pytest.mark.parametrize("category", REQUIRED_CATEGORIES)
def test_required_category_present(category):
    headings = _load_headings()
    matches = [h for h in headings if category in h]
    assert matches, (
        f"Required probe category '{category}' not found in any heading. "
        f"Headings present: {headings}"
    )


def test_eight_distinct_probe_sections():
    """Sanity: at minimum 8 level-2 (## ) sections exist."""
    text = DOC_PATH.read_text(encoding="utf-8")
    level2_count = sum(
        1 for line in text.splitlines() if line.startswith("## ")
    )
    assert level2_count >= 8, (
        f"Expected at least 8 level-2 sections, found {level2_count}"
    )
