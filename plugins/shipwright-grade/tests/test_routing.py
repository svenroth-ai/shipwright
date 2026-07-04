"""Tests for routing — the authoritative-vs-heuristic contract."""

from __future__ import annotations

from pathlib import Path

import pytest
from routing import (
    STATE_ABSENT,
    STATE_MALFORMED,
    STATE_MIXED,
    STATE_PARTIAL,
    STATE_STALE,
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


def _mk_canonical(root: Path, *, events: str, rtm: bool = True) -> None:
    """Build the REAL Shipwright layout: root-level shipwright_events.jsonl +
    .shipwright/compliance/traceability-matrix.md (what the collector reads)."""
    (root / "shipwright_events.jsonl").write_text(events, encoding="utf-8")
    if rtm:
        comp = root / ".shipwright" / "compliance"  # artifact-path-canon: legacy
        comp.mkdir(parents=True, exist_ok=True)
        (comp / "traceability-matrix.md").write_text(  # artifact-path-canon: legacy
            "# Traceability Matrix\n", encoding="utf-8")


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


class TestCanonicalLayout:
    """The REAL Shipwright layout — root shipwright_events.jsonl +
    .shipwright/compliance/traceability-matrix.md — is authoritative (G4 fixes the
    G1 gap where only .shipwright/events.jsonl + rtm.md were recognised)."""

    def test_canonical_layout_is_authoritative(self, tmp_path: Path):
        _mk_canonical(tmp_path, events='{"type": "work_completed"}\n')
        d = decide_routing(tmp_path)
        assert d.state == STATE_VALID
        assert d.detected_mode == "authoritative"

    def test_root_events_without_rtm_is_mixed(self, tmp_path: Path):
        (tmp_path / ".shipwright").mkdir()
        _mk_canonical(tmp_path, events='{"type": "work_completed"}\n', rtm=False)
        d = decide_routing(tmp_path)
        assert d.state == STATE_MIXED
        assert d.detected_mode == "heuristic"

    def test_symlinked_eventlog_escaping_root_is_ignored(self, tmp_path: Path):
        # A hostile clone points shipwright_events.jsonl at an out-of-tree file;
        # routing must not follow it (→ log treated as absent). POSIX-only.
        outside = tmp_path / "outside.jsonl"
        outside.write_text('{"type": "work_completed"}\n', encoding="utf-8")
        repo = tmp_path / "repo"
        (repo / ".shipwright" / "compliance").mkdir(parents=True)
        (repo / ".shipwright" / "compliance" / "traceability-matrix.md").write_text(
            "# RTM\n", encoding="utf-8")
        link = repo / "shipwright_events.jsonl"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform/privilege")
        d = decide_routing(repo)
        # RTM present, event log symlink ignored → MIXED, never authoritative.
        assert d.detected_mode == "heuristic"
        assert d.state in (STATE_MIXED, STATE_PARTIAL)


class TestStaleness:
    """Staleness (G4): a VALID-shaped `.shipwright/` whose recorded commits are
    all behind the working-tree HEAD falls back to heuristic (STATE_STALE)."""

    def test_stale_when_head_not_in_recorded_commits(self, tmp_path: Path):
        _mk_shipwright(
            tmp_path,
            events='{"type": "work_completed", "commit": "aaaaaaaaaaaa"}\n',
            rtm=True,
        )
        d = decide_routing(tmp_path, head_sha="bbbbbbbbbbbb")
        assert d.state == STATE_STALE
        assert d.detected_mode == "heuristic"
        assert d.effective_mode == "heuristic"

    def test_valid_when_head_matches_a_recorded_commit(self, tmp_path: Path):
        head = "abcdef0123456789abcdef0123456789abcdef01"
        _mk_shipwright(
            tmp_path,
            events='{"type": "work_completed", "commit": "abcdef0123456"}\n',
            rtm=True,
        )
        d = decide_routing(tmp_path, head_sha=head)
        assert d.state == STATE_VALID
        assert d.detected_mode == "authoritative"

    def test_commitless_log_stays_valid(self, tmp_path: Path):
        # The worktree-model log carries commit="" — staleness is unknowable, so
        # we must NOT false-flag it as stale.
        _mk_shipwright(
            tmp_path,
            events='{"type": "work_completed", "commit": ""}\n',
            rtm=True,
        )
        d = decide_routing(tmp_path, head_sha="deadbeefcafe")
        assert d.state == STATE_VALID
        assert d.detected_mode == "authoritative"

    def test_no_head_sha_stays_valid(self, tmp_path: Path):
        _mk_shipwright(
            tmp_path,
            events='{"type": "work_completed", "commit": "aaaaaaaaaaaa"}\n',
            rtm=True,
        )
        d = decide_routing(tmp_path)  # no head_sha → cannot assess staleness
        assert d.state == STATE_VALID

    def test_large_log_reads_the_tail_not_the_head(self, tmp_path: Path):
        # Regression: a >64 KB log whose OLDEST events carry legacy commits but
        # whose NEWEST work_completed is commit-less must NOT be flagged stale
        # (a head-only read saw the old commits and mis-fired). Pins the tail read.
        old = "".join(
            f'{{"type": "work_completed", "id": "old{i}", "commit": "deadbeef{i:04d}", '
            f'"ts": "2024-01-01T00:00:00", "note": "{"x" * 200}"}}\n'
            for i in range(400)
        )
        newest = '{"type": "work_completed", "id": "new", "commit": "", "ts": "2024-06-01T00:00:00"}\n'
        _mk_canonical(tmp_path, events=old + newest)
        assert len((old + newest).encode("utf-8")) > 65536  # exceeds the head cap
        d = decide_routing(tmp_path, head_sha="feedface0000")
        assert d.state == STATE_VALID
        assert d.detected_mode == "authoritative"
