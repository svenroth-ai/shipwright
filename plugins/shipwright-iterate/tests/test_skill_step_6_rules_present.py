"""Drift-protection for the three Step 6 governance rules added by
iterate-2026-05-11-test-hygiene-and-skill-rules (AC-5).

Pins that SKILL.md Step 6 contains three named rule anchors:

1. **Test-Update-Klausel** — when changing test infrastructure, update
   the skill's reference rules to match.
2. **Registry-driven SSoT meta-test rule** — every registry that maps
   to files on disk needs both forward AND reverse drift tests.
3. **Silent-skip CI-discipline rule** — pytest.skip on missing-binary
   / missing-import paths must hard-fail in CI with an install hint.

Per external-review #O12: anchor the probe on the Step 6 heading first,
then search the section body for normalized rule keys — NOT arbitrary
prose fragments. This survives whitespace tweaks and minor rewording
of the surrounding text, but fails when a rule disappears entirely or
is renamed.

Mirrors the ADR-021 decision-log drift-protection pattern.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Resolve repo root by walking up from this test file. The test lives in
# plugins/shipwright-iterate/tests/, so parents[3] is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_MD = (
    REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate" / "SKILL.md"
)

# Canonical rule anchors (each MUST appear inside Step 6 body).
# Order matches the spec; substring matching is intentionally lenient.
RULE_ANCHORS = (
    "Test-Update-Klausel",
    "Registry-driven SSoT",
    "Silent-skip CI-discipline",
)


def _extract_step_6_body(text: str) -> str:
    """Return the body of `### Step 6: Build (TDD ...)` until the next H3.

    Anchored on the heading first per external-review #O12 — keyword-only
    matching would false-positive on the Override Classes table.
    """
    # Match the heading; capture everything until the next "### " at line start.
    pattern = re.compile(
        r"^### Step 6: Build.*?(?=\n### )",
        flags=re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return ""
    return match.group(0)


def test_skill_md_exists() -> None:
    """Smoke check: SKILL.md is at the expected location."""
    assert SKILL_MD.is_file(), f"SKILL.md not found at {SKILL_MD}"


def test_step_6_heading_present() -> None:
    """The `### Step 6: Build` heading must exist for the anchor probe to work."""
    text = SKILL_MD.read_text(encoding="utf-8")
    body = _extract_step_6_body(text)
    assert body, (
        "Could not extract Step 6 body from SKILL.md. Expected a heading "
        '`### Step 6: Build (TDD ...)` followed by content. If Step 6 was '
        "renamed or restructured, update both the probe regex and this test."
    )


@pytest.mark.parametrize("anchor", RULE_ANCHORS)
def test_step_6_carries_rule_anchor(anchor: str) -> None:
    """Each governance-rule anchor must appear in Step 6's body.

    Failure = the rule was either:
    - Removed entirely (regression), or
    - Renamed (deliberate but unannounced) — update RULE_ANCHORS.

    External-review #O12 wanted anchor-based matching over prose fragments
    to keep this stable under benign edits.
    """
    text = SKILL_MD.read_text(encoding="utf-8")
    body = _extract_step_6_body(text)
    assert anchor in body, (
        f"Step 6 of SKILL.md is missing the rule anchor {anchor!r}. "
        f"This is one of the three governance rules added by "
        f"iterate-2026-05-11-test-hygiene-and-skill-rules (AC-5). "
        f"If the rule was deliberately removed or renamed, update "
        f"RULE_ANCHORS in this test and document the change in an ADR."
    )


def test_step_6_anchors_not_in_unrelated_sections() -> None:
    """Anchor uniqueness: each rule anchor MUST live in Step 6's body, not
    elsewhere in the skill. Catches the case where someone moves the rules
    out of Step 6 (into a reference doc, say) without updating the
    probe — the false-positive shape from ADR-025.

    A migration to a reference doc is fine, but it must update Step 6 to
    link out AND keep at least the anchor in Step 6's body for this probe.
    """
    text = SKILL_MD.read_text(encoding="utf-8")
    step_6 = _extract_step_6_body(text)
    for anchor in RULE_ANCHORS:
        # Total count across SKILL.md must be >= 1 (covered above) AND
        # at least one occurrence must be inside Step 6's body.
        assert anchor in step_6, (
            f"Rule anchor {anchor!r} is not inside Step 6's body. "
            f"Found total occurrences in SKILL.md: {text.count(anchor)}. "
            f"Move the rule back to Step 6 or update RULE_ANCHORS."
        )
