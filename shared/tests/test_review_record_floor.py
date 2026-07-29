"""The medium+ code-review floor — at least one review must actually have run.

Before this, ``check_review_record`` verified only that no review type was left
``pending``. All five could be ``not_run`` with dispositions and the gate
returned green, so a medium+ iterate could finish with no code review of any
kind. The record answered *"was it written down?"* when the question is *"did it
happen?"*.

**Measured before building.** Across the 27 review records in this repo at the
time of writing, 25 were medium+ and every one of them had at least one of
``code`` / ``external_code`` completed — so this floor fails nothing that has
already happened. It is a ratchet on future runs, not a retroactive verdict.
``test_historical_shapes_still_pass`` keeps that promise honest by replaying the
shapes actually observed.

The floor deliberately does not accept ``not_applicable``: if it did, the gate
would be satisfiable by re-labelling, which is the same
bookkeeping-instead-of-substance failure it exists to close.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.review_record_core import make_entry, new_record, upsert_review  # noqa: E402
from lib.review_record_schema import RECORDABLE_TYPES  # noqa: E402
from tools.verifiers.review_record_check import check_review_record  # noqa: E402


def _write_run(
    root: Path,
    run_id: str,
    *,
    complexity: str,
    statuses: dict[str, str],
) -> None:
    """Lay down an iterate entry (for complexity) plus a review record.

    Built through the real ``new_record``/``make_entry`` rather than a
    hand-written dict: a fixture shaped by hand is validated by nothing, and an
    invalid one makes the check fail for the wrong reason — which it did on the
    first run of these tests, turning three of them green by accident.
    """
    entries = root / ".shipwright" / "agent_docs" / "iterates"
    entries.mkdir(parents=True, exist_ok=True)
    (entries / f"{run_id}.json").write_text(
        json.dumps({"run_id": run_id, "complexity": complexity}), encoding="utf-8",
    )

    record = new_record(run_id)
    for review_type in RECORDABLE_TYPES:
        status = statuses.get(review_type, "completed")
        if status == "pending":
            continue                      # new_record already materialises it
        # upsert_review, not a direct `record["reviews"][...]` write: `spec` is a
        # gate row living in a sibling section, and routing is exactly what this
        # helper must not re-implement.
        record = upsert_review(record, make_entry(
            review_type, status,
            disposition=("the rule that applies" if status != "completed" else None),
            # Evidence, because the floor now asks whether a pass HAPPENED and
            # not merely whether a row says so. `recorded_by` is what a real
            # `--from <adapter>` recording leaves behind; all 45 of this repo's
            # real records carry at least one of the four traces.
            recorded_by=("code-reviewer" if status == "completed" else None),
        ), force=True)

    d = root / ".shipwright" / "planning" / "iterate" / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "reviews.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8",
    )


def _check(root: Path, run_id: str):
    # commit_hash="" skips the committed-in-HEAD half, which is a separate
    # concern with its own tests; these cases are about the floor.
    return check_review_record(root, run_id, "")


# ---------------------------------------------------------------------------
# The floor
# ---------------------------------------------------------------------------

def test_medium_blocks_when_neither_ran(tmp_path: Path):
    """The hole this closes: every type answered, nothing actually reviewed."""
    _write_run(
        tmp_path, "iterate-x", complexity="medium",
        statuses={"code": "not_run", "external_code": "not_run"},
    )
    result = _check(tmp_path, "iterate-x")
    assert result.ok is False
    assert "code review" in result.detail.lower()


def test_external_alone_satisfies_the_floor(tmp_path: Path):
    """The substitution path — 15 of 27 historical runs look exactly like this."""
    _write_run(
        tmp_path, "iterate-x", complexity="medium",
        statuses={"code": "not_run", "external_code": "completed"},
    )
    assert _check(tmp_path, "iterate-x").ok is True


def test_internal_alone_satisfies_the_floor(tmp_path: Path):
    _write_run(
        tmp_path, "iterate-x", complexity="medium",
        statuses={"code": "completed", "external_code": "not_run"},
    )
    assert _check(tmp_path, "iterate-x").ok is True


def test_not_applicable_does_not_satisfy_the_floor(tmp_path: Path):
    """Otherwise the gate is bypassable by re-labelling."""
    _write_run(
        tmp_path, "iterate-x", complexity="medium",
        statuses={"code": "not_applicable", "external_code": "not_applicable"},
    )
    assert _check(tmp_path, "iterate-x").ok is False


def test_large_is_floored_too(tmp_path: Path):
    _write_run(
        tmp_path, "iterate-x", complexity="large",
        statuses={"code": "not_run", "external_code": "not_run"},
    )
    assert _check(tmp_path, "iterate-x").ok is False


def test_small_is_not_floored(tmp_path: Path):
    """At small the phase matrix says review only on risk flags.

    The one historical zero-review run was small and was CORRECT; flooring it
    would turn compliant behaviour into a failure.
    """
    _write_run(
        tmp_path, "iterate-x", complexity="small",
        statuses={"code": "not_run", "external_code": "not_run"},
    )
    assert _check(tmp_path, "iterate-x").ok is True


def test_unknown_complexity_fails_the_gate(tmp_path: Path):
    """A run with no iterate entry now FAILS this gate. **This reverses a
    decision recorded here**, so the reversal is argued rather than assumed.

    The prior reasoning: the exposure is closed one check over, because
    `check_iterate_history_has_run_id` fails the same F11 run when the entry is
    missing, and F5c writes it before F11 gets here — so failing here too would
    change long-standing behaviour to defend a door already locked.

    What changed (`trg-51a57370`): the lock is on a DIFFERENT door. It holds
    only while both checks run in the same orchestrator, and `check_review_record`
    is called directly — by tests, and by anything invoking the verifier before
    F5c — where the sibling is not there to fail. A check that answers "not
    applicable" to a question it could not evaluate is the same fail-open shape
    this whole run is about; "I could not tell" and "this run is exempt" are
    different claims and only one of them was being made.

    The cost the prior decision named is real but bounded: no merged record is
    ever re-verified, so nothing retroactively reds, and the remediation is the
    F5c step the run owed anyway.
    """
    # No entry file at all → complexity unknown.
    d = tmp_path / ".shipwright" / "planning" / "iterate" / "iterate-x"
    d.mkdir(parents=True)
    record = new_record("iterate-x")
    for review_type in RECORDABLE_TYPES:
        record = upsert_review(record, make_entry(
            review_type, "not_run", disposition="the rule that applies",
        ), force=True)
    (d / "reviews.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

    result = _check(tmp_path, "iterate-x")
    assert result.is_failure
    assert "F5c" in result.detail


def test_trivial_is_skipped_entirely(tmp_path: Path):
    _write_run(
        tmp_path, "iterate-x", complexity="trivial",
        statuses={"code": "not_run", "external_code": "not_run"},
    )
    assert _check(tmp_path, "iterate-x").ok is True


# ---------------------------------------------------------------------------
# Ordering and regression
# ---------------------------------------------------------------------------

def test_pending_still_reported_first(tmp_path: Path):
    """An unanswered type must still read as unanswered, not as a floor failure.

    The two failures need different repairs — 'record the pass' vs 'run a
    review' — so the more specific message has to win.
    """
    _write_run(
        tmp_path, "iterate-x", complexity="medium",
        statuses={"code": "pending", "external_code": "not_run"},
    )
    result = _check(tmp_path, "iterate-x")
    assert result.ok is False
    assert "unanswered" in result.detail


@pytest.mark.parametrize(
    ("code", "external"),
    [
        ("not_run", "completed"),      # 15 historical runs
        ("completed", "completed"),    # 11 historical runs
    ],
)
def test_historical_shapes_still_pass(tmp_path: Path, code: str, external: str):
    """Replays the two medium+ shapes actually observed in this repo.

    The measurement said this floor blocks none of them; this keeps that claim
    from silently becoming false.

    Re-measured when the floor began demanding evidence rather than a status
    (``trg-51a57370``): of the 45 records in this repo carrying a completed
    ``code`` / ``external_code`` row, **45 carry evidence** and 0 are
    evidence-free. The promise holds under the tighter rule — which is why the
    fixture now supplies ``recorded_by``: a row without it is not a shape this
    repo has ever produced.
    """
    _write_run(
        tmp_path, "iterate-x", complexity="medium",
        statuses={"code": code, "external_code": external},
    )
    assert _check(tmp_path, "iterate-x").ok is True
