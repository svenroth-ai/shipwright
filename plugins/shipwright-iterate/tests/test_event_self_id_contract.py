"""Drift-protection tests for the S1 event self-identification contract.

Campaign 2026-06-07-tracked-campaign-status, sub-iterate S1: campaign
sub-iterates must stamp ``campaign`` + ``sub_iterate_id`` into their
``work_completed`` event via the F5b ``--event-extras-json`` hook, and
the manual ``/shipwright-iterate --campaign <slug> --sub-iterate-id <id>``
path must do the same. These tests parse the contract markdowns (runner
agent, SKILL.md, F5b reference) and pin the wording — the same pattern as
``test_sub_iterate_runner_contract.py`` (which is baseline-frozen, hence
the separate file).
"""

from __future__ import annotations

from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
RUNNER_DOC = PLUGIN_ROOT / "agents" / "sub-iterate-runner.md"
SKILL_DOC = PLUGIN_ROOT / "skills" / "iterate" / "SKILL.md"
F5B_DOC = PLUGIN_ROOT / "skills" / "iterate" / "references" / "F5b.md"
CAMPAIGN_DOC = (
    PLUGIN_ROOT / "skills" / "iterate" / "references" / "campaign-mode.md"
)


def _runner() -> str:
    return RUNNER_DOC.read_text(encoding="utf-8")


def _runner_step_4() -> str:
    """The Step 4 (Finalization) section body — scoped so a match in the
    result-JSON examples can't satisfy a Step-4 pin."""
    text = _runner()
    start = text.index("### Step 4")
    end = text.index("### Step 5", start)
    return text[start:end]


# ---------------------------------------------------------------------------
# Runner contract: Step 4 finalize call carries the stamp
# ---------------------------------------------------------------------------


def test_runner_step_4_uses_finalize_iterate():
    text = _runner_step_4()
    assert "finalize_iterate.py" in text, (
        "Step 4 must record the work_completed event via finalize_iterate.py "
        "(F5b model) — bare record_event.py drifted from the per-tree, "
        "PR-committed event flow."
    )


def test_runner_step_4_passes_event_extras_json():
    assert "--event-extras-json" in _runner_step_4(), (
        "Step 4's finalize call must pass --event-extras-json so the event "
        "is classified AND campaign-stamped at recording time."
    )


def test_runner_step_4_stamps_campaign_key():
    text = _runner_step_4()
    assert '"campaign"' in text, (
        'Step 4 must stamp "campaign" into the event extras (S1: events.jsonl '
        "self-sufficiency for per-sub status projection)."
    )


def test_runner_step_4_stamps_sub_iterate_id_key():
    text = _runner_step_4()
    assert '"sub_iterate_id"' in text, (
        'Step 4 must stamp "sub_iterate_id" into the event extras (S1).'
    )


def test_runner_no_longer_records_via_bare_record_event():
    text = _runner()
    assert "- **F7:** Record event (`record_event.py`)" not in text, (
        "Legacy F7 record_event.py bullet must be replaced by the F5b "
        "finalize_iterate.py call (event recording + extras in one step)."
    )


# ---------------------------------------------------------------------------
# SKILL.md: manual --campaign / --sub-iterate-id flag path
# ---------------------------------------------------------------------------


def test_skill_documents_manual_campaign_flag():
    text = SKILL_DOC.read_text(encoding="utf-8")
    assert "--campaign" in text, (
        "SKILL.md must document the manual --campaign <slug> flag so a "
        "hand-run sub-iterate stamps its event."
    )


def test_skill_documents_manual_sub_iterate_id_flag():
    text = SKILL_DOC.read_text(encoding="utf-8")
    assert "--sub-iterate-id" in text, (
        "SKILL.md must document the manual --sub-iterate-id <id> flag so a "
        "hand-run sub-iterate stamps its event."
    )


def test_skill_manual_flags_route_to_f5b_extras():
    """The flag documentation must tie the flags to the F5b extras stamp —
    naming both event keys — so the manual path is actionable, not
    decorative."""
    text = SKILL_DOC.read_text(encoding="utf-8")
    assert "sub_iterate_id" in text and '"campaign"' in text, (
        "SKILL.md must state that --campaign/--sub-iterate-id land as the "
        '"campaign" + "sub_iterate_id" keys in the F5b --event-extras-json.'
    )


# ---------------------------------------------------------------------------
# F5b reference: stamp keys documented at the producer
# ---------------------------------------------------------------------------


def test_f5b_reference_documents_stamp_keys():
    text = F5B_DOC.read_text(encoding="utf-8")
    assert "campaign" in text and "sub_iterate_id" in text, (
        "references/F5b.md must document the optional campaign + "
        "sub_iterate_id extras keys (producer-side contract)."
    )


# ---------------------------------------------------------------------------
# Campaign-mode reference: briefing includes the stamp values
# ---------------------------------------------------------------------------


def test_campaign_mode_briefing_mentions_stamp():
    text = CAMPAIGN_DOC.read_text(encoding="utf-8").lower()
    assert "stamp" in text and "work_completed" in text, (
        "references/campaign-mode.md must remind the orchestrator that the "
        "runner brief carries campaign slug + sub_iterate_id and the runner "
        "STAMPS them into the work_completed event (S1)."
    )
