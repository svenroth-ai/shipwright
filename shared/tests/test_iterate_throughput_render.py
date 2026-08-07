"""Pin tests for the throughput-report render allowlist.

``_NESTED_CALLOUTS`` is a second span registry, independent of
``SPAN_PARENTS`` in ``iterate_timings.py`` with no drift guard between the
two (external code review, test-phase-attribution) - a new nested span name
can be added to one and silently omitted from the other. This file pins the
one deliberate omission that exists today so a future addition of
``f0_unit_result`` to the allowlist is a conscious edit, not a silent default.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from lib.iterate_throughput_render import _NESTED_CALLOUTS  # noqa: E402


def test_f0_unit_result_is_deliberately_excluded_from_the_render_allowlist():
    """One row per test unit per attempt (~18 rows) would flood the
    throughput report before any view exists to make that useful - the
    deferred latency follow-up designs that rendering. If this starts
    failing because someone added the name to _NESTED_CALLOUTS, that is a
    real design decision to make, not a regression to silently fix."""
    assert "f0_unit_result" not in _NESTED_CALLOUTS
