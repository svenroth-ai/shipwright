"""Anchor- and region-scoping edge cases for the cross-layer criteria digest
(Stage-3 doubt review, 2026-08-25), split out of ``test_layer_coverage_criteria.py``
(bloat anti-ratchet: that file crossed its 300-line baseline) the same way
``test_spec_checks_shipped_form.py`` was split out of ``test_spec_checks.py``
earlier in this run.

Both cases below are about WHERE ``criteria_digests`` looks, not what counts
as a criterion once it is looking: a nested FR heading getting its own
anchor (``iter_anchored_blocks``), and a real, deeper ``Acceptance Criteria``
heading level being found at all (``_criteria_region``). See
``test_layer_coverage_criteria.py``'s module docstring for the parser this
suite is part of.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))

from verifiers._layer_coverage_ac import criteria_digests  # noqa: E402


def test_a_nested_fr_heading_still_gets_its_own_digest_entry():
    """A DEEPER heading nested inside a parent's block (`### FR-01.02` inside
    `## FR-01.01`) must still yield its own anchor — the old ``i = j`` jump in
    ``iter_anchored_blocks`` swallowed it into the parent's span instead of
    ever considering it as a candidate anchor (medium, 2026-08-25): the id
    vanished from BOTH sides of a diff, so ``criteria_changed_keys`` could
    never see it change. No wrapping ``## Acceptance Criteria`` heading here
    — the whole-document fail-safe scans it directly, exercising
    ``iter_anchored_blocks`` on exactly the reviewer's example."""
    spec = (
        "# Spec\n\n"
        "## FR-01.01 — Parent\n\n"
        "- (E) parent criterion\n\n"
        "### FR-01.02 — Nested\n\n"
        "- (E) nested criterion\n"
    )
    digests = criteria_digests(spec)
    assert "FR-01.01" in digests
    assert "FR-01.02" in digests
    assert digests["FR-01.01"] != digests["FR-01.02"]


def test_level_3_acceptance_criteria_heading_scopes_correctly():
    """`/shipwright-project`'s real spec.md nests the section one level
    deeper than `/shipwright-adopt`'s (`### Acceptance Criteria` under
    `## 2. Functional Requirements`, `spec-generation.md:305`, both the
    abstract template and its worked example) — a level-2-only regex never
    matched it, so ``_criteria_region`` fell back to whole-document scanning
    on every project-generated spec, not a rare exception (medium,
    2026-08-25). With the fix, a bolded FR reference OUTSIDE the level-3
    section (a cross-reference under the sibling `### Removed Requirements`
    heading, same shape a real spec's own template puts there) must not be
    pooled into that FR's digest."""
    spec = (
        "## 2. Functional Requirements\n\n"
        "### Acceptance Criteria\n\n"
        "**FR-01.01: Name**\n"
        "- [ ] real criterion\n\n"
        "### Removed Requirements\n\n"
        "Some note referencing **FR-01.01: Name** again elsewhere.\n"
        "- an unrelated bullet under that stray reference\n\n"
        "## 3. Constraints\n\n"
        "- something\n"
    )
    only_real = (
        "## 2. Functional Requirements\n\n"
        "### Acceptance Criteria\n\n"
        "**FR-01.01: Name**\n"
        "- [ ] real criterion\n"
    )
    assert criteria_digests(spec)["FR-01.01"] == criteria_digests(only_real)["FR-01.01"]
