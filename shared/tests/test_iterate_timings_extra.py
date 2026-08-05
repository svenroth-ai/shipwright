"""Tests for the ``extra`` metadata bag's closed-vocabulary validation.

Mirrors the ``iterate_timings.py`` -> ``iterate_timings_extra.py`` split.
Covers the external-code-review numeric-bounds finding: a huge int or a
non-finite float previously passed the bare ``isinstance`` check unbounded.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from lib import iterate_timings_extra as ite  # noqa: E402


def test_every_numeric_extra_field_has_a_registered_bound():
    """SSoT registry rule (forward+reverse): a numeric field in
    EXTRA_FIELD_TYPES with no bound would silently validate as unbounded;
    a bound for a field EXTRA_FIELD_TYPES doesn't define is dead weight."""
    numeric_fields = {
        key for key, types in ite.EXTRA_FIELD_TYPES.items()
        if int in types or float in types
    }
    assert numeric_fields == set(ite._EXTRA_NUMERIC_BOUNDS)


def test_numeric_field_within_bounds_is_accepted():
    assert ite.validate_extra({"weight": 22, "waited_seconds": 1080.0}) == {
        "weight": 22, "waited_seconds": 1080.0,
    }


def test_numeric_field_over_its_bound_is_rejected():
    with_out_of_range = {"polls": 10_000_000}
    try:
        ite.validate_extra(with_out_of_range)
        assert False, "expected IterateTimingError"
    except ite.IterateTimingError as exc:
        assert "polls" in str(exc)


def test_nan_float_is_rejected():
    try:
        ite.validate_extra({"waited_seconds": math.nan})
        assert False, "expected IterateTimingError"
    except ite.IterateTimingError as exc:
        assert "finite" in str(exc)


def test_infinite_float_is_rejected():
    try:
        ite.validate_extra({"waited_seconds": math.inf})
        assert False, "expected IterateTimingError"
    except ite.IterateTimingError as exc:
        assert "finite" in str(exc)


def test_negative_number_below_its_bound_is_rejected():
    try:
        ite.validate_extra({"weight": -1})
        assert False, "expected IterateTimingError"
    except ite.IterateTimingError as exc:
        assert "weight" in str(exc)


def test_bool_typed_field_does_not_fall_into_the_numeric_bounds_branch():
    """Live production regression: bool is an int subclass in Python, so a
    genuine bool-typed field (timed_out) fell into the numeric-bounds branch,
    found no registered bound (bools aren't numeric), and the fail-closed
    check rejected the ENTIRE extra dict — silently dropping deliver_pr.py's
    own ci_wait span in a real delivery run."""
    assert ite.validate_extra({"timed_out": True}) == {"timed_out": True}
    assert ite.validate_extra({"timed_out": False}) == {"timed_out": False}
