"""The plan boundary gate judges only this session's changes (FR-01.03 #7, e2e run 22).

Run 22's Plan phase found 63 uncommitted files from the Project and Design phases and
asked whether to commit them. setup-planning-session.py now records a baseline of what is
already dirty, and ``--gate boundary`` reports only paths new or changed since then.
In-process (diff coverage), the same way the design gate's baseline is tested.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.covers("FR-01.03/AC17")

_CHECKS = Path(__file__).resolve().parent.parent / "scripts" / "checks"


def _load(name: str, alias: str):
    spec = importlib.util.spec_from_file_location(alias, _CHECKS / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture()
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "run-plan")
    root = tmp_path / "proj"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / "README.md").write_text("x\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    # what the Project and Design phases left uncommitted
    (root / "backend").mkdir()
    (root / "backend" / "server.py").write_text("print('scaffold')\n", encoding="utf-8")
    (root / "package.json").write_text("{}\n", encoding="utf-8")
    spec = root / ".shipwright" / "planning" / "01-a" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("# Spec\n\nDo the thing.\n", encoding="utf-8")
    return root


def _setup(project: Path, monkeypatch, capsys) -> dict:
    setup = _load("setup-planning-session.py", "_plan_setup_inproc")
    spec = project / ".shipwright" / "planning" / "01-a" / "spec.md"
    monkeypatch.setattr(sys, "argv", ["setup-planning-session.py", "--file", str(spec),
                                      "--plugin-root", str(_CHECKS.parent.parent), "--project-root", str(project)])
    assert setup.main() == 0
    return json.loads(capsys.readouterr().out)


def test_earlier_phase_output_does_not_trip_the_gate(project, monkeypatch, capsys):
    assert _setup(project, monkeypatch, capsys)["boundary_baseline"] == "written"
    assert (project / ".shipwright" / "plan-boundary-baseline-01-a.json").is_file()
    gates = _load("check-plan-gates.py", "_plan_gates_inproc")
    gate = gates.boundary_gate(project, "01-a")
    assert gate["ok"] is True, gate


def test_a_production_write_after_the_baseline_still_fails(project, monkeypatch, capsys):
    _setup(project, monkeypatch, capsys)
    (project / "backend" / "server.py").write_text("print('plan wrote code')\n", encoding="utf-8")
    (project / "src.py").write_text("x = 1\n", encoding="utf-8")
    gate = _load("check-plan-gates.py", "_plan_gates_inproc2").boundary_gate(project, "01-a")
    assert gate["ok"] is False
    assert sorted(p.split(": ", 1)[1] for p in gate["problems"]) == ["backend/server.py", "src.py"]


def test_a_resume_keeps_the_baseline_and_without_one_the_gate_is_strict(project, monkeypatch, capsys):
    gates = _load("check-plan-gates.py", "_plan_gates_inproc3")
    assert gates.boundary_gate(project, "01-a")["ok"] is False  # no baseline: whole dirty tree, as before
    _setup(project, monkeypatch, capsys)
    assert _setup(project, monkeypatch, capsys)["boundary_baseline"] == "kept"
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "another-run")
    assert gates.boundary_gate(project, "01-a")["ok"] is False  # another run's baseline is not trusted


def test_a_project_root_that_is_not_the_repo_top_is_not_written(tmp_path, monkeypatch, capsys):
    spec = tmp_path / ".shipwright" / "planning" / "01-a" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("# Spec\n", encoding="utf-8")
    setup = _load("setup-planning-session.py", "_plan_setup_inproc2")
    monkeypatch.setattr(sys, "argv", ["setup-planning-session.py", "--file", str(spec),
                                      "--plugin-root", str(_CHECKS.parent.parent), "--project-root", str(tmp_path)])
    assert setup.main() == 0
    assert json.loads(capsys.readouterr().out)["boundary_baseline"] == "not_written"


def test_the_next_split_takes_a_fresh_baseline_after_a_build_in_the_same_run(project, monkeypatch, capsys):
    """plan/01 -> build/01 -> plan/02 share one run id: plan/02 must not inherit plan/01's snapshot."""
    _setup(project, monkeypatch, capsys)
    # build/01 commits part of the tree, edits a Project file and leaves new output uncommitted
    _git(project, "add", "backend")
    _git(project, "commit", "-q", "-m", "build 01")
    (project / "package.json").write_text('{"devDependencies": {}}\n', encoding="utf-8")
    (project / "board.js").write_text("// build 01\n", encoding="utf-8")
    spec2 = project / ".shipwright" / "planning" / "02-b" / "spec.md"
    spec2.parent.mkdir(parents=True)
    spec2.write_text("# Spec 2\n", encoding="utf-8")
    setup = _load("setup-planning-session.py", "_plan_setup_inproc3")
    monkeypatch.setattr(sys, "argv", ["setup-planning-session.py", "--file", str(spec2),
                                      "--plugin-root", str(_CHECKS.parent.parent), "--project-root", str(project)])
    assert setup.main() == 0
    assert json.loads(capsys.readouterr().out)["boundary_baseline"] == "written"
    gates = _load("check-plan-gates.py", "_plan_gates_inproc4")
    assert gates.boundary_gate(project, "02-b")["ok"] is True
    assert gates.boundary_gate(project, "01-a")["ok"] is False  # another split's gate does not trust it
