"""``check-plan-gates.py --gate review``'s reviewer-failure / reviewer-identity
handling — split out of ``test_check_plan_gates.py`` (300-LOC guideline).

FR-01.03/AC19 — a reviewer that answered nothing (or was cut off mid-sentence)
is recorded as UNAVAILABLE, a failure with a reason, never silently counted as
a completed review; if NEITHER reviewer delivered, the step fails loudly
rather than passing.

FR-01.03/AC20 — reviewers are identified truthfully; a marker written under an
older roster (e.g. schema 3's deepseek/openai) remains readable as historical
evidence, and the CURRENT roster is never hidden behind a historical name.
"""

import json
import sys
from pathlib import Path

import pytest

from tests._check_plan_gates_support import _problems, run_gates

# `planning` fixture comes from conftest.py — no import needed, and importing
# it here would shadow the same-named test-function parameter (ruff F811).

# Derive the current/historical reviewer rosters from the production module
# itself rather than hardcoding them a second time here — a roster change
# (as already happened once: deepseek -> glm) would otherwise leave these
# pins asserting a stale contract while still passing (Stage-3 code review,
# low).
_SHARED_LIB = Path(__file__).resolve().parents[3] / "shared" / "scripts" / "lib"
if str(_SHARED_LIB) not in sys.path:
    sys.path.append(str(_SHARED_LIB))
from review_verdict import HISTORICAL_REVIEWER_PAIRS, REVIEWERS  # noqa: E402

_CURRENT_A, _CURRENT_B = REVIEWERS
_STALE_HISTORICAL_A, _STALE_HISTORICAL_B = HISTORICAL_REVIEWER_PAIRS[0]  # gemini/openai
_READABLE_HISTORICAL_A, _READABLE_HISTORICAL_B = HISTORICAL_REVIEWER_PAIRS[1]  # deepseek/openai


@pytest.mark.covers("FR-01.03/AC19")
def test_a_reviewer_that_never_answered_is_recorded_unavailable_not_reviewed(planning):
    """FR-01.03/AC19: a reviewer that answered nothing (or was cut off) is
    recorded as UNAVAILABLE — a failure with a reason — never silently
    counted as a completed review. One side failing still blocks Step 6
    until the operator records why proceeding on the other alone is fine."""
    (planning / "external_review_state.json").write_text(
        json.dumps({
            "status": "completed", "provider": "openrouter",
            "marker_schema": 4,
            "verdicts": {_CURRENT_A: "unavailable", _CURRENT_B: "approve"},
        }),
        encoding="utf-8",
    )
    code, out = run_gates(planning, "review")
    assert code == 1
    assert any(
        "only one reviewer answered" in p and _CURRENT_A in p for p in _problems(out, "review")
    )


@pytest.mark.covers("FR-01.03/AC19")
def test_neither_reviewer_answering_fails_loudly_not_a_pass(planning):
    """FR-01.03/AC19: if NEITHER reviewer delivered, the step fails loudly
    instead of quietly passing as reviewed."""
    (planning / "external_review_state.json").write_text(
        json.dumps({
            "status": "completed", "provider": "openrouter",
            "marker_schema": 4,
            "verdicts": {_CURRENT_A: "unavailable", _CURRENT_B: "unavailable"},
        }),
        encoding="utf-8",
    )
    code, out = run_gates(planning, "review")
    assert code == 1
    assert any("neither reviewer answered" in p for p in _problems(out, "review"))


@pytest.mark.covers("FR-01.03/AC20")
def test_a_historical_schema_marker_is_still_read_truthfully(planning):
    """FR-01.03/AC20: an older marker recorded under a prior reviewer roster
    (schema 3, deepseek/openai) remains readable as historical evidence — it
    is not rejected merely for predating the current glm/openai contract."""
    (planning / "external_review_state.json").write_text(
        json.dumps({
            "status": "completed", "provider": "openrouter",
            "marker_schema": 3,
            "verdicts": {
                _READABLE_HISTORICAL_A: "approve", _READABLE_HISTORICAL_B: "approve",
            },
        }),
        encoding="utf-8",
    )
    assert run_gates(planning, "review")[0] == 0


@pytest.mark.covers("FR-01.03/AC20")
def test_a_current_schema_marker_cannot_borrow_a_historical_reviewer_name(planning):
    """FR-01.03/AC20: the CURRENT roster (glm/openai) is never hidden behind
    a historical name — a schema-4 marker naming the old gemini/openai pair
    is a contract mismatch, not a quiet alias."""
    (planning / "external_review_state.json").write_text(
        json.dumps({
            "status": "completed", "provider": "openrouter",
            "marker_schema": 4,
            "verdicts": {
                _STALE_HISTORICAL_A: "approve", _STALE_HISTORICAL_B: "approve",
            },
        }),
        encoding="utf-8",
    )
    code, out = run_gates(planning, "review")
    assert code == 1
    assert any("does not match" in p for p in _problems(out, "review"))
