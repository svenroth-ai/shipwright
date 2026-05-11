"""Drift-protection for the Self-Review Section 8 ("Test Hygiene Probe")
added by iterate-2026-05-11-test-hygiene-helper-and-self-review-wiring (AC-5).

Pins that ``references/iteration-reviews.md`` contains:

1. A ``### 8. Test Hygiene Probe`` heading inside the Self-Review checklist.
2. The CLI invocation snippet
   ``uv run shared/scripts/tools/scan_test_hygiene.py --diff`` inside that
   section.
3. The "Mandatory at medium+" wording inside that section.

Mirrors the ADR-044 / PR #26 pattern (anchor on heading first, then search
the section body for normalized invocation keys — NOT arbitrary prose).
External-review #O12 from the prior iterate motivated this anchor style.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
REVIEWS_MD = (
    REPO_ROOT
    / "plugins"
    / "shipwright-iterate"
    / "skills"
    / "iterate"
    / "references"
    / "iteration-reviews.md"
)


def _extract_section_8_body(text: str) -> str:
    """Return the body of `### 8. Test Hygiene Probe` until the next heading.

    Anchored on the H3 heading first. The next-heading boundary is any line
    starting with `## ` or `### ` after section 8's heading.
    """
    pattern = re.compile(
        r"^### 8\. Test Hygiene Probe.*?(?=^(?:## |### )|\Z)",
        flags=re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return ""
    return match.group(0)


def test_iteration_reviews_md_exists() -> None:
    """Smoke check: iteration-reviews.md is at the expected location."""
    assert REVIEWS_MD.is_file(), f"iteration-reviews.md not found at {REVIEWS_MD}"


def test_section_8_heading_present() -> None:
    """The Section 8 heading must exist for the anchor probe to work."""
    text = REVIEWS_MD.read_text(encoding="utf-8")
    body = _extract_section_8_body(text)
    assert body, (
        "Could not extract Section 8 body from iteration-reviews.md. "
        "Expected a heading `### 8. Test Hygiene Probe` followed by content. "
        "If Section 8 was renamed or restructured, update both the probe "
        "regex and this test."
    )


def test_section_8_carries_cli_invocation() -> None:
    """Section 8 must contain the canonical CLI invocation snippet."""
    text = REVIEWS_MD.read_text(encoding="utf-8")
    body = _extract_section_8_body(text)
    expected = "uv run shared/scripts/tools/scan_test_hygiene.py --diff"
    assert expected in body, (
        f"Section 8 of iteration-reviews.md is missing the CLI invocation "
        f"snippet {expected!r}. The Self-Review item is only mechanically "
        f"executable when this exact command appears. If the CLI was moved "
        f"or renamed, update both this test and the iteration-reviews.md "
        f"section in the same diff (Test-Update-Klausel, ADR-044)."
    )


def test_section_8_carries_mandatory_at_medium_wording() -> None:
    """Section 8 must explicitly state it is mandatory at medium+."""
    text = REVIEWS_MD.read_text(encoding="utf-8")
    body = _extract_section_8_body(text)
    assert "Mandatory at medium+" in body, (
        "Section 8 must explicitly carry the 'Mandatory at medium+' wording — "
        "without it, the rule degrades to advisory across all complexity "
        "levels and the Self-Review gate is structurally toothless. "
        "Required by iterate-2026-05-11-test-hygiene-helper-and-self-review-wiring AC-4."
    )


def test_self_review_intro_mentions_eight_point_checklist() -> None:
    """The 'X-point checklist' wording in the Self-Review intro must scale
    with the actual item count.

    Prevents the regression where Section 8 is added but the intro still
    advertises '7-point checklist' — operators skim the intro to decide
    how much process applies and the bug would silently underrun the gate.
    """
    text = REVIEWS_MD.read_text(encoding="utf-8")
    assert "8-point checklist" in text, (
        "Self-Review intro must advertise '8-point checklist' once Section 8 "
        "lands. Found neither — either Section 8 wasn't added (AC-4 incomplete) "
        "or the intro still says '7-point checklist' (regression)."
    )
    assert "7-point checklist" not in text, (
        "Self-Review intro still mentions '7-point checklist' but Section 8 "
        "exists. Bump to '8-point checklist' to keep intro and item count "
        "consistent."
    )
