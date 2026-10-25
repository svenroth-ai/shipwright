"""A Brief package that changed since approval blocks resume / next / apply in code (B2 fix rounds)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

import phase_task_lifecycle  # noqa: E402,F401
from orchestrator import create_config  # noqa: E402
from orchestrator_pkg import brief_resume_guard  # noqa: E402
from orchestrator_pkg.single_session_cli import dispatch_single_session  # noqa: E402
from single_session.loop_state import init_loop_state, save_loop_state  # noqa: E402


def _package(project: Path) -> Path:
    """A valid approved package at ``project/brief`` (built inline: no shared test helper import)."""
    bp = brief_resume_guard._load()._lib("brief_package")
    dest = project / "brief"
    (dest / "mockups").mkdir(parents=True)
    files = {"brief.md": "# App\n\n## Capture note\nRequirement: x\n", "scope.md": "s\n", "visual-guidelines.md": "v\n",
             "mockups/01.html": "<html></html>\n",
             "screen-map.json": json.dumps({"screens": [{"id": "n", "mockup": "01.html"}]})}
    for rel, text in files.items():
        (dest / rel).write_text(text, encoding="utf-8")
    brief = {"version": bp.BRIEF_VERSION, "profile": "vite-hono", "deploy_target": "jelastic-dev",
             "autonomy": "guided", "ux_shape": "classic", "source_class": "synthetic", "scope": "scope.md",
             "design_system": "visual-guidelines.md", "brief_dir": "brief", "env_preflight": [],
             "allow_parallel_builders": False, "ui_host": "web",
             "approved_by": "human:sven", "approved_at": "2026-10-25T00:00:00Z"}
    (dest / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    brief["package_sha256"] = bp.package_sha256(dest)
    (dest / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    return dest


def _run(project: Path, *, with_package: bool = True):
    cfg = create_config("full_app", "vite-hono", "guided", "jelastic-dev", project, mode="single_session")
    save_loop_state(project, init_loop_state(cfg["runId"]))
    if with_package:
        _package(project)
        brief_resume_guard._load().record(project, "brief")
    return cfg


def _cmd(project: Path, command: str) -> int:
    ns = argparse.Namespace(command=command, confirm=False, result_json=str(project / "nope.json"),
                            override_reason=None)
    return dispatch_single_session(ns, project)


def _tamper(project: Path) -> None:
    (project / "brief" / "brief.md").write_text("# tampered\n", encoding="utf-8")


@pytest.mark.covers("FR-01.01")
def test_resume_proceeds_while_the_recorded_package_still_verifies(tmp_project, capsys):
    _run(tmp_project)
    assert _cmd(tmp_project, "single-session-resume") == 0
    assert json.loads(capsys.readouterr().out)["action"] == "resume"


@pytest.mark.covers("FR-01.01")
@pytest.mark.parametrize("command", ["single-session-resume", "single-session-next", "single-session-apply"])
def test_resume_next_and_apply_are_blocked_when_the_package_changed(tmp_project, capsys, command):
    _run(tmp_project)
    _tamper(tmp_project)
    assert _cmd(tmp_project, command) == 3
    out = json.loads(capsys.readouterr().out)
    assert out["refused"] is True and out["code"] == "hash_mismatch"


@pytest.mark.covers("FR-01.01")
def test_a_run_without_a_package_resumes_and_a_stray_package_only_warns(tmp_project, capsys):
    _run(tmp_project, with_package=False)
    _package(tmp_project)  # committed, but this run does not use it
    assert _cmd(tmp_project, "single-session-resume") == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["action"] == "resume"
    assert "WARNING" in captured.err and "brief/brief.json" in captured.err


@pytest.mark.covers("FR-01.01")
def test_a_missing_run_config_keeps_its_own_exit_code(tmp_project, capsys):
    assert _cmd(tmp_project, "single-session-next") == 1
    assert "no_config" in capsys.readouterr().out


@pytest.mark.covers("FR-01.01")
def test_the_guard_fails_closed_when_the_intake_module_is_missing(tmp_project, monkeypatch):
    _run(tmp_project)
    monkeypatch.setattr(brief_resume_guard, "_BDI", tmp_project / "gone.py")
    assert brief_resume_guard.refusal(tmp_project)["code"] == "intake_unavailable"
    plain = tmp_project / "plain"
    plain.mkdir()
    assert brief_resume_guard.refusal(plain) is None


@pytest.mark.covers("FR-01.01")
@pytest.mark.parametrize("exc,code", [(OSError("unreadable"), "io_error"), (KeyError("boom"), "internal_error")])
def test_unexpected_errors_while_verifying_are_a_structured_refusal(tmp_project, monkeypatch, exc, code):
    class _Boom:
        @staticmethod
        def verify_run_config(_root):
            raise exc

    monkeypatch.setattr(brief_resume_guard, "_load", lambda: _Boom)
    assert brief_resume_guard.refusal(tmp_project)["code"] == code
