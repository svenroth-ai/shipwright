"""Boundary gate vs earlier phases' uncommitted output (finding F1, FR-01.04 #11)."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests import test_check_design_gates as _gates

_git, _git_init, _problems, run_gates = _gates._git, _gates._git_init, _gates._problems, _gates.run_gates
project = _gates.project

_LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib" / "boundary_baseline.py"


# --- boundary (#11): earlier phases' uncommitted output (F1) ---------------

SETUP_SCRIPT = str(
    Path(__file__).resolve().parent.parent / "scripts" / "checks" / "setup-design-session.py"
)


def _start_session(project: Path) -> None:
    proc = subprocess.run(
        [sys.executable, SETUP_SCRIPT, "--project-root", str(project), "--plugin-root", str(project)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert json.loads(proc.stdout)["success"] is True, proc.stdout + proc.stderr


def _project_phase_output(project: Path) -> None:
    (project / "src").mkdir(exist_ok=True)
    (project / "src" / "app.py").write_text("print('from the project phase')\n", encoding="utf-8")


@pytest.mark.covers("FR-01.04/AC12")
def test_uncommitted_output_of_an_earlier_phase_does_not_trip_the_boundary(project):
    _git_init(project)
    _project_phase_output(project)
    _start_session(project)
    code, out = run_gates(project, "boundary")
    assert code == 0, out


@pytest.mark.covers("FR-01.04/AC12")
def test_a_change_this_session_makes_outside_the_allowed_paths_still_fails(project):
    _git_init(project)
    _project_phase_output(project)
    _start_session(project)
    (project / "src" / "other.py").write_text("print('design wrote this')\n", encoding="utf-8")
    code, out = run_gates(project, "boundary")
    assert code == 1
    problems = _problems(out, "boundary")
    assert any("src/other.py" in p for p in problems)
    assert not any("src/app.py" in p for p in problems)


@pytest.mark.covers("FR-01.04/AC12")
def test_editing_an_earlier_phases_dirty_file_this_session_still_fails(project):
    _git_init(project)
    _project_phase_output(project)
    _start_session(project)
    (project / "src" / "app.py").write_text("print('design edited it')\n", encoding="utf-8")
    code, out = run_gates(project, "boundary")
    assert code == 1
    assert any("src/app.py" in p for p in _problems(out, "boundary"))


@pytest.mark.covers("FR-01.04/AC12")
def test_without_a_session_baseline_the_boundary_stays_strict(project):
    _git_init(project)
    _project_phase_output(project)
    assert run_gates(project, "boundary")[0] == 1


@pytest.mark.covers("FR-01.04/AC12")
def test_restoring_an_earlier_phases_dirty_file_to_head_this_session_still_fails(project):
    _git_init(project)
    _project_phase_output(project)
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "init")
    (project / "src" / "app.py").write_text("print('dirty from the project phase')\n", encoding="utf-8")
    _start_session(project)
    _git(project, "checkout", "--", "src/app.py")  # clean again, content moved
    code, out = run_gates(project, "boundary")
    assert code == 1
    assert any("src/app.py" in p for p in _problems(out, "boundary"))


@pytest.mark.covers("FR-01.04/AC12")
def test_the_baseline_file_itself_is_not_a_boundary_violation(project):
    _git_init(project)
    _start_session(project)
    assert (project / ".shipwright" / "design-boundary-baseline.json").is_file()
    assert run_gates(project, "boundary")[0] == 0


@pytest.mark.covers("FR-01.04/AC12")
def test_a_corrupt_baseline_falls_back_to_strict_not_a_traceback(project):
    _git_init(project)
    _project_phase_output(project)
    _start_session(project)
    (project / ".shipwright" / "design-boundary-baseline.json").write_text("{not json", encoding="utf-8")
    code, out = run_gates(project, "boundary")
    assert code == 1
    assert any("src/app.py" in p for p in _problems(out, "boundary"))


@pytest.mark.covers("FR-01.04/AC12")
def test_a_deleted_earlier_phase_file_stays_exempt_but_a_new_deletion_does_not(project):
    _git_init(project)
    (project / "src").mkdir()
    (project / "src" / "a.py").write_text("a\n", encoding="utf-8")
    (project / "src" / "b.py").write_text("b\n", encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "init")
    (project / "src" / "a.py").unlink()  # the project phase deleted a.py
    _start_session(project)
    assert run_gates(project, "boundary")[0] == 0
    (project / "src" / "b.py").unlink()  # design deletes b.py
    code, out = run_gates(project, "boundary")
    assert code == 1
    problems = _problems(out, "boundary")
    assert any("src/b.py" in p for p in problems) and not any("src/a.py" in p for p in problems)


@pytest.mark.covers("FR-01.04/AC12")
def test_a_second_setup_at_the_same_commit_does_not_launder_the_sessions_own_writes(project):
    _git_init(project)
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "init")
    _start_session(project)
    (project / "src").mkdir()
    (project / "src" / "design_wrote.py").write_text("x\n", encoding="utf-8")
    _start_session(project)  # resume: must keep the original baseline
    code, out = run_gates(project, "boundary")
    assert code == 1
    assert any("src/design_wrote.py" in p for p in _problems(out, "boundary"))


@pytest.mark.covers("FR-01.04/AC12")
def test_an_already_dirty_file_with_a_space_or_non_ascii_name_is_still_caught_when_edited(project):
    _git_init(project)
    (project / "src").mkdir()
    for name in ("my file.py", "k\u00e4se.py"):
        (project / "src" / name).write_text("project phase\n", encoding="utf-8")
    _start_session(project)
    assert run_gates(project, "boundary")[0] == 0
    (project / "src" / "my file.py").write_text("design edited\n", encoding="utf-8")
    code, out = run_gates(project, "boundary")
    assert code == 1
    assert any("my file.py" in p for p in _problems(out, "boundary"))
    assert not any("se.py" in p for p in _problems(out, "boundary"))


# --- in-process unit tests of lib/boundary_baseline.py ---------------------


def _lib():
    spec = importlib.util.spec_from_file_location("_bb_under_test", _LIB)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.covers("FR-01.04/AC12")
def test_dirty_paths_reports_both_sides_of_a_rename_and_verbatim_names(tmp_path):
    _git_init(tmp_path)
    (tmp_path / "a b.py").write_text("x\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    _git(tmp_path, "mv", "a b.py", "c.py")
    (tmp_path / "k\u00e4se.py").write_text("y\n", encoding="utf-8")
    assert {"a b.py", "c.py", "k\u00e4se.py"} <= set(_lib().dirty_paths(tmp_path))


@pytest.mark.covers("FR-01.04/AC12")
def test_dirty_paths_is_empty_outside_a_git_worktree(tmp_path):
    assert _lib().dirty_paths(tmp_path) == []


@pytest.mark.covers("FR-01.04/AC12")
def test_unreadable_path_never_equals_a_baseline_and_a_directory_is_unreadable(tmp_path):
    (tmp_path / "sub").mkdir()
    lib = _lib()
    assert lib.fingerprint(tmp_path, "sub") is None
    assert lib.fingerprint(tmp_path, "missing.txt") == "<deleted>"


@pytest.mark.covers("FR-01.04/AC12")
def test_setup_reports_whether_the_baseline_was_written_or_kept(project):
    _git_init(project)
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "init")

    def setup() -> dict:
        proc = subprocess.run(
            [sys.executable, SETUP_SCRIPT, "--project-root", str(project), "--plugin-root", str(project)],
            capture_output=True, text=True, encoding="utf-8",
        )
        return json.loads(proc.stdout)

    assert setup()["boundary_baseline"] == "written"
    assert setup()["boundary_baseline"] == "kept"


@pytest.mark.covers("FR-01.04/AC12")
def test_a_resume_in_a_repo_with_no_commit_yet_keeps_the_baseline(project):
    _git_init(project)  # unborn HEAD
    _start_session(project)
    (project / "src").mkdir()
    (project / "src" / "x.py").write_text("x\n", encoding="utf-8")
    _start_session(project)
    code, out = run_gates(project, "boundary")
    assert code == 1
    assert any("src/x.py" in p for p in _problems(out, "boundary"))


@pytest.mark.covers("FR-01.04/AC12")
def test_the_skill_runs_the_baseline_cli_and_it_works_without_creating_designs_dir(project, tmp_path):
    skill = (Path(__file__).resolve().parent.parent / "skills" / "design" / "SKILL.md").read_text(encoding="utf-8")
    assert "scripts/lib/boundary_baseline.py" in skill and "--project-root" in skill
    root = tmp_path / "fresh"
    root.mkdir()
    _git_init(root)
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("x\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(_LIB), "--project-root", str(root)],
                          capture_output=True, text=True, encoding="utf-8")
    assert json.loads(proc.stdout) == {"boundary_baseline": "written"}
    assert not (root / ".shipwright" / "designs").exists()
    assert run_gates(root, "boundary")[0] == 0
