"""Tests for the authoritative-ingestion path (G4).

A target with a healthy, current ``.shipwright/`` (root ``shipwright_events.jsonl``
+ ``.shipwright/compliance/traceability-matrix.md``) is graded from its OWN records
via the compliance adapter and the shared engine. Every degraded case — corrupt,
partial, stale, empty, or an adapter failure — falls back to the labelled heuristic
projection instead.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import authoritative
import grade_inputs_projector
from conftest import build_repo
from engine_bridge import load_engine
from grade_inputs_projector import grade_context
from repo_context import RepoContext
from resolve_target import resolve_target
from routing import RoutingDecision

# Commit-less events (the modern worktree model: F6.5 skipped, commit=""), so the
# staleness check correctly declines to judge and the log grades authoritatively.
_WORK_EVENTS = (
    '{"type": "work_completed", "id": "e1", "ts": "2024-01-02T09:00:00+00:00", '
    '"source": "iterate", "commit": "", "tests": {"passed": 3, "total": 3}, '
    '"affected_frs": ["FR-01"], "change_type": "fr", "adr_id": "iterate-a"}\n'
    '{"type": "work_completed", "id": "e2", "ts": "2024-01-03T09:00:00+00:00", '
    '"source": "iterate", "commit": "", "tests": {"passed": 4, "total": 4}, '
    '"change_type": "none", "none_reason": "docs", "adr_id": "iterate-b"}\n'
)
_RTM = "# Traceability Matrix\n\n| FR | Status |\n|----|--------|\n| FR-01 | ok |\n"


def _canonical_repo(root: Path, events: str = _WORK_EVENTS) -> Path:
    """A real git repo carrying the canonical Shipwright records."""
    return build_repo(root, [
        {"subject": "chore: seed (#1)", "date": "2024-01-01T09:00:00",
         "files": {
             "pyproject.toml": '[project]\nname = "sample"\n',
             "shipwright_events.jsonl": events,
             ".shipwright/compliance/traceability-matrix.md": _RTM,
         }},
    ])


def _model_for(root: Path):
    target = resolve_target(str(root))
    return grade_context(RepoContext(target))


class TestAuthoritativeEndToEnd:
    def test_canonical_records_grade_authoritatively(self, tmp_path: Path):
        model = _model_for(_canonical_repo(tmp_path / "auth"))
        assert model.mode == "authoritative"
        assert model.gradeable is True
        # The stamp comes from the compliance adapter (event-log provenance).
        assert "shipwright_events.jsonl" in model.verified_from
        # A measurable dimension carries authoritative provenance, not a
        # heuristic "deferred to G2" placeholder.
        measurable = [d for d in model.dimensions if d.score is not None]
        assert measurable, "expected ≥1 measurable dimension"
        assert any(d.provenance.mode == "authoritative" for d in measurable)

    def test_valid_but_empty_records_fall_back_to_heuristic(self, tmp_path: Path):
        # Routing sees a VALID shape (JSON-lines events + RTM), but the log holds
        # no work_completed events and there are no requirements → nothing
        # authoritatively gradeable → heuristic.
        events = '{"type": "phase_started", "ts": "2024-01-02T09:00:00+00:00"}\n'
        model = _model_for(_canonical_repo(tmp_path / "empty", events=events))
        assert model.mode == "heuristic"

    def test_corrupt_event_log_falls_back_to_heuristic(self, tmp_path: Path):
        # A non-JSON first line → routing STATE_MALFORMED → heuristic (never
        # reaches ingestion).
        model = _model_for(_canonical_repo(tmp_path / "corrupt", events="not json\n"))
        assert model.mode == "heuristic"


class TestDogfoodGuard:
    """G6 dogfood guard: the monorepo + WebUI grade AUTHORITATIVELY (from their own
    ``.shipwright/`` records), so the G6 cold-repo projection calibration must not
    touch them. This pins that the authoritative path never invokes the projection
    heuristics G6 tuned — if it did, the monorepo's A could silently regress."""

    def test_authoritative_grade_never_runs_the_projection(self, tmp_path: Path, monkeypatch):
        root = _canonical_repo(tmp_path / "auth")
        baseline = _model_for(root)
        assert baseline.mode == "authoritative"

        def boom(*_a, **_k):
            raise AssertionError(
                "an authoritative grade must not run the cold-repo projection")
        # Every G6-tuned signal flows through these two projection entry points;
        # sabotaging them proves the authoritative path bypasses the projection.
        monkeypatch.setattr(grade_inputs_projector, "compute_signals", boom)
        monkeypatch.setattr(grade_inputs_projector, "project_inputs", boom)
        after = _model_for(root)
        assert after == baseline  # byte-identical: G6 left the dogfood grade untouched


class TestFailSafe:
    """``try_authoritative_grade`` never raises and never grades off degenerate
    data — any failure returns ``None`` so the caller falls back."""

    _ROUTING = RoutingDecision(
        detected_mode="authoritative", effective_mode="heuristic",
        state="valid", reason="detected")

    def _ctx(self, tmp_path: Path) -> RepoContext:
        target = resolve_target(str(_canonical_repo(tmp_path / "ctx")))
        return RepoContext(target)

    def test_none_when_collect_all_raises(self, tmp_path: Path, monkeypatch):
        def boom(_root):
            raise RuntimeError("corrupt .shipwright/")
        monkeypatch.setattr(
            authoritative, "load_compliance_ingest",
            lambda: (boom, lambda data: None))
        engine = load_engine()
        assert authoritative.try_authoritative_grade(
            self._ctx(tmp_path), engine, self._ROUTING) is None

    def test_none_when_records_empty(self, tmp_path: Path, monkeypatch):
        empty = SimpleNamespace(work_events=[], requirements=[])
        monkeypatch.setattr(
            authoritative, "load_compliance_ingest",
            lambda: (lambda _root: empty, lambda data: None))
        engine = load_engine()
        assert authoritative.try_authoritative_grade(
            self._ctx(tmp_path), engine, self._ROUTING) is None

    def test_grade_context_falls_back_when_ingestion_returns_none(
        self, tmp_path: Path, monkeypatch
    ):
        # Routing detects authoritative, but ingestion declines → heuristic path.
        monkeypatch.setattr(
            grade_inputs_projector, "try_authoritative_grade",
            lambda *a, **k: None)
        model = _model_for(_canonical_repo(tmp_path / "fallthrough"))
        assert model.mode == "heuristic"


class TestEventLogSizeGuard:
    """A hostile clone could ship a giant event log to OOM the unbounded
    cross-plugin collect_all reader; the authoritative path refuses it and
    falls back to the byte-bounded heuristic projection."""

    def test_oversize_eventlog_falls_back_end_to_end(self, tmp_path: Path, monkeypatch):
        # Shrink the cap so the test log is "oversize" without writing 10 MB.
        monkeypatch.setattr(authoritative, "_MAX_AUTHORITATIVE_EVENTLOG_BYTES", 200)
        big = _WORK_EVENTS + ('{"type": "note", "pad": "%s"}\n' % ("x" * 500))
        model = _model_for(_canonical_repo(tmp_path / "big", events=big))
        assert model.mode == "heuristic"

    def test_eventlog_over_cap_detects_root_log(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(authoritative, "_MAX_AUTHORITATIVE_EVENTLOG_BYTES", 10)
        (tmp_path / "shipwright_events.jsonl").write_text("x" * 100, encoding="utf-8")
        assert authoritative._eventlog_over_cap(tmp_path) is True
        assert authoritative._eventlog_over_cap(tmp_path / "nonexistent") is False
