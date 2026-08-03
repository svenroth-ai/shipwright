"""Grade-snapshot emitter tests (M-Pre-3,
iterate-2026-07-10-grade-snapshot-events).

``emit_grade_snapshot`` appends a ``grade_snapshot`` event to the durable,
tracked ``shipwright_events.jsonl`` when a compliance dashboard regen MOVES the
Control Grade, so the WebUI Ship's-Log can trend it (the grade itself is a repo
aggregate the dashboard overwrites — no history survives).

Covers:
 * AC2 — a regen appends exactly one snapshot (RED before this iterate).
 * AC1 — a regen that changes nothing appends nothing; a changed grade appends
   (iterate-2026-08-01-grade-snapshot-dedup REVERSED the original
   "unconditionally, one per regen" contract after measuring that 34% of this
   repo's event log had become identical heartbeat snapshots).
 * Additive — a consumer that doesn't know the type ignores it gracefully.
 * Integration (composition) — update_compliance's dashboard branch actually
   wires the emitter, the event lands in the durable log, and a second regen
   over unchanged data adds nothing to it.
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


def _repo(root: Path) -> Path:
    """A one-commit git repo, so ``resolve_tree_lineage`` yields a real tree.

    The dedup deliberately refuses to compare records whose attribution is
    unresolvable, so a bare ``tmp_path`` (no repo → ``lineage="unknown"``) can
    never dedup — correct behaviour, but it means the wiring tests below have to
    run against an actual tree. Inlined rather than imported from
    ``shared/tests/_tree_lineage_fixtures``: that is a different pytest root and
    cross-root imports are what ADR-044 forbids. Identity and signing are pinned
    so the fixture never depends on the developer's global git config.
    """
    import subprocess

    root.mkdir(parents=True, exist_ok=True)
    def git(*args):
        subprocess.run(["git", "-C", str(root), *args], check=True,
                       capture_output=True)
    git("init", "-b", "main")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "user.name", "fixture")
    git("config", "commit.gpgsign", "false")
    (root / "one.txt").write_text("1", encoding="utf-8")
    git("add", "-A")
    git("commit", "-m", "one")
    return root


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

    def test_a_regen_that_changes_nothing_appends_nothing(self, tmp_path):  # AC1
        # REVERSED by iterate-2026-08-01-grade-snapshot-dedup. This used to
        # assert two regens → two snapshots, on the documented premise that "a
        # regen is an explicit act". Measurement falsified it (34% of this
        # repo's event log was grade snapshots; 47 identical records from 20
        # sessions on one day), so a repeat regen from the same tree now records
        # nothing. A CHANGED grade still appends — see the test below.
        tmp_path = _repo(tmp_path / "repo")
        first = emit_grade_snapshot(_gradeable_data(tmp_path))
        assert first["appended"] == 1

        second = emit_grade_snapshot(_gradeable_data(tmp_path))
        assert second["appended"] == 0
        assert second["reason"] == "unchanged_grade"
        assert second["grade"] == first["grade"]
        assert second == {
            "appended": 0,
            "reason": "unchanged_grade",
            "grade": first["grade"],
            "score": first["score"],
        }

        snaps = [e for e in _read_events(tmp_path) if e.get("type") == "grade_snapshot"]
        assert len(snaps) == 1

    def test_a_regen_whose_grade_changed_still_appends(self, tmp_path, monkeypatch):
        # AC2 — the other half of the contract: dedup must never swallow a real
        # move. Patched on the MODULE OBJECT (ADR-045), as the sibling
        # not-gradeable test does, so the branch is pinned rather than the
        # environment.
        from scripts.lib import _grade_snapshot as gs
        from scripts.lib.control_grade import GradeReport

        tmp_path = _repo(tmp_path / "repo")
        emit_grade_snapshot(_gradeable_data(tmp_path))
        regressed = GradeReport(
            gradeable=True, score=42.0, grade="F",
            verdict="Regressed", band_label="F",
        )
        monkeypatch.setattr(gs, "compute_grade", lambda inp: regressed)
        changed = gs.emit_grade_snapshot(_gradeable_data(tmp_path))

        assert changed["appended"] == 1
        snaps = [e for e in _read_events(tmp_path) if e.get("type") == "grade_snapshot"]
        assert len(snaps) == 2
        assert snaps[-1]["grade"] == "F"

    def test_snapshot_grade_matches_dashboard(self, tmp_path):
        # External-plan-review (OpenAI #1 / Gemini A): falsify the "recompute
        # diverges from the dashboard grade" risk. Both the dashboard render and
        # the emitter call the SAME deterministic compute_grade on the SAME
        # ComplianceData → the snapshot grade IS the grade the dashboard shows.
        from scripts.lib.compliance_report import generate
        data = _gradeable_data(tmp_path)
        result = emit_grade_snapshot(data)
        dashboard_md = generate(data)
        # Both the grade LETTER and the (int score)/100 the dashboard renders.
        assert f"Control Grade: **{result['grade']}**" in dashboard_md
        assert f"({int(result['score'])}/100)" in dashboard_md


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
        md_text = dashboard_md.read_text(encoding="utf-8")
        assert f"Control Grade: **{snaps[0]['grade']}**" in md_text
        assert f"({int(snaps[0]['score'])}/100)" in md_text

    def test_a_second_regen_over_unchanged_data_adds_nothing(
        self, tmp_path, monkeypatch, capsys,
    ):
        """category: integration — the dedup composes with the REAL regen loop.

        The unit tests drive ``emit_grade_snapshot`` directly. This drives
        ``update_compliance.main`` twice, so the dedup is exercised through the
        actual dashboard branch, the actual result-payload plumbing and the
        actual durable log — the place the 234 duplicate lines were produced.
        """
        tmp_path = _repo(tmp_path / "repo")
        (tmp_path / ".shipwright" / "compliance").mkdir(parents=True)
        data = _gradeable_data(tmp_path)
        monkeypatch.setattr(update_compliance, "collect_all", lambda pr: data)
        monkeypatch.setattr(sys, "argv", [
            "update_compliance.py",
            "--project-root", str(tmp_path),
            "--phase", "design",
        ])

        assert update_compliance.main() == 0
        assert json.loads(capsys.readouterr().out)["grade_snapshot"]["appended"] == 1

        assert update_compliance.main() == 0
        second = json.loads(capsys.readouterr().out)["grade_snapshot"]
        assert second["appended"] == 0
        assert second["reason"] == "unchanged_grade"

        snaps = [e for e in _read_events(tmp_path) if e.get("type") == "grade_snapshot"]
        assert len(snaps) == 1, "two regens over identical data are one data point"
