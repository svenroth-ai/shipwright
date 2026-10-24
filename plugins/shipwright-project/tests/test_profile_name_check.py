"""``--profile`` of the project writers must name a profile the resolver resolves (campaign S3).

Accepted: a project / user / bundled profile, or a reserved sentinel (``generic`` /
``detecting``). Rejected (exit 4, nothing written): a name failing the D3 rules or
resolving nowhere. Tagged to FR-01.06 (see shared/tests/test_profile_resolver.py).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from lib.profile_check import profile_error
from write_run_config import main as run_config_main

pytestmark = pytest.mark.covers("FR-01.06")

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
_PROJECT_CONFIG = _SCRIPTS / "checks" / "write-project-config.py"


def _profile(root: Path, name: str, text: str | None = None) -> None:
    d = root / ".shipwright" / "profiles"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(text if text is not None else json.dumps({"name": name}), encoding="utf-8")


@pytest.mark.parametrize("name", ["generic", "detecting", "vite-hono", "supabase-nextjs"])
def test_sentinels_and_bundled_names_are_accepted(tmp_path, name):
    assert profile_error(name, tmp_path) is None


def test_project_and_user_profiles_are_accepted(tmp_path):
    _profile(tmp_path, "my-stack")
    (Path(os.environ["SHIPWRIGHT_USER_PROFILES_DIR"]) / "user-stack.json").write_text(
        json.dumps({"name": "user-stack"}), encoding="utf-8")
    assert profile_error("my-stack", tmp_path) is None
    assert profile_error("user-stack", tmp_path) is None


@pytest.mark.parametrize("name", ["My_Stack", "../x", "Vite-Hono", "con", "a b", "", "reducibility-idioms"])
def test_names_failing_the_rules_are_rejected(tmp_path, name):
    assert profile_error(name, tmp_path)


def test_unknown_name_lists_the_searched_paths(tmp_path):
    msg = profile_error("no-such-stack", tmp_path)
    assert "not_found" in msg and str(tmp_path / ".shipwright" / "profiles") in msg


def test_invalid_profile_file_is_rejected_naming_the_file(tmp_path):
    _profile(tmp_path, "broken", "{ nope")
    assert "broken.json" in profile_error("broken", tmp_path)


def test_write_run_config_rejects_an_unresolvable_profile(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["write_run_config.py", "--project-root", str(tmp_path), "--profile", "My_Stack"])
    assert run_config_main() == 4
    assert "cannot be used" in capsys.readouterr().err
    assert not (tmp_path / "shipwright_run_config.json").exists()


@pytest.mark.parametrize("name", ["generic", "detecting"])
def test_write_run_config_accepts_sentinels(tmp_path, monkeypatch, name):
    monkeypatch.setattr(sys, "argv", ["write_run_config.py", "--project-root", str(tmp_path), "--profile", name])
    assert run_config_main() == 0
    assert json.loads((tmp_path / "shipwright_run_config.json").read_text())["profile"] == name


def _write_project_config(root: Path, profile: str, status: str = "in_progress"):
    planning = root / ".shipwright" / "planning"
    planning.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [sys.executable, str(_PROJECT_CONFIG), "--planning-dir", str(planning), "--profile", profile,
         "--scope", "full_app", "--project-root", str(root), "--status", status],
        capture_output=True, text=True, check=False,
    )


def test_write_project_config_rejects_and_writes_nothing(tmp_path):
    done = _write_project_config(tmp_path, "no-such-stack")
    assert done.returncode == 4 and "no-such-stack" in done.stderr
    assert not (tmp_path / "shipwright_project_config.json").exists()


@pytest.mark.parametrize("profile", ["detecting", "generic", "vite-hono", "my-stack"])
def test_write_project_config_accepts_resolvable_names(tmp_path, profile):
    _profile(tmp_path, "my-stack")
    done = _write_project_config(tmp_path, profile)
    assert done.returncode == 0, done.stderr
    assert json.loads((tmp_path / "shipwright_project_config.json").read_text())["profile"] == profile


def test_profile_check_imports_the_resolver_through_the_plugin_layout(tmp_path):
    """lib/profile_check.py copied to <root>/<plugin>/<ver>/scripts/lib reaches <root>/shared (parents[4])."""
    repo = Path(__file__).resolve().parents[3]
    root = tmp_path / "cache" / "shipwright"
    lib = root / "shipwright-project" / "1.0.0" / "scripts" / "lib"
    lib.mkdir(parents=True)
    shutil.copy2(_SCRIPTS / "lib" / "profile_check.py", lib)
    (root / "shared" / "scripts").mkdir(parents=True)
    for f in (repo / "shared" / "scripts").glob("profile_*.py"):
        shutil.copy2(f, root / "shared" / "scripts" / f.name)
    shutil.copytree(repo / "shared" / "profiles", root / "shared" / "profiles")
    shutil.copytree(repo / "shared" / "schemas", root / "shared" / "schemas")
    proj = tmp_path / "proj"
    _profile(proj, "my-stack")
    code = (
        "import importlib.util as u;"
        f"s = u.spec_from_file_location('profile_check', r'{lib / 'profile_check.py'}');"
        "m = u.module_from_spec(s); s.loader.exec_module(m);"
        f"print(m.profile_error('my-stack', r'{proj}'), m.profile_error('nope-stack', r'{proj}') is not None)"
    )
    env = {**os.environ, "SHIPWRIGHT_USER_PROFILES_DIR": str(tmp_path / "u")}
    done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, env=env, check=False)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "None True"


def test_write_project_config_main_in_process(tmp_path, monkeypatch, capsys):
    import importlib.util

    spec = importlib.util.spec_from_file_location("write_project_config_under_test", _PROJECT_CONFIG)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    planning = tmp_path / ".shipwright" / "planning"
    planning.mkdir(parents=True)
    argv = ["x", "--planning-dir", str(planning), "--scope", "full_app", "--project-root", str(tmp_path),
            "--status", "in_progress", "--profile"]
    monkeypatch.setattr(sys, "argv", argv + ["no-such-stack"])
    assert module.main() == 4
    assert "no-such-stack" in capsys.readouterr().err and not (tmp_path / "shipwright_project_config.json").exists()
    monkeypatch.setattr(sys, "argv", argv + ["generic"])
    assert module.main() == 0
    assert json.loads((tmp_path / "shipwright_project_config.json").read_text())["profile"] == "generic"


def test_write_project_config_profile_lookup_root_is_above_dot_shipwright(tmp_path):
    """The skill call sites pass only --planning-dir <project>/.shipwright/planning: the profile LOOKUP must use
    <project>. The write root is deliberately unchanged (config stays beside planning's parent, pre-existing)."""
    _profile(tmp_path, "my-stack")
    planning = tmp_path / ".shipwright" / "planning"
    planning.mkdir(parents=True)
    done = subprocess.run(
        [sys.executable, str(_PROJECT_CONFIG), "--planning-dir", str(planning), "--profile", "my-stack",
         "--scope", "full_app", "--status", "in_progress"],
        capture_output=True, text=True, check=False,
    )
    assert done.returncode == 0, done.stderr
    assert (tmp_path / ".shipwright" / "shipwright_project_config.json").is_file()
    assert not (tmp_path / "shipwright_project_config.json").exists()


def test_missing_shared_tree_is_an_install_error_not_a_bad_name(tmp_path, monkeypatch, capsys):
    import lib.profile_check as profile_check

    monkeypatch.setattr(profile_check, "_SHARED_SCRIPTS", str(tmp_path / "nowhere"))
    with pytest.raises(ImportError):
        profile_check.profile_error("vite-hono", tmp_path)
    monkeypatch.setattr(sys, "argv", ["write_run_config.py", "--project-root", str(tmp_path), "--profile", "vite-hono"])
    assert run_config_main() == 1
    assert "shared/` tree is incomplete" in capsys.readouterr().err


def _load_project_config_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("write_project_config_s5", _PROJECT_CONFIG)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_file_mode_layout_finds_the_project_profile_through_profile_root(tmp_path):
    """`/shipwright-project @requirements.md`: planning_dir is the requirements file's parent, which sits
    OUTSIDE the project. Only --profile-root (both SKILL call sites pass it) locates `.shipwright/profiles/`;
    it is lookup-only, so the config stays exactly where it was written before (beside planning's parent)."""
    project = tmp_path / "project"
    _profile(project, "my-stack")
    notes = tmp_path / "notes"
    notes.mkdir()
    argv = [sys.executable, str(_PROJECT_CONFIG), "--planning-dir", str(notes), "--profile", "my-stack",
            "--scope", "full_app", "--status", "in_progress"]
    without = subprocess.run(argv, capture_output=True, text=True, check=False)
    assert without.returncode == 4 and "my-stack" in without.stderr
    with_root = subprocess.run([*argv, "--profile-root", str(project)], capture_output=True, text=True, check=False)
    assert with_root.returncode == 0, with_root.stderr
    assert json.loads((tmp_path / "shipwright_project_config.json").read_text())["profile"] == "my-stack"
    assert not (project / "shipwright_project_config.json").exists()  # the write location did not move


@pytest.mark.parametrize("sentinel", ["generic", "detecting"])
def test_early_sentinel_call_skips_the_profile_check(tmp_path, monkeypatch, sentinel):
    """in_progress + a reserved sentinel never reaches the resolver (no new failure mode for the early call)."""
    import lib.profile_check as profile_check

    def boom(*_a, **_k):
        raise AssertionError("profile_error must not run for the early sentinel call")

    monkeypatch.setattr(profile_check, "profile_error", boom)
    module = _load_project_config_module()
    plan_dir = tmp_path / "notes"
    plan_dir.mkdir()
    monkeypatch.setattr(sys, "argv", ["x", "--planning-dir", str(plan_dir), "--scope", "full_app",
                                      "--project-root", str(tmp_path), "--status", "in_progress",
                                      "--profile", sentinel])
    assert module.main() == 0
    assert json.loads((tmp_path / "shipwright_project_config.json").read_text())["profile"] == sentinel


def test_missing_shared_tree_degrades_for_the_early_project_config_only(tmp_path, monkeypatch, capsys):
    """Early (in_progress) call, like the gitignore merge: an incomplete shared tree warns on stderr and the
    config is still written; a complete scaffold keeps the hard install error (exit 1, nothing written)."""
    import lib.profile_check as profile_check

    monkeypatch.setattr(profile_check, "_SHARED_SCRIPTS", str(tmp_path / "nowhere"))
    module = _load_project_config_module()
    plan_dir = tmp_path / "notes"
    plan_dir.mkdir()
    monkeypatch.setattr(sys, "argv", ["x", "--planning-dir", str(plan_dir), "--scope", "full_app",
                                      "--project-root", str(tmp_path), "--status", "in_progress",
                                      "--profile", "vite-hono"])
    assert module.main() == 0
    assert "profile check skipped" in capsys.readouterr().err
    assert (tmp_path / "shipwright_project_config.json").is_file()
    (tmp_path / "shipwright_project_config.json").unlink()
    monkeypatch.setattr(sys, "argv", ["x", "--planning-dir", str(plan_dir), "--scope", "full_app",
                                      "--project-root", str(tmp_path), "--status", "complete",
                                      "--profile", "vite-hono"])
    assert module.main() == 1
    assert "incomplete" in capsys.readouterr().err
    assert not (tmp_path / "shipwright_project_config.json").exists()
