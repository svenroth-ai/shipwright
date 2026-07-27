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

from lib.review_record_core import make_entry, new_record  # noqa: E402
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
    for review_type in ("self", "plan", "code", "doubt", "external_code"):
        status = statuses.get(review_type, "completed")
        if status == "pending":
            continue                      # new_record already materialises it
        record["reviews"][review_type] = make_entry(
            review_type, status,
            disposition=("the rule that applies" if status != "completed" else None),
        )

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


def test_unknown_complexity_skips_the_gate_and_is_caught_elsewhere(tmp_path: Path):
    """A run with no iterate entry skips this gate — deliberately, not by accident.

    Raised by both external plan reviewers: if complexity cannot be read, the
    floor does not apply, so failing to write the entry would be a way around
    it. Pinned here rather than "fixed" because the hole is closed one check
    over: `check_iterate_history_has_run_id` fails the same F11 run when the
    entry is missing, and F5c writes that entry before F11 reaches this point.
    Making this check ALSO fail closed would change long-standing behaviour for
    every pre-entry record, to defend a door that is already locked.

    The test exists so that if the sibling check is ever relaxed, the exposure
    is visible here instead of being rediscovered.
    """
    # No entry file at all → complexity unknown.
    d = tmp_path / ".shipwright" / "planning" / "iterate" / "iterate-x"
    d.mkdir(parents=True)
    record = new_record("iterate-x")
    for review_type in ("self", "plan", "code", "doubt", "external_code"):
        record["reviews"][review_type] = make_entry(
            review_type, "not_run", disposition="the rule that applies",
        )
    (d / "reviews.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

    result = _check(tmp_path, "iterate-x")
    assert result.ok is True
    assert result.severity == "skipped"


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
    """
    _write_run(
        tmp_path, "iterate-x", complexity="medium",
        statuses={"code": code, "external_code": external},
    )
    assert _check(tmp_path, "iterate-x").ok is True
