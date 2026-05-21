"""Determinism tests for ComplianceData.timestamp + downstream `Generated:`
banners in the 5 compliance generators.

Iterate: iterate-2026-05-22-deterministic-render-timestamps.

The bug: `data_collector.collect_all()` used to set
`timestamp=datetime.now(timezone.utc).strftime(...)`. Every regeneration
of `.shipwright/compliance/*.md` therefore mutated the
`Generated: <ISO-now>` line of all 5 files even when the underlying
events were unchanged. Working tree was perpetually dirty.

The fix: `collect_all()` now derives timestamp from
`max(event.timestamp for event in work_events)`. Two runs against the
same `shipwright_events.jsonl` produce identical `ComplianceData.timestamp`
and identical rendered markdown.

This test lives in the compliance plugin's own test suite (sys.path
clean to its `scripts/lib/`) because the same test in `shared/tests/`
runs into a sys.modules ordering issue when other shared tests have
already loaded a different `scripts` package layout. See
iterate-2026-05-22's mini-plan + ADR for the topology details.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.lib.change_history import generate as render_change_history
from scripts.lib.compliance_report import generate as render_compliance_dashboard
from scripts.lib.data_collector import (
    ComplianceData,
    _latest_event_timestamp,
    collect_all,
)
from scripts.lib.rtm_generator import generate as render_rtm
from scripts.lib.sbom_generator import generate as render_sbom
from scripts.lib.test_evidence import generate as render_test_evidence


_BASE_EVENT_LINE = json.dumps({
    "type": "work_completed",
    "source": "iterate",
    "ts": "2026-05-20T12:00:00+00:00",
    "intent": "change",
    "description": "baseline event",
    "tests": {"passed": 5, "total": 5},
    "commit": "abc1234567890",
    "affected_frs": [],
})

_LATER_EVENT_LINE = json.dumps({
    "type": "work_completed",
    "source": "iterate",
    "ts": "2026-05-22T10:30:00+00:00",
    "intent": "change",
    "description": "later event",
    "tests": {"passed": 6, "total": 6},
    "commit": "def4567890abc",
    "affected_frs": [],
})


def _write_min_repo(project_root: Path, *, event_lines: list[str]) -> None:
    """Materialise the minimum on-disk shape `collect_all` expects."""
    (project_root / "shipwright_events.jsonl").write_text(
        ("\n".join(event_lines) + "\n") if event_lines else "",
        encoding="utf-8",
    )
    (project_root / "shipwright_run_config.json").write_text(
        json.dumps({
            "status": "complete",
            "completed_steps": ["project", "plan", "build", "test"],
            "current_step": None,
        }),
        encoding="utf-8",
    )
    (project_root / "shipwright_build_config.json").write_text(
        json.dumps({"splits": []}),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# `_latest_event_timestamp` (the compliance-side local mirror of
# shared/scripts/lib/events_log.latest_event_dt)
# ---------------------------------------------------------------------------


class TestLatestEventTimestamp:
    """The compliance-side helper must mirror the shared helper's contract."""

    def test_empty_returns_literal(self):
        assert _latest_event_timestamp([]) == "(no events)"

    def test_single_event(self):
        from scripts.lib.data_collector import WorkEvent
        e = WorkEvent(id="e1", timestamp="2026-05-20T12:00:00+00:00", source="iterate")
        assert _latest_event_timestamp([e]) == "2026-05-20T12:00:00+00:00"

    def test_multiple_events_returns_max(self):
        from scripts.lib.data_collector import WorkEvent
        events = [
            WorkEvent(id="e1", timestamp="2026-05-20T12:00:00+00:00", source="iterate"),
            WorkEvent(id="e2", timestamp="2026-05-22T03:30:00+00:00", source="iterate"),
            WorkEvent(id="e3", timestamp="2026-05-21T09:15:00+00:00", source="iterate"),
        ]
        assert _latest_event_timestamp(events) == "2026-05-22T03:30:00+00:00"

    def test_skips_blank_timestamps(self):
        from scripts.lib.data_collector import WorkEvent
        events = [
            WorkEvent(id="e1", timestamp="", source="iterate"),
            WorkEvent(id="e2", timestamp="2026-05-20T12:00:00+00:00", source="iterate"),
        ]
        assert _latest_event_timestamp(events) == "2026-05-20T12:00:00+00:00"

    def test_parity_with_shared_helper(self, tmp_path):
        """Sanity: the compliance-side helper and the shared
        `events_log.latest_event_dt` must agree on the same input,
        modulo their interface mismatch (str vs datetime).

        This is the drift-protection test the events_log.py docstring
        mentions but the compliance-plugin side didn't yet have.
        """
        import json
        import sys
        from datetime import datetime, timezone
        from pathlib import Path

        # The compliance plugin's tests don't normally have shared/lib
        # on sys.path — add it explicitly for the parity probe.
        repo_root = Path(__file__).resolve().parents[3]
        shared_scripts = repo_root / "shared" / "scripts"
        if str(shared_scripts) not in sys.path:
            sys.path.insert(0, str(shared_scripts))
        from lib.events_log import latest_event_dt  # type: ignore[import-not-found]

        # Write a synthetic events.jsonl that both helpers will read.
        (tmp_path / "shipwright_events.jsonl").write_text("\n".join([
            json.dumps({"type": "x", "ts": "2026-05-20T12:00:00+00:00"}),
            json.dumps({"type": "y", "ts": "2026-05-22T03:30:00+00:00"}),
        ]) + "\n", encoding="utf-8")

        # Shared helper: returns datetime.
        shared_dt = latest_event_dt(tmp_path)
        assert shared_dt is not None

        # Compliance helper: takes a list of WorkEvent (the post-collect
        # form). Build it from the same fixture.
        from scripts.lib.data_collector import WorkEvent, _read_event_log
        raw = _read_event_log(tmp_path)
        events = [
            WorkEvent.from_dict(d) if hasattr(WorkEvent, "from_dict") and "id" in d
            else WorkEvent(id=str(d.get("id", "")), timestamp=d.get("ts", ""), source=d.get("source", ""))
            for d in raw
        ]
        compliance_str = _latest_event_timestamp(events)

        # Parity check: shared.isoformat() == compliance string (both
        # represent the same instant, with the same suffix shape since
        # events use +00:00).
        assert shared_dt == datetime(2026, 5, 22, 3, 30, 0, tzinfo=timezone.utc)
        assert compliance_str == "2026-05-22T03:30:00+00:00"
        # Round-trip the compliance string through datetime parsing and
        # confirm it equals the shared helper's answer.
        parsed = datetime.fromisoformat(compliance_str.replace("Z", "+00:00"))
        assert parsed == shared_dt, (
            f"Parity broken: shared helper says {shared_dt!r} but "
            f"compliance helper says {compliance_str!r}"
        )


# ---------------------------------------------------------------------------
# Compliance generators — each renders byte-identical output across two
# back-to-back calls separated by real wall-clock time.
# ---------------------------------------------------------------------------


_GENERATORS = {
    "change_history": render_change_history,
    "compliance_dashboard": render_compliance_dashboard,
    "rtm": render_rtm,
    "sbom": render_sbom,
    "test_evidence": render_test_evidence,
}


@pytest.mark.parametrize("generator_id", list(_GENERATORS.keys()))
def test_generator_is_deterministic_against_same_events(
    tmp_path: Path, generator_id: str
) -> None:
    """Two renders against the same events.jsonl produce identical markdown.

    Pre-fix this asserted differently for the 5 generators with a
    `Generated: <ISO-now>` banner — every call drifted by seconds.
    """
    _write_min_repo(tmp_path, event_lines=[_BASE_EVENT_LINE])

    render = _GENERATORS[generator_id]

    out_1 = render(collect_all(tmp_path))
    time.sleep(1.2)  # real wall-clock advance
    out_2 = render(collect_all(tmp_path))

    assert out_1 == out_2, (
        f"[{generator_id}] Compliance render is non-deterministic — "
        f"two back-to-back calls produced different output despite "
        f"identical events.jsonl input.\n"
        f"=== First (first 400 chars) ===\n{out_1[:400]}\n"
        f"=== Second (first 400 chars) ===\n{out_2[:400]}"
    )


@pytest.mark.parametrize("generator_id", list(_GENERATORS.keys()))
def test_generator_changes_when_events_change(
    tmp_path: Path, generator_id: str
) -> None:
    """Sanity check: adding an event to events.jsonl MUST change the output
    for the 5 generators that reflect event data in their banner / body.

    This rules out "tests pass because the helper degenerated to a constant".
    """
    _write_min_repo(tmp_path, event_lines=[_BASE_EVENT_LINE])
    render = _GENERATORS[generator_id]

    out_1 = render(collect_all(tmp_path))

    _write_min_repo(tmp_path, event_lines=[_BASE_EVENT_LINE, _LATER_EVENT_LINE])

    out_2 = render(collect_all(tmp_path))

    if generator_id == "sbom":
        # SBOM renders dependency lists, not event data — its `Generated:`
        # banner is the only event-derived field, and adding a non-build
        # event SHOULD bump the banner from 2026-05-20 to 2026-05-22. If
        # outputs are still identical, the banner is degenerate.
        assert out_1 != out_2, (
            f"[sbom] Adding a later event did not change the rendered "
            f"banner — `Generated:` is degenerate."
        )
    else:
        assert out_1 != out_2, (
            f"[{generator_id}] Adding a later event did not change the "
            f"render output — the generator is not reading event data "
            f"(degenerate determinism)."
        )


def test_collect_all_timestamp_is_event_derived(tmp_path: Path) -> None:
    """`ComplianceData.timestamp` set by `collect_all` is the events' max ts
    (NOT a wall-clock datetime.now), so two invocations produce equal data.
    """
    _write_min_repo(tmp_path, event_lines=[
        _BASE_EVENT_LINE,
        _LATER_EVENT_LINE,
    ])
    data_1 = collect_all(tmp_path)
    time.sleep(0.5)
    data_2 = collect_all(tmp_path)
    assert data_1.timestamp == data_2.timestamp
    assert data_1.timestamp == "2026-05-22T10:30:00+00:00"


def test_collect_all_falls_back_to_literal_when_no_events(tmp_path: Path) -> None:
    """Empty / missing events.jsonl yields the stable `(no events)` literal."""
    _write_min_repo(tmp_path, event_lines=[])
    data = collect_all(tmp_path)
    assert data.timestamp == "(no events)"
