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
import subprocess
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


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, encoding="utf-8", check=False)
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout.strip()


def _git_commit(root: Path, name: str) -> None:
    (root / name).write_text(name, encoding="utf-8")
    _git(root, "add", name)
    _git(root, "commit", "-m", f"add {name}")


def _git_repo(root: Path) -> Path:
    """A real repo on ``main`` with one commit — attribution is resolved from
    git, so a fixture that fakes it would prove nothing about the producer."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "fixture")
    _git(root, "config", "commit.gpgsign", "false")
    _git_commit(root, "one.txt")
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
        # Both the grade LETTER and the (int score)/100 the dashboard renders.
        assert f"Control Grade: **{result['grade']}**" in dashboard_md
        assert f"({int(result['score'])}/100)" in dashboard_md


class TestEmitterAttributesTheTree:
    """Every emitted snapshot names the tree it measured
    (iterate-2026-07-28-grade-snapshot-lineage).

    Without this, snapshots from many worktrees union-merge onto ``main`` as one
    indistinguishable timeline, and the Ship's-Log sparkline plots a mixture of
    subjects as if it were one project's trend.
    """

    def test_snapshot_from_a_real_repo_names_its_branch_and_base(self, tmp_path):
        root = _git_repo(tmp_path / "repo")
        _git(root, "checkout", "-b", "iterate/x")
        _git_commit(root, "two.txt")

        result = emit_grade_snapshot(_gradeable_data(root))

        event = [e for e in _read_events(root) if e.get("type") == "grade_snapshot"][0]
        assert event["lineage"] == "branch"
        assert event["branch"] == "iterate/x"
        assert event["base"] == _git(root, "rev-parse", "main")
        # The caller's payload reports it too, so a regen's own output says
        # which tree it just measured.
        assert result["lineage"] == "branch"

    def test_snapshot_on_the_default_branch_is_main_lineage(self, tmp_path):
        root = _git_repo(tmp_path / "repo")

        emit_grade_snapshot(_gradeable_data(root))

        event = [e for e in _read_events(root) if e.get("type") == "grade_snapshot"][0]
        assert event["lineage"] == "main"
        assert event["branch"] == "main"

    def test_unresolvable_tree_still_emits_an_explicitly_unknown_snapshot(self, tmp_path):
        # tmp_path is not a git repo. The snapshot must still land — attribution
        # is metadata, not a precondition — and must say "unknown" out loud,
        # because an ABSENT lineage is reserved for events written before
        # attribution existed.
        result = emit_grade_snapshot(_gradeable_data(tmp_path))
        assert result["appended"] == 1

        event = [e for e in _read_events(tmp_path) if e.get("type") == "grade_snapshot"][0]
        assert event["lineage"] == "unknown"
        assert "branch" not in event

    def test_a_raising_resolver_never_costs_us_the_snapshot(self, tmp_path, monkeypatch):
        # The regen must survive a broken git the same way it survives every
        # other degraded input: with a recorded, honest gap.
        import grade_snapshot_shape

        def _boom(_root):
            raise RuntimeError("git exploded")

        monkeypatch.setattr(grade_snapshot_shape, "resolve_tree_lineage", _boom)

        assert emit_grade_snapshot(_gradeable_data(tmp_path))["appended"] == 1
        event = [e for e in _read_events(tmp_path) if e.get("type") == "grade_snapshot"][0]
        assert event["lineage"] == "unknown"
        assert event["grade"]


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

    def test_regen_in_a_branch_tree_lands_an_attributed_snapshot(
        self, tmp_path, monkeypatch, capsys,
    ):
        """category: integration — the whole chain, in a tree that is NOT main.

        This is the defect's actual shape: a compliance regen running inside an
        iterate worktree, on a branch, whose event then union-merges onto
        ``main``. Three components have to compose for the fix to hold — the
        update_compliance dashboard branch, the emitter, and the git resolver —
        and each of them passes its own unit tests while still producing an
        unattributed event if the wiring between them is wrong.
        """
        root = _git_repo(tmp_path / "repo")
        (root / ".shipwright" / "compliance").mkdir(parents=True)
        _git(root, "checkout", "-b", "iterate/lineage-demo")
        _git_commit(root, "two.txt")
        branch_point = _git(root, "rev-parse", "main")

        data = _gradeable_data(root)
        monkeypatch.setattr(update_compliance, "collect_all", lambda pr: data)
        monkeypatch.setattr(sys, "argv", [
            "update_compliance.py", "--project-root", str(root), "--phase", "design",
        ])
        assert update_compliance.main() == 0

        payload = json.loads(capsys.readouterr().out)
        assert payload["grade_snapshot"]["lineage"] == "branch"

        snaps = [e for e in _read_events(root) if e.get("type") == "grade_snapshot"]
        assert len(snaps) == 1
        assert snaps[0]["lineage"] == "branch"
        assert snaps[0]["branch"] == "iterate/lineage-demo"
        # `base` names the main commit this tree extends — NOT its own HEAD,
        # which is the whole reason `commit` was unusable here.
        assert snaps[0]["base"] == branch_point
        assert snaps[0]["base"] != _git(root, "rev-parse", "HEAD")
