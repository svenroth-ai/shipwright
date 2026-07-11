"""Grade-snapshot emitter tests (M-Pre-3,
iterate-2026-07-10-grade-snapshot-events).

``emit_grade_snapshot`` appends one ``grade_snapshot`` event to the durable,
tracked ``shipwright_events.jsonl`` per compliance dashboard regen so the WebUI
Ship's-Log can trend the Control Grade (today the grade is a repo aggregate the
dashboard overwrites — no history survives).

Covers:
 * AC2 — a regen appends exactly one snapshot (RED before this iterate).
 * AC1 — one snapshot PER regen, unconditionally (documented idempotency).
 * Additive — a consumer that doesn't know the type ignores it gracefully.
 * Integration (composition) — update_compliance's dashboard branch actually
   wires the emitter, and the event lands in the durable log.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.lib.collectors.change_history import collect_events
from scripts.lib.data_collector import ComplianceData, DependencyInfo
from scripts.lib._grade_snapshot import emit_grade_snapshot

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

import scripts.tools.update_compliance as update_compliance  # noqa: E402


def _read_events(root: Path) -> list[dict]:
    path = root / "shipwright_events.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(ln)
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]


def _gradeable_data(root: Path) -> ComplianceData:
    """ComplianceData whose report is gradeable: one declared dependency makes
    the dependency-hygiene dimension measurable → a letter + score to trend."""
    return ComplianceData(
        project_root=root,
        dependencies=[DependencyInfo("left-pad", "1.0.0", "runtime", "MIT")],
        timestamp="2026-07-10T00:00:00Z",
    )


class TestEmitGradeSnapshot:
    def test_appends_exactly_one_event(self, tmp_path):  # AC2
        result = emit_grade_snapshot(_gradeable_data(tmp_path))
        assert result["appended"] == 1

        snaps = [e for e in _read_events(tmp_path) if e.get("type") == "grade_snapshot"]
        assert len(snaps) == 1
        event = snaps[0]
        assert event["grade"] == result["grade"]
        assert event["score"] == result["score"]
        assert event["ts"]
        assert event["id"].startswith("evt-")

    def test_not_gradeable_repo_emits_nothing(self, tmp_path, monkeypatch):
        # A Not-Gradeable report (no measurable dimension) has no letter/score
        # to trend → the emitter skips cleanly, appending nothing. Forced
        # deterministically (an empty repo can still be gradeable via the bloat
        # scan, so we pin the branch, not the environment).
        from scripts.lib import _grade_snapshot as gs
        from scripts.lib.control_grade import GradeReport

        not_gradeable = GradeReport(
            gradeable=False, score=None, grade="?",
            verdict="Not gradeable", band_label="Not gradeable",
        )
        monkeypatch.setattr(gs, "compute_grade", lambda inp: not_gradeable)
        result = gs.emit_grade_snapshot(_gradeable_data(tmp_path))
        assert result["appended"] == 0
        assert result["reason"] == "not_gradeable"
        assert _read_events(tmp_path) == []

    def test_each_regen_appends_another_snapshot(self, tmp_path):  # AC1 contract
        # One snapshot PER regen, unconditionally — two regens → two snapshots
        # (the trend cadence; the WebUI dedupes consecutive identical points).
        emit_grade_snapshot(_gradeable_data(tmp_path))
        emit_grade_snapshot(_gradeable_data(tmp_path))
        snaps = [e for e in _read_events(tmp_path) if e.get("type") == "grade_snapshot"]
        assert len(snaps) == 2

    def test_snapshot_grade_matches_dashboard(self, tmp_path):
        # External-plan-review (OpenAI #1 / Gemini A): falsify the "recompute
        # diverges from the dashboard grade" risk. Both the dashboard render and
        # the emitter call the SAME deterministic compute_grade on the SAME
        # ComplianceData → the snapshot grade IS the grade the dashboard shows.
        from scripts.lib.compliance_report import generate
        data = _gradeable_data(tmp_path)
        result = emit_grade_snapshot(data)
        dashboard_md = generate(data)
        assert f"Control Grade: **{result['grade']}**" in dashboard_md


class TestAdditiveConsumer:
    """Reverse drift-protection: a consumer that doesn't know grade_snapshot
    must skip it gracefully (never crash, never mis-count it as work)."""

    def test_change_history_collector_ignores_grade_snapshot(self, tmp_path):
        log = tmp_path / "shipwright_events.jsonl"
        log.write_text(
            json.dumps({
                "v": 1, "id": "evt-w0000001", "ts": "2026-07-10T00:00:00Z",
                "type": "work_completed", "source": "iterate", "commit": "abc",
                "tests": {"passed": 3, "total": 3},
            }) + "\n"
            + json.dumps({
                "v": 1, "id": "evt-g0000001", "ts": "2026-07-10T00:01:00Z",
                "type": "grade_snapshot", "grade": "A", "score": 95.0,
            }) + "\n",
            encoding="utf-8",
        )
        work_events, test_runs, phase_events = collect_events(tmp_path)
        # The grade_snapshot is silently ignored; only the work event collected.
        assert [w.id for w in work_events] == ["evt-w0000001"]
        assert test_runs == []
        assert phase_events == []


class TestComplianceRegenComposition:
    """category: integration — compliance dashboard regen → grade_snapshot event.

    Exercises the REAL update_compliance loop (its ``dashboard`` branch) end to
    end, proving the collector-regen and the event-emitter compose rather than
    each merely working in isolation.
    """

    def test_dashboard_regen_emits_snapshot(self, tmp_path, monkeypatch, capsys):
        (tmp_path / ".shipwright" / "compliance").mkdir(parents=True)
        data = _gradeable_data(tmp_path)
        # Deterministic gradeable input, independent of on-disk spec parsing.
        monkeypatch.setattr(update_compliance, "collect_all", lambda pr: data)
        monkeypatch.setattr(sys, "argv", [
            "update_compliance.py",
            "--project-root", str(tmp_path),
            "--phase", "design",  # PHASE_REPORTS["design"] == ["dashboard"]
        ])
        rc = update_compliance.main()
        assert rc == 0

        payload = json.loads(capsys.readouterr().out)
        assert payload["grade_snapshot"]["appended"] == 1

        # Dashboard regenerated ...
        dashboard_md = (tmp_path / ".shipwright" / "compliance" / "dashboard.md")
        assert dashboard_md.exists()
        # ... and exactly one grade_snapshot composed into the durable log.
        snaps = [e for e in _read_events(tmp_path) if e.get("type") == "grade_snapshot"]
        assert len(snaps) == 1
        assert snaps[0]["grade"]
        assert snaps[0]["score"] is not None
        # Real-flow parity (external code-review OpenAI #2/#3): the snapshot grade
        # IS the grade in the regenerated dashboard ARTIFACT. update_compliance
        # collects `data` once and feeds the SAME object to both the dashboard
        # render and the emitter, so the logged grade cannot diverge from what
        # the dashboard shows for that regen.
        assert f"Control Grade: **{snaps[0]['grade']}**" in dashboard_md.read_text(encoding="utf-8")
