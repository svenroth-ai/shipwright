"""`amend` joins the drift-adoption producer-event universe (AC8).

iterate-2026-08-08-triage-amend-event. Before this change, a legitimate
`amend` line on main's tracked log would refuse as `main_tracked_unparseable`
— indistinguishable from genuine corruption — instead of being adopted like
`append`/`status`. Unit-level: exercises the pure predicates directly, no git
fixture needed for this shape-only question.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.sweep_drift_events import _bad_drift_reason, _is_producer_event  # noqa: E402

AMEND_LINE = '{"event":"amend","id":"trg-1","ts":"2026-08-08T00:00:00Z","by":"cli","title":"x"}'
STATUS_LINE = '{"event":"status","id":"trg-2","newStatus":"dismissed","by":"webui"}'


def test_a_well_formed_amend_line_is_a_producer_event() -> None:
    assert _is_producer_event(AMEND_LINE) is True


def test_an_amend_line_glued_to_another_record_gets_the_glued_reason_code() -> None:
    """An `amend` line concatenated onto another record is the AC14 recoverable
    shape, not indistinguishable garbage — `_bad_drift_reason` must route it to
    `main_tracked_glued_line`, not the generic `main_tracked_unparseable`."""
    reason = _bad_drift_reason(1, AMEND_LINE + STATUS_LINE)
    assert "main_tracked_glued_line" in reason
