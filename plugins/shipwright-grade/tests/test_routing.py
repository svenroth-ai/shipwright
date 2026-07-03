"""Tests for routing — the authoritative-vs-heuristic contract."""

from __future__ import annotations

from pathlib import Path

from routing import (
    STATE_ABSENT,
    STATE_MALFORMED,
    STATE_MIXED,
    STATE_PARTIAL,
    STATE_VALID,
    decide_routing,
)


def _mk_shipwright(root: Path, *, events: str | None = None, rtm: bool = False) -> None:
    sw = root / ".shipwright"
    sw.mkdir(parents=True, exist_ok=True)
    if events is not None:
        (sw / "events.jsonl").write_text(events, encoding="utf-8")
    if rtm:
        comp = sw / "compliance"  # artifact-path-canon: legacy
        comp.mkdir(parents=True, exist_ok=True)
        (comp / "rtm.md").write_text("# RTM\n", encoding="utf-8")


class TestRouting:
    def test_absent_is_heuristic(self, tmp_path: Path):
        d = decide_routing(tmp_path)
        assert d.state == STATE_ABSENT
        assert d.detected_mode == "heuristic"
        assert d.effective_mode == "heuristic"
        assert d.is_authoritative_source is False

    def test_valid_shipwright_is_authoritative_source_but_heuristic_effective(
        self, tmp_path: Path
    ):
        _mk_shipwright(tmp_path, events='{"type": "work_completed"}\n', rtm=True)
        d = decide_routing(tmp_path)
        assert d.state == STATE_VALID
        assert d.detected_mode == "authoritative"
        # G1 always grades heuristically; authoritative ingestion is G4.
        assert d.effective_mode == "heuristic"
        assert d.is_authoritative_source is True

    def test_partial_shipwright_falls_back_to_heuristic(self, tmp_path: Path):
        (tmp_path / ".shipwright").mkdir()
        d = decide_routing(tmp_path)
        assert d.state == STATE_PARTIAL
        assert d.detected_mode == "heuristic"

    def test_malformed_event_log_is_heuristic(self, tmp_path: Path):
        _mk_shipwright(tmp_path, events="not json at all\n", rtm=True)
        d = decide_routing(tmp_path)
        assert d.state == STATE_MALFORMED
        assert d.detected_mode == "heuristic"

    def test_mixed_events_without_rtm_is_heuristic(self, tmp_path: Path):
        _mk_shipwright(tmp_path, events='{"type": "x"}\n', rtm=False)
        d = decide_routing(tmp_path)
        assert d.state == STATE_MIXED
        assert d.detected_mode == "heuristic"
