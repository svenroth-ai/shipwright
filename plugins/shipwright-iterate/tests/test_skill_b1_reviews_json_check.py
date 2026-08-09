"""Drift-protection for B1's direct reviews.json read
(iterate-2026-08-09-compaction-state-audit).

Root cause: B1's replay-check consulted only two markers (the external-review
marker and an ADR `Self-Review:` block) even though the fuller per-review-type
record (`reviews.json`) already existed on disk — a mid-cascade interruption
(e.g. stopped after `spec-reviewer` passed but before `code-reviewer` ran) was
invisible to a resume. The fix adds a third, canonical replay-check that reads
`reviews.json` directly via `record_review_pass.py show`.

This is a documentation-presence test only — it proves the instruction exists
in B1's body, not that a future agent follows it (that half is behavioral,
covered by `write-review-payload-on-stop.py`'s salvage-path tests and the
handoff renderer tests, which drive the actual reviews.json read).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_MD = REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate" / "SKILL.md"


def _extract_b1_body(text: str) -> str:
    pattern = re.compile(r"^### B1\. Resumable Iterate Run.*?(?=\n### )",
                         flags=re.MULTILINE | re.DOTALL)
    match = pattern.search(text)
    return match.group(0) if match else ""


def test_b1_heading_present() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")
    assert _extract_b1_body(text), (
        "Could not extract '### B1. Resumable Iterate Run' body from SKILL.md."
    )


def test_b1_names_the_direct_reviews_json_read() -> None:
    text = SKILL_MD.read_text(encoding="utf-8")
    body = _extract_b1_body(text)
    assert "record_review_pass.py" in body and "show" in body, (
        "B1 must name the canonical reviews.json read path "
        "(`record_review_pass.py show`) — do not leave resume to a "
        "hand-rolled file read."
    )
    assert "reviews" in body and "object" in body, (
        "B1 must describe reading the record's `reviews` object, not just "
        "invoking the CLI without saying what to look at."
    )


def test_b1_gates_on_self_before_treating_pending_as_interrupted() -> None:
    """Pins the false-positive fix from external review (Branch A, openai
    finding #1): a freshly-init'd record has every type pending, which must
    NOT be read as "the cascade was interrupted"."""
    text = SKILL_MD.read_text(encoding="utf-8")
    body = _extract_b1_body(text)
    assert "self" in body.lower() and "terminal" in body.lower(), (
        "B1's reviews.json replay-check must gate on `self` being terminal "
        "before treating any other pending type as an interrupted cascade — "
        "otherwise a freshly-init'd (all-pending) record false-triggers an "
        "unnecessary Step 8 restart."
    )


def test_b1_does_not_rely_on_session_handoff_for_this_check() -> None:
    """Pins the Internal Plan Review HIGH finding: the auto-generated
    session_handoff.md is gitignored/runtime-only and a killed-mid-phase run
    never gets it regenerated — it cannot be the authoritative signal for
    this specific check."""
    text = SKILL_MD.read_text(encoding="utf-8")
    body = _extract_b1_body(text)
    assert "do not hand-read" in body.lower() or "not the" in body.lower(), (
        "B1 must call out reviews.json as the canonical source for the "
        "review-cascade replay-check, not session_handoff.md's best-effort "
        "snapshot."
    )
