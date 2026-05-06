"""Drift-protection between Phase Matrix, F0.5 section, design-and-testing.md.

The F0.5 End-to-End Verification Gate (ADR-037) is described in three
places that must stay consistent:

1. SKILL.md Phase Matrix row "E2E Verification (author + execute)"
2. SKILL.md F0.5 section ("Mandatory at medium+")
3. references/design-and-testing.md "End-to-End Verification — Authoring"
   + "End-to-End Verification — Execution" (medium+ "always" / "no skip")

If any of these three drifts, the iterate skill's behavior at medium+ is
underspecified. This test is the canary — it fails loudly when one of
the three loses its anchor phrase.

Anti-pattern from ADR-025: don't keyword-match across a long file (you
hit the wrong section). Anchor on section heading first, then probe
within.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_MD = REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate" / "SKILL.md"
DESIGN_TESTING_MD = (
    REPO_ROOT
    / "plugins"
    / "shipwright-iterate"
    / "skills"
    / "iterate"
    / "references"
    / "design-and-testing.md"
)


def _section(text: str, heading_re: str) -> str:
    """Return body between ``heading_re`` and the next equivalent-or-shallower
    heading (fences excluded).

    The match must begin at a line start outside a code fence — otherwise a
    shell comment in a ``` block would be mistaken for a section. ADR-025
    anti-pattern check.
    """
    pattern = re.compile(heading_re, re.MULTILINE)
    in_fence = False
    pos = 0
    found_start = -1
    found_depth = 0
    # First pass: find the heading anchored on heading_re, skipping fences
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            pos += len(line)
            continue
        if not in_fence and pattern.match(line):
            found_start = pos + len(line)  # body starts AFTER heading line
            ls = line.lstrip()
            found_depth = len(ls) - len(ls.lstrip("#"))
            pos += len(line)
            break
        pos += len(line)
    if found_start < 0:
        raise AssertionError(f"heading not found: {heading_re!r}")

    # Second pass: from found_start, find the next equivalent-or-shallower heading
    in_fence = False
    pos2 = found_start
    end = len(text)
    for line in text[found_start:].splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            pos2 += len(line)
            continue
        if not in_fence:
            ls = line.lstrip()
            n_hash = len(ls) - len(ls.lstrip("#"))
            if 1 <= n_hash <= found_depth and ls[n_hash:n_hash + 1] == " ":
                end = pos2
                break
        pos2 += len(line)
    return text[found_start:end]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def skill_md() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def design_testing_md() -> str:
    return DESIGN_TESTING_MD.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Phase Matrix
# ---------------------------------------------------------------------------


def test_phase_matrix_has_e2e_verification_row(skill_md: str):
    """Anchor on the Phase Matrix table heading (Section 6) and verify the
    renamed row is present with the exact column semantics."""
    section = _section(skill_md, r"^## 6\. Phase Matrix by Complexity")
    rows = [
        line for line in section.splitlines()
        if line.startswith("| ") and "E2E" in line and "Verification" in line
    ]
    assert rows, "no 'E2E Verification' row in Phase Matrix (Section 6)"
    assert len(rows) == 1, f"expected exactly one row, got: {rows}"
    row = rows[0]
    # Column semantics: trivial | small | medium | large
    assert "if feature+UI" in row, row
    assert "touches_io_boundary" in row, (
        f"small column should mention touches_io_boundary safety floor: {row}"
    )
    assert "always" in row, f"medium column must say 'always': {row}"


def test_phase_matrix_does_not_use_legacy_e2e_update_label(skill_md: str):
    """The pre-F0.5 row was named 'E2E Update' — stale spelling regression
    risk. Failing this test means someone reverted the F0.5 rename."""
    section = _section(skill_md, r"^## 6\. Phase Matrix by Complexity")
    legacy_rows = [
        line for line in section.splitlines()
        if line.startswith("| E2E Update")
    ]
    assert not legacy_rows, (
        f"legacy 'E2E Update' row resurfaced; F0.5 rename regressed: {legacy_rows}"
    )


# ---------------------------------------------------------------------------
# F0.5 section
# ---------------------------------------------------------------------------


def test_f05_section_exists_with_medium_plus_mandate(skill_md: str):
    """F0.5 must exist as its own ### section under Finalization, with the
    'Mandatory at medium+' anchor phrase."""
    f05_body = _section(skill_md, r"^### F0\.5: End-to-End Verification Gate")
    assert "Mandatory at medium\\+" in f05_body or "Mandatory at medium+" in f05_body, (
        "F0.5 must declare itself Mandatory at medium+"
    )
    # The four fail-closed conditions are the contract enforced by both the
    # production-time orchestrator and the post-commit audit. All four must
    # be enumerated in the prose so a reader can match them against the
    # implementation.
    for keyword in ("tests_run", "exit_code", "justification", "surface"):
        assert keyword in f05_body, (
            f"F0.5 section is missing fail-closed keyword: {keyword!r}"
        )


def test_f05_references_orchestrator_and_audit(skill_md: str):
    """F0.5 prose must point at both layers (production-time + post-commit)
    so a future reader can locate the implementation. Anchored on F0.5,
    not the whole file — keyword-anchor anti-pattern from ADR-025."""
    f05_body = _section(skill_md, r"^### F0\.5: End-to-End Verification Gate")
    assert "surface_verification.py" in f05_body, (
        "F0.5 must point at the orchestrator (production-time chokepoint)"
    )
    assert "verify_iterate_finalization.py" in f05_body, (
        "F0.5 must point at the post-commit audit"
    )


# ---------------------------------------------------------------------------
# design-and-testing.md
# ---------------------------------------------------------------------------


def test_design_testing_has_authoring_section(design_testing_md: str):
    """Authoring (Step 11a) must exist with the 'Medium+ always' anchor."""
    section = _section(design_testing_md, r"^## End-to-End Verification — Authoring")
    assert "Medium+ always" in section or "Medium+ always (no skip)" in section, (
        "Authoring section must say 'Medium+ always'"
    )


def test_design_testing_has_execution_section(design_testing_md: str):
    """Execution (Step 11b) must exist with 'Always at medium+'."""
    section = _section(design_testing_md, r"^## End-to-End Verification — Execution")
    assert "Always at medium\\+" in section or "Always at medium+" in section, (
        "Execution section must say 'Always at medium+'"
    )
    # Each per-surface runner must be documented so the orchestrator's
    # surface taxonomy stays exhaustive.
    for surface in ("Web", "CLI", "API", "None"):
        assert surface in section, (
            f"Execution section missing per-surface runner: {surface}"
        )


def test_design_testing_browser_verify_marked_early_signal(design_testing_md: str):
    """Browser Verify section must carry the early-signal banner so readers
    don't take it as the authoritative gate at medium+."""
    section = _section(design_testing_md, r"^## Browser Verify")
    assert "Early-signal" in section or "early-signal" in section.lower(), (
        "Browser Verify must be marked early-signal at medium+"
    )
    assert "F0.5" in section, "Browser Verify banner must point at F0.5"


def test_design_testing_smoke_marked_legacy(design_testing_md: str):
    """Smoke Test section must say it does NOT satisfy the F0.5 gate."""
    section = _section(design_testing_md, r"^## Smoke Test")
    assert "Legacy" in section or "F0.5" in section, (
        "Smoke Test must be marked legacy / not-F0.5-satisfying"
    )


# ---------------------------------------------------------------------------
# Cross-document consistency
# ---------------------------------------------------------------------------


def test_phase_matrix_mentions_io_boundary_for_small(skill_md: str):
    """Plan A.1 specifies small column = 'if feature+UI or touches_io_boundary'.
    The taxonomy and prose disagreed in earlier drafts — this test pins both
    sides on the same flag name."""
    section = _section(skill_md, r"^## 6\. Phase Matrix by Complexity")
    e2e_row = [
        line for line in section.splitlines()
        if line.startswith("| ") and "E2E Verification" in line
    ][0]
    assert "touches_io_boundary" in e2e_row, e2e_row


def test_skill_md_step_11_split_into_a_and_b(skill_md: str):
    """Step 11 must be split into 11a (Author) + 11b (Execute) — the
    spec-only-authorship-is-not-a-test rule depends on this split."""
    assert "### Step 11a:" in skill_md, "Step 11a (Author E2E Spec) missing"
    assert "### Step 11b:" in skill_md, "Step 11b (Execute E2E Spec) missing"
    # No legacy "### Step 11: E2E Update" should remain
    assert "### Step 11: E2E Update" not in skill_md, (
        "legacy Step 11 (E2E Update) resurfaced; F0.5 split regressed"
    )


def test_f_step_ordering_invariant_names_f05(skill_md: str):
    """The 'Order matters' callout under Finalization must enumerate F0.5
    so a reader can't miss it when sequencing F-steps."""
    section = _section(skill_md, r"^## Finalization")
    # The invariant is in the first 2000 chars of the Finalization section
    head = section[:3000]
    assert "F0.5" in head, "Finalization 'Order matters' invariant must name F0.5"


# ---------------------------------------------------------------------------
# Backend-affects-Frontend rule (plan §V.4)
# ---------------------------------------------------------------------------


def test_skill_md_documents_backend_affects_frontend_rule(skill_md: str):
    """SKILL.md F0.5 section must document the Backend-affects-Frontend rule
    so a reader of the iterate skill at medium+ knows that a server-only
    diff still triggers surface=web. The rule's existence is the only
    enforcement at the prose level — the matrix=`always` cell subsumes
    file-path detection."""
    f05_body = _section(skill_md, r"^### F0\.5: End-to-End Verification Gate")
    assert "Backend-affects-Frontend" in f05_body, (
        "F0.5 section must document the Backend-affects-Frontend rule "
        "(server-only diff → surface=web at medium+)"
    )


def test_hooks_and_pipeline_md_explains_file_path_agnostic(monkeypatch=None):
    """docs/hooks-and-pipeline.md must document why file-path-agnostic at
    medium+ is the correct semantics — otherwise a future reader will
    think detect_frontend_changes.py should also gate F0.5."""
    hooks_doc = REPO_ROOT / "docs" / "hooks-and-pipeline.md"
    text = hooks_doc.read_text(encoding="utf-8")
    # The rename from "Browser Verify Gate Semantics" → "Browser Verify +
    # End-to-End Verification Gate Semantics" was Unit F of the previous
    # iterate; this anchors that section name.
    assert "End-to-End Verification Gate Semantics" in text, (
        "docs/hooks-and-pipeline.md must contain the renamed section "
        "'Browser Verify + End-to-End Verification Gate Semantics'"
    )
    assert "file-path-agnostic" in text, (
        "docs/hooks-and-pipeline.md must explain that F0.5 at medium+ is "
        "file-path-agnostic — otherwise the semantics drift back toward "
        "detect_frontend_changes.py-only gating"
    )


def test_conventions_md_carries_e2e_learning():
    """The 'End-to-End Verification: spec-only authorship counts as no test'
    Learning bullet must stay in conventions.md so the rule survives across
    iterate runs (it's the most important behavioral lesson from the
    2026-04 webui regression)."""
    conv = REPO_ROOT / ".shipwright" / "agent_docs" / "conventions.md"
    text = conv.read_text(encoding="utf-8")
    assert "spec-only authorship counts as no test" in text, (
        "conventions.md Learnings must keep the F0.5 rule"
    )
    assert "Backend-affects-Frontend" in text, (
        "conventions.md Learnings must keep the Backend-affects-Frontend rule"
    )
