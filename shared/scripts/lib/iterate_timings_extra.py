#!/usr/bin/env python3
"""Iterate-timing spans — the ``extra`` metadata bag's closed-vocabulary validation.

Split from ``iterate_timings.py`` at ~300 lines (file-size guideline). Self-
contained leaf module (no dependency on the parent, which imports back from
here) enforcing "never record prompts/findings/source/console/test output"
by construction: an unlisted key, a wrong type, an over-length or non-
identifier-shaped string, or an out-of-range/non-finite number is rejected,
not merely discouraged.
"""

from __future__ import annotations

import math
import re


class IterateTimingError(ValueError):
    """A span/event could not be validated. Callers treat this as reject-one, not fatal."""


EXTRA_FIELD_TYPES: dict[str, tuple[type, ...]] = {
    "waited_seconds": (int, float),
    "provider": (str,),
    "rung": (str,),
    "polls": (int,),
    "timed_out": (bool,),
    "checks_observed": (int,),
    "checks_passed": (int,),
    "weight": (int,),
    "capacity": (int,),
    "blocker_owner": (str,),
    "blocker_run_id": (str,),
    "restart_reason": (str,),
    "retry_shape": (str,),
    "conclusion": (str,),
    "reviewer": (str,),
    "stage": (str,),
    "resource": (str,),
}
_EXTRA_STR_MAX = 80
_EXTRA_MAX_KEYS = 10
# Identifier-shaped only — a length cap alone still let a CLI-supplied
# --extra-json value hold up to 200 chars of arbitrary prose (a prompt
# fragment, a finding, a log line) under an allowed key; prose almost always
# uses characters this excludes (quotes, parens, newlines, most punctuation)
# (external code review). Every actual value this codebase writes (provider
# names, rungs, statuses, owner:pid:dir strings, run ids) fits comfortably.
_EXTRA_STR_PATTERN = re.compile(r"^[A-Za-z0-9 ._:/-]*$")

# Every numeric ``extra`` field MUST have a bound here — validate_extra fails
# closed (rejects) on a numeric field with no entry, rather than passing an
# unbounded value through by omission (external code review: a huge int or a
# NaN/Infinity float previously passed the bare isinstance check unbounded).
# `test_every_numeric_extra_field_has_a_registered_bound` pins forward+reverse
# coverage against EXTRA_FIELD_TYPES (SSoT registry convention).
_EXTRA_NUMERIC_BOUNDS: dict[str, tuple[float, float]] = {
    "waited_seconds": (0, 172800),   # 48h — well past the documented 34h outlier run
    "polls": (0, 100_000),
    "checks_observed": (0, 1_000),
    "checks_passed": (0, 1_000),
    "weight": (0, 1_000),
    "capacity": (0, 1_000),
}


def validate_extra(extra: dict | None) -> dict:
    """Validate the bounded metadata bag against the closed vocabulary above."""
    if not extra:
        return {}
    if not isinstance(extra, dict):
        raise IterateTimingError(f"extra must be an object, got {type(extra).__name__}")
    if len(extra) > _EXTRA_MAX_KEYS:
        raise IterateTimingError(f"extra has too many fields ({len(extra)} > {_EXTRA_MAX_KEYS})")
    clean: dict = {}
    for key, value in extra.items():
        types = EXTRA_FIELD_TYPES.get(key)
        if types is None:
            raise IterateTimingError(f"unknown extra field {key!r} (closed vocabulary)")
        if isinstance(value, bool) and bool not in types:
            raise IterateTimingError(f"extra[{key!r}] must be one of {types}, got bool")
        if not isinstance(value, types):
            raise IterateTimingError(f"extra[{key!r}] must be one of {types}, got {type(value).__name__}")
        if isinstance(value, str):
            if len(value) > _EXTRA_STR_MAX:
                raise IterateTimingError(f"extra[{key!r}] exceeds {_EXTRA_STR_MAX} chars")
            if not _EXTRA_STR_PATTERN.match(value):
                raise IterateTimingError(
                    f"extra[{key!r}] must be identifier-shaped "
                    f"(letters/digits/space/._:/- only)"
                )
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            # bool is an int subclass in Python - without this exclusion a
            # legitimate bool-typed field (e.g. timed_out) falls into the
            # numeric-bounds branch below, finds no registered bound (bools
            # aren't numeric), and the fail-closed check rejects the ENTIRE
            # extra dict - silently dropping the whole span in production
            # (caught live: deliver_pr.py's ci_wait span carries timed_out).
            if isinstance(value, float) and not math.isfinite(value):
                raise IterateTimingError(
                    f"extra[{key!r}] must be finite (no NaN/Infinity), got {value!r}")
            bounds = _EXTRA_NUMERIC_BOUNDS.get(key)
            if bounds is None:  # fail closed: an unbounded numeric field is a bug, not data
                raise IterateTimingError(f"extra[{key!r}] has no registered numeric bound")
            lo, hi = bounds
            if not (lo <= value <= hi):
                raise IterateTimingError(f"extra[{key!r}] must be within [{lo}, {hi}], got {value!r}")
        clean[key] = value
    return clean
