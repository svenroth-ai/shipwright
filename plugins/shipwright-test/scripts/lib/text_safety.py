#!/usr/bin/env python3
"""Normalizing externally-authored text before it is recorded or printed.

Journey titles, test names, spec paths, category and screen names are written
by people (or by other tools) and reach three places verbatim: the operator's
terminal, the triage record, and whatever renders that record downstream. An
ANSI escape smuggled into a plan heading should not be able to rewrite what an
operator sees, and a dedup key must be derived from the cleaned string or the
same finding can key two ways and appear twice.

Its own module rather than a corner of the plan parser: both test-phase
producers need it, and neither owns the other (external code review, R8/C3).

iterate-2026-07-27-test-phase-record-honesty, FR-01.06.
"""

from __future__ import annotations

import re

# C0 and C1 control characters, minus the ordinary whitespace (\t \n \r) that
# the whitespace collapse below handles.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def sanitize(text: str) -> str:
    """Strip control characters and collapse whitespace runs."""
    return " ".join(_CONTROL_CHARS.sub("", text).split())


__all__ = ["sanitize"]
