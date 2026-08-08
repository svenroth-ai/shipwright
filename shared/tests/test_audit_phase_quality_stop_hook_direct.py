"""Direct in-process coverage for ``hooks.audit_phase_quality_on_stop.main``.

ADR-045: a Stop hook invoked via ``subprocess.run`` — the shape every other
test in ``test_audit_phase_quality.py`` uses, for real end-to-end fidelity —
is invisible to this process's own coverage measurement, so the
diff-coverage gate scores the whole module 0% covered even though the E2E
suite exercises it thoroughly. These call ``main()`` directly in-process
instead, trading "real separate process" fidelity for diff-coverage
visibility on a module the E2E suite already proves correct end to end.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import time
from pathlib import Path

import hooks.audit_phase_quality_on_stop as hook_mod
from lib import phase_quality as pq
from lib.worktree_isolation import write_run_pointer


def _shipwright_project(tmp_path: Path, *, run_id: str = "run-direct") -> Path:
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({
            "run_id": run_id,
            "current_step": "build",
            "completed_steps": ["project", "design", "plan"],
        }),
        encoding="utf-8",
    )
    events = [
        {"type": "phase_completed", "phase": "build", "timestamp": "2026-04-18T12:00:00Z"},
    ]
    (tmp_path / "shipwright_events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8",
    )
    (tmp_path / ".shipwright" / "agent_docs" / "build_dashboard.md").write_text(
        "# Dashboard\n\n## build\nsection complete\n", encoding="utf-8",
    )
    handoff = tmp_path / ".shipwright" / "agent_docs" / "session_handoff.md"
    handoff.write_text("# Session Handoff\n\nReason: build: finalize\n", encoding="utf-8")
    now = time.time()
    os.utime(handoff, (now, now))
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- initial build bullet\n", encoding="utf-8",
    )
    (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").write_text(
        "## ADR-001: build decision\n\n**Status:** Accepted\n\nBody.\n", encoding="utf-8",
    )
    return tmp_path


def _run_main(
    monkeypatch, project: Path, *, session_id: str = "sess-direct", plugin_root: str = "shipwright-build",
) -> int:
    monkeypatch.chdir(project)
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", f"/fake/plugins/{plugin_root}")
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", session_id)
    monkeypatch.delenv("SHIPWRIGHT_PHASE_QUALITY", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_PROJECT_ROOT", raising=False)
    return hook_mod.main()


def test_main_writes_findings_and_aggregates_in_process(tmp_path: Path, monkeypatch):
    project = _shipwright_project(tmp_path)
    rc = _run_main(monkeypatch, project)
    assert rc == 0
    finding_dir = project / pq.FINDING_DIR
    assert finding_dir.is_dir()
    phases = {json.loads(p.read_text(encoding="utf-8"))["phase"] for p in finding_dir.glob("*.json")}
    assert phases == {"project", "design", "plan", "build"}
    assert (project / pq.REPORT_PATH).exists()
    assert (project / pq.SUMMARY_PATH).exists()
    assert (project / pq.DASHBOARD_PATH).exists()


def test_main_greenfield_noop_in_process(tmp_path: Path, monkeypatch):
    rc = _run_main(monkeypatch, tmp_path)
    assert rc == 0
    assert not (tmp_path / pq.FINDING_DIR).exists()


def test_main_disabled_by_env_flag_in_process(tmp_path: Path, monkeypatch):
    project = _shipwright_project(tmp_path)
    monkeypatch.chdir(project)
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    monkeypatch.setenv("SHIPWRIGHT_PHASE_QUALITY", "0")
    rc = hook_mod.main()
    assert rc == 0
    assert not (project / pq.FINDING_DIR).exists()


def test_main_unrecognized_plugin_root_noop_in_process(tmp_path: Path, monkeypatch):
    project = _shipwright_project(tmp_path)
    rc = _run_main(monkeypatch, project, plugin_root="unrelated")
    assert rc == 0
    assert not (project / pq.FINDING_DIR).exists()


def test_main_renders_both_roots_when_pointer_redirects(tmp_path: Path, monkeypatch):
    """The render-both-roots fix (code-review finding #6): when a verified
    pointer redirects `audit_root` away from `plain_root`, BOTH trees'
    dashboards must refresh, not just the redirected worktree's."""
    main_root = tmp_path / "main"
    _shipwright_project(main_root, run_id="run-a")
    subprocess.run(["git", "init", "-q"], cwd=str(main_root), check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=str(main_root), check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(main_root), check=True)
    subprocess.run(["git", "add", "-A"], cwd=str(main_root), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(main_root), check=True)

    worktree = main_root / ".worktrees" / "demo"
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", "demo", str(worktree)],
        cwd=str(main_root), check=True,
    )
    _shipwright_project(worktree, run_id="run-a")
    write_run_pointer(
        main_root, run_id="run-a", slug="demo", branch="demo",
        worktree_path=worktree, session_id="sess-direct",
    )

    rc = _run_main(monkeypatch, main_root)

    assert rc == 0
    assert (worktree / pq.REPORT_PATH).exists()
    assert (main_root / pq.REPORT_PATH).exists()


def test_main_one_bad_phase_does_not_abort_the_rest_in_process(tmp_path: Path, monkeypatch):
    """A per-phase crash must land an error finding for that phase and keep
    auditing the rest — the module's own defense-in-depth contract."""
    project = _shipwright_project(tmp_path)

    def boom(*_args, **_kwargs):
        raise RuntimeError("simulated canon-check failure")

    monkeypatch.setattr(hook_mod.pq, "run_canon_checks", boom)

    rc = _run_main(monkeypatch, project)

    assert rc == 0
    finding_dir = project / pq.FINDING_DIR
    findings = {json.loads(p.read_text(encoding="utf-8"))["phase"]: json.loads(p.read_text(encoding="utf-8"))
                for p in finding_dir.glob("*.json")}
    assert set(findings) == {"project", "design", "plan", "build"}
    for data in findings.values():
        assert data.get("source") == "error"
