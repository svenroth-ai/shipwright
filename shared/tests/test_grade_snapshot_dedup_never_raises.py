"""``grade_snapshot`` dedup — the comparison never raises (AC3d).

Split from ``test_grade_snapshot_dedup.py``; see that module for the contract as
a whole. This half exists because the comparison runs **while holding the append
lock**, over a durable log that is union-merged and hand-editable. A raise there
leaves ``append_event_idempotent``, lands in ``update_compliance``'s best-effort
``except Exception``, and the snapshot is LOST — strictly worse than the
duplicate the dedup exists to remove.

The SYMMETRIC cases are the load-bearing ones. An asymmetric case (malformed on
one side, clean on the other) differs in value anyway and so never reaches the
equality the guards prevent — both the ``bool`` and the ``isfinite`` guard
survived deletion with the whole suite green until the symmetric cases existed
(Stage-3 doubt review, confirmed by mutation).
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _grade_snapshot_dedup_fixtures import _append, _snap, _snaps, _write  # noqa: E402
from lib.event_dedup import unchanged_grade_skip  # noqa: E402


class _ExplodingFloat(float):
    error_type = ValueError

    def __float__(self):
        raise self.error_type("deliberate numeric-subclass failure")


class TestTheComparisonNeverRaises:
    """It runs under the append lock, over durable union-merged amendable data."""

    # `10**400` and not a bigger number on purpose: it round-trips through JSON
    # yet overflows `float()`, so it reaches `_comparable_grade` the way a real
    # log line would. Python 3.11 caps int<->str at 4300 digits, so `10**10000`
    # cannot survive `json.dumps`/`loads` at all and would test the JSON layer
    # rather than this code.
    @pytest.mark.parametrize(
        "score",
        [None, "95", True, False, float("nan"), float("inf"), float("-inf"),
         10**400, [88.0], {"v": 88.0}],
        ids=["null", "numeric-string", "true", "false", "nan", "inf", "-inf",
             "float-overflowing-int", "list", "dict"],
    )
    def test_a_malformed_predecessor_score_never_raises_and_never_suppresses(
        self, tmp_path, score,
    ):
        _write(tmp_path, _snap(score=score))
        event_id, skip = _append(tmp_path, _snap())
        assert skip is None and event_id is not None

    @pytest.mark.parametrize(
        "score", [None, "95", True, float("nan"), 10**400],
        ids=["null", "numeric-string", "true", "nan", "float-overflowing-int"],
    )
    def test_a_malformed_candidate_score_never_raises_and_never_suppresses(
        self, tmp_path, score,
    ):
        _write(tmp_path, _snap())
        event_id, skip = _append(tmp_path, _snap(score=score))
        assert skip is None and event_id is not None

    @pytest.mark.parametrize("grade", [None, "", 7, ["B"]],
                             ids=["null", "empty", "int", "list"])
    def test_a_malformed_grade_never_raises_and_never_suppresses(self, tmp_path, grade):
        _write(tmp_path, _snap(grade=grade))
        event_id, skip = _append(tmp_path, _snap(grade=grade))
        assert skip is None and event_id is not None

    def test_a_corrupt_line_never_turns_an_older_match_into_a_skip(
        self, tmp_path, recwarn,
    ):
        """Corruption fails open under production-default warning handling.

        The recovered prefix deliberately contains a matching snapshot. If the
        reader's warning is treated as the corruption signal, normal warning
        handling returns that prefix and suppresses the candidate, collapsing a
        possible B -> unknown -> B transition across the unreadable fragment.
        """
        (tmp_path / "shipwright_events.jsonl").write_text(
            json.dumps(_snap()) + "\n"
            + '{"type":"grade_snapshot","grade":"A" {truncated\n',
            encoding="utf-8",
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("default")
            event_id, skip = _append(tmp_path, _snap())
        assert event_id is not None and skip is None, "an unreadable log must not eat the append"
        assert len(_snaps(tmp_path)) == 2
        assert any("Corrupt event" in str(item.message) for item in caught)

    def test_a_corrupt_line_warning_as_error_does_not_cost_the_snapshot(self, tmp_path):
        (tmp_path / "shipwright_events.jsonl").write_text(
            json.dumps(_snap()) + "\n" + "{truncated\n",
            encoding="utf-8",
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            event_id, skip = _append(tmp_path, _snap())
        assert event_id is not None and skip is None
        assert len(_snaps(tmp_path)) == 2

    def test_a_malformed_amendment_fails_open(self, tmp_path):
        predecessor = _snap()
        malformed = {
            "v": 1, "id": "evt-bad-amend", "ts": "2026-08-01T00:00:01+00:00",
            "type": "event_amended", "amends": predecessor["id"], "fields": [],
        }
        _write(tmp_path, predecessor, malformed)

        event_id, skip = _append(tmp_path, _snap())

        assert event_id is not None and skip is None
        assert len(_snaps(tmp_path)) == 2

    # SYMMETRIC — the same malformed value on BOTH sides. This is the shape that
    # actually pins the guards: the asymmetric cases above differ in value
    # anyway, so they never reach the equality the guards exist to prevent, and
    # both the `bool` and the `isfinite` guard survived deletion with the whole
    # suite green until these cases existed (Stage-3 doubt review, confirmed by
    # mutation). `True` would otherwise compare as the grade 1.0, and
    # `inf == inf` is True.
    @pytest.mark.parametrize(
        "score", [None, True, float("inf"), float("-inf"), "95", 10**400],
        ids=["null", "true", "inf", "-inf", "numeric-string",
             "float-overflowing-int"],
    )
    def test_two_malformed_records_are_not_equal_to_each_other(self, tmp_path, score):
        # The guard is "both comparable AND equal", not "the two answers match" —
        # a naive `_comparable(a) == _comparable(b)` makes None == None suppress.
        _write(tmp_path, _snap(score=score))
        _, skip = _append(tmp_path, _snap(score=score))
        assert skip is None, f"two unreadable grades (score={score!r}) are not the same grade"

    def test_a_symmetric_nan_is_not_equal_to_itself_either(self, tmp_path):
        # nan is the one case that would fall out even without isfinite, since
        # nan != nan. Kept separate so it cannot be mistaken for evidence that
        # the isfinite guard is pinned — the inf cases above are what pin it.
        _write(tmp_path, _snap(score=float("nan")))
        _, skip = _append(tmp_path, _snap(score=float("nan")))
        assert skip is None

    @pytest.mark.parametrize("error_type", [TypeError, ValueError, OverflowError])
    def test_a_numeric_subclass_conversion_failure_never_raises(
        self, tmp_path, error_type,
    ):
        class Exploding(_ExplodingFloat):
            pass

        Exploding.error_type = error_type
        _write(tmp_path, _snap())
        event_id, skip = _append(tmp_path, _snap(score=Exploding(88.0)))
        assert event_id is not None and skip is None

    @pytest.mark.parametrize("entry", [[], "scalar", 7, None, True])
    def test_a_non_object_entry_handed_to_the_helper_never_raises(self, entry):
        skip = unchanged_grade_skip(_snap(), [_snap(), entry])
        assert skip == {"reason": "unchanged_grade", "grade": "B", "score": 88.0}
