"""One authority for "is this review clear to proceed past?".

Before this, the marker carried a status and a finding count, and three
different readers each decided for themselves what a passing review looked
like. These tests pin the shared evaluator and the ``mark-review-state.py``
CLI that writes what it reads; ``test_verifiers_plan_w5.py`` pins the W5
consumer. In particular: a disagreement nobody decided blocks — including the
case where a verdict could not be read, which must not pass as agreement — and
the reader DERIVES that from the verdicts rather than trusting the marker's
own summary of them.
"""

import json
import subprocess
import sys
from pathlib import Path

from lib.review_marker import (
    STATE_BLOCK,
    STATE_LEGACY,
    STATE_OK,
    evaluate_review_state,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MARK_SCRIPT = _REPO_ROOT / "shared" / "scripts" / "checks" / "mark-review-state.py"


def _run_mark(planning_dir: Path, *args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(_MARK_SCRIPT), "--planning-dir", str(planning_dir), *args],
        capture_output=True, text=True, encoding="utf-8",
    )
    try:
        return proc.returncode, json.loads(proc.stdout)
    except json.JSONDecodeError:  # pragma: no cover - diagnostic path
        raise AssertionError(f"non-JSON stdout: {proc.stdout!r} / {proc.stderr!r}")


# ---------------------------------------------------------------------------
# evaluate_review_state
# ---------------------------------------------------------------------------


CONTRADICTING = {"gemini": "approve", "openai": "reject"}


def test_absent_marker_blocks():
    state, reason = evaluate_review_state(None)
    assert state == STATE_BLOCK
    assert "did not run" in reason


def test_unknown_status_blocks():
    assert evaluate_review_state({"status": "probably-fine"})[0] == STATE_BLOCK


def test_skip_without_justification_blocks():
    state, reason = evaluate_review_state({"status": "skipped_user_opt_out", "reason": "  "})
    assert state == STATE_BLOCK
    assert "justification" in reason


def test_skip_with_justification_passes():
    """A skipped review has no reviewers, so it has no verdicts to weigh."""
    state, _ = evaluate_review_state(
        {"status": "skipped_user_opt_out", "reason": "offline demo"}
    )
    assert state == STATE_OK


def test_agreeing_verdicts_pass():
    state, _ = evaluate_review_state({
        "status": "completed", "verdicts": {"gemini": "approve", "openai": "revise"},
    })
    assert state == STATE_OK


def test_unresolved_contradiction_blocks():
    state, reason = evaluate_review_state({"status": "completed", "verdicts": CONTRADICTING})
    assert state == STATE_BLOCK
    assert "unresolved reviewer disagreement" in reason


def test_recorded_resolution_clears_the_block():
    state, _ = evaluate_review_state({
        "status": "completed", "verdicts": CONTRADICTING,
        "contradiction_resolution": "took the reject; reworked the section split",
    })
    assert state == STATE_OK


def test_whitespace_is_not_a_resolution():
    state, _ = evaluate_review_state({
        "status": "completed", "verdicts": CONTRADICTING,
        "contradiction_resolution": "   ",
    })
    assert state == STATE_BLOCK


def test_the_disagreement_is_recomputed_not_trusted():
    """A marker whose stored block disagrees with its own verdicts must not
    walk through. The reader derives it, exactly as the writer did."""
    hand_edited_away = {
        "status": "completed", "verdicts": CONTRADICTING, "contradiction": None,
    }
    assert evaluate_review_state(hand_edited_away)[0] == STATE_BLOCK

    claims_agreement = {
        "status": "completed", "verdicts": CONTRADICTING,
        "contradiction": {"requires_resolution": False, "reason": "all fine, honest"},
    }
    assert evaluate_review_state(claims_agreement)[0] == STATE_BLOCK


def test_a_stored_contradiction_cannot_invent_one_either():
    state, _ = evaluate_review_state({
        "status": "completed",
        "verdicts": {"gemini": "approve", "openai": "approve"},
        "contradiction": {"requires_resolution": True, "reason": "fabricated"},
    })
    assert state == STATE_OK


def test_an_incomplete_verdict_pair_blocks():
    """Two reviewers always run; one recorded verdict is a malformed record,
    not one reviewer agreeing."""
    state, reason = evaluate_review_state({
        "status": "completed", "verdicts": {"gemini": "approve"},
    })
    assert state == STATE_BLOCK
    assert "historical gemini/openai" in reason


def test_verdicts_from_reviewers_that_never_ran_do_not_satisfy_the_gate():
    """Otherwise two invented reviewer names would clear it without either
    real reviewer having spoken."""
    state, _ = evaluate_review_state({
        "status": "completed", "verdicts": {"foo": "approve", "bar": "approve"},
    })
    assert state == STATE_BLOCK


def test_an_unreadable_verdict_blocks():
    state, _ = evaluate_review_state({
        "status": "completed", "verdicts": {"gemini": "approve", "openai": "unknown"},
    })
    assert state == STATE_BLOCK


def test_one_silent_reviewer_blocks_until_decided():
    """One reviewer approving is not the guarantee two reviewers give."""
    marker = {
        "status": "completed", "verdicts": {"gemini": "approve", "openai": "unavailable"},
    }
    state, reason = evaluate_review_state(marker)
    assert state == STATE_BLOCK
    assert "only one reviewer answered" in reason

    marker["contradiction_resolution"] = "openai rate-limited; proceeded on gemini alone"
    assert evaluate_review_state(marker)[0] == STATE_OK


def test_a_completed_review_where_neither_reviewer_answered_blocks():
    """It needs no operator resolution — the degraded-review gate owns that —
    but it must not read as reviewed either, or two `unavailable` verdicts
    would clear every gate with nobody having reviewed anything."""
    state, reason = evaluate_review_state({
        "status": "completed",
        "verdicts": {"gemini": "unavailable", "openai": "unavailable"},
    })
    assert state == STATE_BLOCK
    assert "neither reviewer answered" in reason


def test_neither_answering_still_asks_for_no_resolution():
    # The remedy is re-run or record a skip, not "say which side you took".
    from lib.review_verdict import contradiction_block
    assert contradiction_block({"gemini": "unavailable", "openai": "unavailable"})["requires_resolution"] is False


def test_a_completed_review_with_no_verdicts_is_legacy_not_ok():
    """Ambiguous by construction: either the marker predates verdicts, or this
    run omitted --verdict. The two callers resolve it differently, so the
    shared evaluator refuses to decide for them."""
    state, reason = evaluate_review_state({
        "status": "completed", "provider": "openrouter", "findings_count": 5,
    })
    assert state == STATE_LEGACY
    assert "no reviewer verdicts" in reason


# ---------------------------------------------------------------------------
# mark-review-state.py — the contradiction is derived, never asserted
# ---------------------------------------------------------------------------


def test_verdicts_round_trip_through_the_marker(tmp_path):
    code, out = _run_mark(
        tmp_path, "--status", "completed", "--provider", "openrouter",
        "--verdict", "deepseek=approve", "--verdict", "openai=reject",
    )
    assert code == 0
    state = out["state"]
    assert state["verdicts"] == {"deepseek": "approve", "openai": "reject"}
    assert state["contradiction"]["detected"] is True
    assert state["contradiction"]["requires_resolution"] is True
    assert state["marker_schema"] == 3
    # …and the written file says the same thing.
    written = json.loads(Path(out["marker_path"]).read_text(encoding="utf-8"))
    assert written["contradiction"] == state["contradiction"]


def test_a_written_contradiction_blocks_the_gate(tmp_path):
    _run_mark(
        tmp_path, "--status", "completed",
        "--verdict", "deepseek=approve", "--verdict", "openai=reject",
    )
    marker = json.loads((tmp_path / "external_review_state.json").read_text(encoding="utf-8"))
    assert evaluate_review_state(marker)[0] == STATE_BLOCK


def test_resolution_passed_on_the_cli_clears_it(tmp_path):
    _run_mark(
        tmp_path, "--status", "completed",
        "--verdict", "deepseek=approve", "--verdict", "openai=reject",
        "--contradiction-resolution", "kept the plan; openai misread the split boundary",
    )
    marker = json.loads((tmp_path / "external_review_state.json").read_text(encoding="utf-8"))
    assert evaluate_review_state(marker)[0] == STATE_OK


def test_agreeing_verdicts_need_no_resolution(tmp_path):
    _run_mark(
        tmp_path, "--status", "completed",
        "--verdict", "deepseek=approve", "--verdict", "openai=revise",
    )
    marker = json.loads((tmp_path / "external_review_state.json").read_text(encoding="utf-8"))
    assert marker["contradiction"]["requires_resolution"] is False
    assert evaluate_review_state(marker)[0] == STATE_OK


def test_an_unreadable_verdict_requires_a_decision(tmp_path):
    _run_mark(
        tmp_path, "--status", "completed",
        "--verdict", "deepseek=approve", "--verdict", "openai=unknown",
    )
    marker = json.loads((tmp_path / "external_review_state.json").read_text(encoding="utf-8"))
    assert marker["contradiction"]["requires_resolution"] is True


def test_one_silent_reviewer_requires_a_decision(tmp_path):
    _run_mark(
        tmp_path, "--status", "completed",
        "--verdict", "deepseek=approve", "--verdict", "openai=unavailable",
    )
    marker = json.loads((tmp_path / "external_review_state.json").read_text(encoding="utf-8"))
    assert marker["contradiction"]["requires_resolution"] is True


def test_an_unknown_reviewer_name_is_rejected(tmp_path):
    code, out = _run_mark(tmp_path, "--status", "completed", "--verdict", "claude=approve")
    assert code == 2
    assert out["error"] == "invalid_verdict"


def test_the_same_reviewer_twice_is_rejected_not_overwritten(tmp_path):
    code, out = _run_mark(
        tmp_path, "--status", "completed",
        "--verdict", "deepseek=reject", "--verdict", "deepseek=approve",
    )
    assert code == 2
    assert "twice" in out["message"]


def test_a_bad_verdict_word_is_rejected_not_coerced(tmp_path):
    code, out = _run_mark(
        tmp_path, "--status", "completed", "--verdict", "deepseek=looks-good",
    )
    assert code == 2
    assert out["error"] == "invalid_verdict"


def test_malformed_verdict_pair_is_rejected(tmp_path):
    code, out = _run_mark(tmp_path, "--status", "completed", "--verdict", "deepseek")
    assert code == 2
    assert out["error"] == "invalid_verdict"


def test_omitting_the_verdict_flags_is_legacy_not_a_pass(tmp_path):
    """The flags are optional at the CLI so the skip branches still work, but
    a *completed* review that recorded none cannot be read as clear —
    otherwise the whole disagreement check is opt-out by omission."""
    code, out = _run_mark(tmp_path, "--status", "completed", "--provider", "openrouter")
    assert code == 0
    assert out["state"]["verdicts"] is None
    assert out["state"]["contradiction"] is None
    assert evaluate_review_state(out["state"])[0] == STATE_LEGACY


def test_a_skip_needs_no_verdicts(tmp_path):
    code, out = _run_mark(
        tmp_path, "--status", "skipped_user_opt_out", "--reason", "offline demo",
    )
    assert code == 0
    assert evaluate_review_state(out["state"])[0] == STATE_OK
