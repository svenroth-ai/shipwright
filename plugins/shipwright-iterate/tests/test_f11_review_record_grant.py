"""Drift-protection for F11's standing-grant branch in `check_review_record`.

`SKILL.md` Step 8 and `iteration-reviews.md` step 0 each got a guard when the
`CLAUDE.md` standing request shipped (iterate-2026-07-28-review-subagents-
standing-request). F11 carries the same rule at closing time — it is the phase
where every observed lapse of the `code` pass was actually decided — and it was
the only one of the three left unpinned.

What these pin, and why each would be a real regression:

1. F11 states the grant branch: a `code` row outstanding because of a session
   policy, in a project whose `CLAUDE.md` grants review subagents, was never
   gated at all. Lose this and F11 sends the run back to ASK, which is the
   contradiction the grant exists to remove.
2. The four blockers are explicitly unaffected by any grant. Lose this and the
   grant reads as overriding a genuinely absent `Agent` tool — a campaign
   sub-iterate-runner would be told to spawn what it cannot spawn.
3. The ask survives for the ungranted project. Deleting it rather than scoping
   it would let a project without the grant close `code` silently.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
F11_MD = (
    REPO_ROOT
    / "plugins"
    / "shipwright-iterate"
    / "skills"
    / "iterate"
    / "references"
    / "F11.md"
)


def _norm(text: str) -> str:
    """Normalise markdown so wording is asserted, not layout.

    Same shape as the sibling prose guards in `shared/tests` — em-dashes and
    emphasis markers are stripped so a reflow cannot turn a live assertion into
    one that can never match.
    """
    text = text.replace("—", "-").replace("’", "'").replace("§", "")
    text = re.sub(r"[*`]+", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _review_record_paragraph() -> str:
    """The `check_review_record` paragraph, normalised."""
    body = F11_MD.read_text(encoding="utf-8")
    start = body.index("check_review_record")
    rest = body[start:]
    end = rest.find("\nIt also includes")
    return _norm(rest if end < 0 else rest[:end])


def test_f11_defers_to_a_standing_grant_instead_of_asking() -> None:
    """Step 8 spawns under the grant; F11 must not send the run back to ask."""
    body = _review_record_paragraph()
    assert "grants review subagents standingly" in body, (
        "F11 must name the CLAUDE.md standing grant — otherwise the phase that "
        "decided every observed lapse still routes through the ask that the "
        "grant removed."
    )
    assert "there was never anything to ask - spawn them" in body, (
        "F11 must state the consequence of the grant, not merely mention it: "
        "a policy-gated `code` row in a granted project is not an outstanding "
        "question, it is a cascade that should have run."
    )


def test_the_four_blockers_are_immune_to_the_grant() -> None:
    """A grant is permission, not capability. The runner still has no `Agent`."""
    body = _review_record_paragraph()
    assert "unaffected by any grant" in body, (
        "F11 must state that the four blockers survive the grant — a grant "
        "that appeared to override them would tell a sub-iterate-runner to "
        "spawn a subagent it does not have the tool for."
    )
    assert "still cannot spawn" in body, (
        "…and name the capability case concretely, so the rule is applied "
        "rather than recited."
    )


def test_the_ask_survives_for_a_project_without_the_grant() -> None:
    """Scoped, not deleted — repos adopted before the section shipped, and any
    project that deleted it, still need the ask rather than a silent close."""
    body = _review_record_paragraph()
    assert "otherwise, if the only obstacle is a session policy, ask the operator now" in body, (
        "the ask must remain reachable for an ungranted project"
    )
    assert "not one of the four blockers" in body, (
        "and must still refuse to treat a conditional session policy as a "
        "blocker that licenses closing the row"
    )


def test_close_missing_is_still_not_a_route_for_an_unasked_cascade() -> None:
    """The grant branch was inserted next to this line; it must not have
    displaced it. `close-missing` is for a run predating the record only."""
    body = _review_record_paragraph()
    assert "close-missing is for a run that predates the record - not for a cascade that was never asked about" in body, (
        "F11 must keep refusing close-missing as an escape hatch for a "
        "cascade that simply did not run"
    )
