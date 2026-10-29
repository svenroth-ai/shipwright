"""In-process coverage of the boundary baseline (FR-01.04 #11, finding F1).

The sibling file drives the gate through subprocesses, which diff-coverage
cannot see; these call the module objects directly.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from tests import test_check_design_gates as _gates

_git, _git_init = _gates._git, _gates._git_init
project = _gates.project

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def bb():
    return _load(_SCRIPTS / "lib" / "boundary_baseline.py", "_bb_inproc")


def _dirty(project: Path) -> None:
    (project / "src").mkdir(exist_ok=True)
    (project / "src" / "app.py").write_text("print('earlier phase')\n", encoding="utf-8")


@pytest.mark.covers("FR-01.04/AC12")
def test_session_changes_exempts_earlier_output_and_reports_a_new_write(bb, project):
    _git_init(project)
    _dirty(project)
    assert bb.write_baseline(project) is True
    assert "src/app.py" not in bb.session_changes(project)
    (project / "src" / "other.py").write_text("x = 1\n", encoding="utf-8")
    assert "src/other.py" in bb.session_changes(project)


@pytest.mark.covers("FR-01.04/AC12")
def test_an_edit_to_an_earlier_file_and_a_new_deletion_are_reported(bb, project):
    _git_init(project)
    _dirty(project)
    bb.write_baseline(project)
    (project / "src" / "app.py").write_text("print('edited')\n", encoding="utf-8")
    assert "src/app.py" in bb.session_changes(project)
    (project / "src" / "app.py").unlink()
    assert "src/app.py" in bb.session_changes(project)


@pytest.mark.covers("FR-01.04/AC12")
def test_a_second_write_at_the_same_commit_keeps_the_first_baseline(bb, project):
    _git_init(project)
    _dirty(project)
    assert bb.write_baseline(project) is True
    first = (project / bb.BASELINE_REL).read_text(encoding="utf-8")
    (project / "src" / "late.py").write_text("y = 2\n", encoding="utf-8")
    assert bb.write_baseline(project) is False
    assert (project / bb.BASELINE_REL).read_text(encoding="utf-8") == first
    assert "src/late.py" in bb.session_changes(project)


@pytest.mark.covers("FR-01.04/AC12")
def test_a_new_commit_carries_the_old_baseline_forward(bb, project):
    _git_init(project)
    _dirty(project)
    bb.write_baseline(project)
    first = json.loads((project / bb.BASELINE_REL).read_text(encoding="utf-8"))
    (project / "src" / "app.py").write_text("print('design edited before the commit')\n", encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "commit", "-q", "-m", "earlier output")
    assert bb.write_baseline(project) is True
    second = json.loads((project / bb.BASELINE_REL).read_text(encoding="utf-8"))
    assert second["head"] != first["head"]
    assert second["salt"] == first["salt"]
    assert second["dirty"]["src/app.py"] == first["dirty"]["src/app.py"]
    assert "src/app.py" in bb.session_changes(project)  # the pre-commit edit is not laundered


@pytest.mark.covers("FR-01.04/AC12")
def test_a_file_first_dirtied_after_the_baseline_stays_reported_across_a_commit(bb, project):
    _git_init(project)
    bb.write_baseline(project)
    (project / "src").mkdir(exist_ok=True)
    (project / "src" / "late.py").write_text("x = 1\n", encoding="utf-8")
    (project / "other.txt").write_text("o\n", encoding="utf-8")
    _git(project, "add", "other.txt")
    _git(project, "commit", "-q", "-m", "unrelated")
    bb.write_baseline(project)
    assert "src/late.py" in bb.session_changes(project)


@pytest.mark.covers("FR-01.04/AC12")
def test_a_baseline_of_another_run_is_neither_kept_nor_trusted(bb, project, monkeypatch):
    _git_init(project)
    _dirty(project)
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "run-a")
    assert bb.write_baseline(project) is True
    first = json.loads((project / bb.BASELINE_REL).read_text(encoding="utf-8"))
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "run-b")
    assert "src/app.py" in bb.session_changes(project)  # stale baseline: strict
    assert bb.write_baseline(project) is True  # same HEAD, other run: fresh
    second = json.loads((project / bb.BASELINE_REL).read_text(encoding="utf-8"))
    assert second["run"] == "run-b" and second["salt"] != first["salt"]
    assert "src/app.py" not in bb.session_changes(project)


@pytest.mark.covers("FR-01.04/AC12")
def test_a_subdirectory_project_root_fails_closed(bb, project):
    _git_init(project)
    _dirty(project)
    sub = project / "src"
    assert bb.at_repo_root(project) and not bb.at_repo_root(sub)
    assert bb.write_baseline(sub) is False
    assert not (sub / bb.BASELINE_REL).exists()
    # even with a baseline present, a non-root project root stays strict
    bb.write_baseline(project)
    assert "src/app.py" in bb.session_changes(sub)


@pytest.mark.covers("FR-01.04/AC12")
@pytest.mark.skipif(sys.platform == "win32", reason="a backslash cannot be a POSIX-style name on Windows")
def test_a_backslash_in_a_file_name_is_reported_verbatim(bb, project):
    _git_init(project)
    name = "a\\b.txt"
    (project / name).write_text("x\n", encoding="utf-8")
    assert name in bb.dirty_paths(project)


@pytest.mark.covers("FR-01.04/AC12")
def test_missing_and_malformed_baselines_are_strict(bb, project):
    _git_init(project)
    _dirty(project)
    assert bb._read(project) is None
    assert "src/app.py" in bb.session_changes(project)
    target = project / bb.BASELINE_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    for bad in ("not json", json.dumps([1]), json.dumps({"dirty": {}, "salt": 3})):
        target.write_text(bad, encoding="utf-8")
        assert bb._read(project) is None
        assert "src/app.py" in bb.session_changes(project)


@pytest.mark.covers("FR-01.04/AC12")
def test_dirty_paths_and_head_degrade_when_git_is_missing(bb, project, monkeypatch):
    _git_init(project)

    def boom(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(bb.subprocess, "run", boom)
    assert bb.dirty_paths(project) == []
    assert bb._head(project) is None


@pytest.mark.covers("FR-01.04/AC12")
def test_fingerprint_states(bb, tmp_path, monkeypatch):
    (tmp_path / "f.txt").write_text("a", encoding="utf-8")
    assert bb.fingerprint(tmp_path, "f.txt", "s") not in (None, bb._DELETED)
    assert bb.fingerprint(tmp_path, "nope.txt", "s") == bb._DELETED
    assert bb.fingerprint(tmp_path, "f.txt/child", "s") == bb._DELETED
    monkeypatch.setattr(Path, "open", lambda *a, **k: (_ for _ in ()).throw(PermissionError("locked")))
    assert bb.fingerprint(tmp_path, "f.txt", "s") is None


@pytest.mark.covers("FR-01.04/AC12")
def test_head_is_none_before_the_first_commit_and_write_still_works(bb, project):
    _git_init(project)
    assert bb._head(project) is None
    assert bb.write_baseline(project) is True
    assert bb.write_baseline(project) is False


@pytest.mark.covers("FR-01.04/AC12")
def test_main_reports_written_then_kept_and_not_written_on_oserror(bb, project, monkeypatch, capsys):
    _git_init(project)
    monkeypatch.setattr(sys, "argv", ["boundary_baseline.py", "--project-root", str(project)])
    assert bb.main() == 0
    assert json.loads(capsys.readouterr().out) == {"boundary_baseline": "written"}
    assert bb.main() == 0
    assert json.loads(capsys.readouterr().out) == {"boundary_baseline": "kept"}

    def deny(_root):
        raise OSError("read-only")

    monkeypatch.setattr(bb, "write_baseline", deny)
    assert bb.main() == 0
    assert json.loads(capsys.readouterr().out) == {"boundary_baseline": "not_written"}


@pytest.mark.covers("FR-01.04/AC12")
def test_setup_session_writes_the_baseline_in_process(project, monkeypatch, capsys):
    _git_init(project)
    _dirty(project)
    setup = _load(_SCRIPTS / "checks" / "setup-design-session.py", "_setup_inproc")
    monkeypatch.setattr(sys, "argv", ["setup-design-session.py", "--project-root", str(project),
                                      "--plugin-root", str(project)])
    setup.main()
    out = json.loads(capsys.readouterr().out)
    assert out["success"] is True
    assert (project / ".shipwright" / "design-boundary-baseline.json").is_file()
