"""Drift-protection for `path-a-feature.md`'s Step 2 Spec-Impact classification
rule (FR-01.11/AC05, AC06).

Both ACs describe agent-judgment steps with no deterministic script behind
them (the classification happens while an agent edits `spec.md` by hand) —
this is the SAME idiom already used repo-wide for governance/prose ACs in
this plugin (`test_f11_automerge_arm.py`, `test_f11_delivery_watch.py`,
`test_skill_completeness_matrix.py`): pin the prose that drives the agent's
behavior, anchored on a heading first so wording tweaks elsewhere in the
document cannot silently satisfy the probe.

AC05 — MINT-vs-FOLD gate: a change that completes/polishes/fixes/extends an
existing capability is routed to MODIFYING that requirement's criteria
rather than adding a new requirement.

AC06 — deterministic FR numbering: a new FR takes the next free number in
its split, counting both live and retired (`### Removed Requirements`) rows,
never guessed, never reused. The negative-space enforcement half (a
duplicate/reused id is actually caught) lives at
`shared/tests/test_check_fr_hygiene_doubt3.py::test_a_new_duplicate_id_at_head_is_flagged`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PATH_A_FEATURE = (
    REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate"
    / "references" / "path-a-feature.md"
)


def _extract_step_2_body(text: str) -> str:
    pattern = re.compile(
        r"^## Step 2: Spec Update.*?(?=\n## )",
        flags=re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(0) if match else ""


def test_step_2_heading_present() -> None:
    text = PATH_A_FEATURE.read_text(encoding="utf-8")
    assert _extract_step_2_body(text), (
        "Could not extract '## Step 2: Spec Update' body from "
        "path-a-feature.md — probe regex may need updating."
    )


@pytest.mark.covers("FR-01.11/AC05")
def test_fold_routes_a_completed_or_extended_capability_to_modify() -> None:
    """AC05: a change that completes, polishes, fixes or extends a capability
    that already has a requirement is routed to MODIFYING that requirement's
    criteria rather than to adding a new requirement.

    All four trigger terms and the no-new-row outcome must be asserted on the
    FOLD bullet itself (not merely present anywhere in Step 2) — a review
    finding on PR #730 noted the prior version only checked two of the four
    terms and never asserted the "don't add a new requirement" outcome, so a
    materially broken rule (e.g. one that dropped 'polishes'/'fixes' or that
    quietly started adding a row) could still pass.
    """
    text = PATH_A_FEATURE.read_text(encoding="utf-8")
    body = _extract_step_2_body(text)
    assert "FOLD" in body and "MODIFY" in body, (
        "Step 2 must state the FOLD -> MODIFY rule."
    )
    # Capture the whole FOLD bullet, not just its first physical line — the
    # source hard-wraps it across three lines before the next "- **MINT"
    # bullet starts.
    fold_pos = body.index("**FOLD")
    mint_pos = body.index("**MINT", fold_pos)
    fold_block = body[fold_pos:mint_pos]
    fold_lowered = fold_block.lower()
    assert "MODIFY" in fold_block, (
        "the FOLD bullet must itself say MODIFY, not merely mention it "
        "somewhere in the section."
    )
    for trigger in ("completes", "polishes", "fixes", "extends"):
        assert trigger in fold_lowered, (
            f"the FOLD bullet must name '{trigger}' as a FOLD trigger — "
            "AC05 requires all four (completes/polishes/fixes/extends), "
            "not just a subset."
        )
    assert "do not add a row" in fold_lowered, (
        "the FOLD bullet must explicitly forbid adding a new row — "
        "otherwise a broken rule could route a FOLD case to ADD anyway."
    )
    assert "append acceptance-criteria lines to the existing fr" in (
        fold_lowered
    ), (
        "the FOLD bullet must direct the agent to extend the EXISTING "
        "requirement's criteria, not create a new one."
    )


@pytest.mark.covers("FR-01.11/AC06")
def test_new_fr_numbering_is_deterministic_and_never_reuses_retired_ids() -> None:
    """AC06: a new requirement's number is the next free number in its
    group, counted over live AND retired requirements alike, so a retired
    number is never reused and the number is never guessed.

    This is a prose probe only — numbering happens while an agent edits
    spec.md by hand (module docstring above), so there is no deterministic
    script that actually COMPUTES the next free number or counts retired
    rows for this probe to call. It pins the wording that drives that
    manual computation; it does not exercise the computation itself. The
    negative-space half (a duplicate/reused id being caught after the fact)
    is a real deterministic seam and lives at
    `shared/tests/test_check_fr_hygiene_doubt3.py::test_a_new_duplicate_id_at_head_is_flagged`.
    """
    text = PATH_A_FEATURE.read_text(encoding="utf-8")
    body = _extract_step_2_body(text)
    # `\s+` (not a literal space) because the source hard-wraps the phrase
    # across two lines ("next free\n       number in its split").
    assert re.search(r"next free\s+number", body, flags=re.IGNORECASE), (
        "Step 2 must state the 'next free number' numbering rule."
    )
    assert "Removed Requirements" in body, (
        "Step 2 must count retired rows (### Removed Requirements) toward "
        "the next-free-number computation, or a retired id could be reused."
    )
    assert "never guess a number" in body.lower(), (
        "Step 2 must forbid guessing the number outright."
    )
