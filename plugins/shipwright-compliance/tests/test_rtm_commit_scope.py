"""check_rtm_coverage measures the repo a commit lands in, and never a figure over too few (U13 fixes)."""

from __future__ import annotations

import importlib.util
import io
import json
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "lib"))
import git_commit_target as gct  # noqa: E402
import rtm_gate_support as rgs  # noqa: E402
import rtm_manifest_coverage as rmc  # noqa: E402

if str(Path(__file__).parent) not in sys.path:  # sibling support module; tests/ is no package root
    sys.path.insert(0, str(Path(__file__).parent))
from rtm_hook_test_support import (  # noqa: E402
    collector_manifest, commit_all, hook_env, init_repo, write_manifest)
from rtm_hook_test_support import scrub_git_env  # noqa: E402,F401 - autouse

pytestmark = pytest.mark.covers("FR-01.10")
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
HOOK = Path(__file__).parent.parent / "scripts" / "hooks" / "check_rtm_coverage.py"


def _run(cwd: Path, command: str, tmp_root: Path):
    payload = {"tool_input": {"command": command}, "cwd": str(cwd)}
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, cwd=str(cwd),
                          env=hook_env(tmp_root), timeout=60)


def _project(directory: Path, passing: int) -> None:
    write_manifest(directory, collector_manifest(passing, 10, executed_rest="fail"))
    (directory / "shipwright_run_config.json").write_text("{}", encoding="utf-8")


def _monorepo(tmp_path: Path) -> tuple[Path, Path]:
    """A markerless repo root with the project (30% covered) in ``app/``."""
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    init_repo(repo)
    _project(repo / "app", 3)
    commit_all(repo)
    return repo, repo / "app"


# --- the project is resolved by the shared resolver, from the directory git reached ----

@needs_git
def test_dash_c_at_a_markerless_repo_root_descends_into_the_project(tmp_path):
    repo, app = _monorepo(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert _run(elsewhere, f'git -C "{repo.as_posix()}" commit -m x', tmp_path).returncode == 2
    assert _run(repo, "git -C . commit -m x", tmp_path).returncode == 2
    assert gct.commit_target("git -C . commit", repo).project_root == app


@needs_git
def test_a_stray_shipwright_dir_does_not_capture_the_target(tmp_path):
    """``shared/tests/.shipwright`` shape: a triage store and a cache, no agent_docs."""
    repo, app = _monorepo(tmp_path)
    stray = app / "sub" / ".shipwright"
    (stray / ".cache").mkdir(parents=True)
    (stray / "triage.jsonl").write_text("", encoding="utf-8")
    target = gct.commit_target("git -C app/sub commit", repo)
    assert target.project_root == app and target.found
    assert _run(repo, "git -C app/sub commit -m x", tmp_path).returncode == 2


@needs_git
def test_a_commit_to_no_project_warns_when_the_default_has_compliance_data(tmp_path):
    low = tmp_path / "low"
    low.mkdir()
    init_repo(low)
    _project(low, 3)
    commit_all(low)
    other = tmp_path / "other"
    other.mkdir()
    init_repo(other)
    r = _run(low, f'git -C "{other.as_posix()}" commit -m x', tmp_path)
    assert r.returncode == 0
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "no Shipwright project was found" in ctx and "NOT evaluating" in ctx


def test_an_unloadable_resolver_is_a_note_not_a_crash(tmp_path, monkeypatch):
    def gone():
        raise ImportError("gone")

    monkeypatch.setattr(gct, "_resolver", gone)
    target = gct.commit_target("git -C . commit", tmp_path)
    assert target.project_root == tmp_path and not target.found and "ImportError" in target.note


# --- --work-tree without --git-dir: the index of the repo found from cwd / -C ----------

@needs_git
def test_a_work_tree_alone_measures_the_index_of_the_repo_found_from_cwd(tmp_path):
    low = tmp_path / "low"
    low.mkdir()
    init_repo(low)
    _project(low, 3)
    commit_all(low)
    empty = tmp_path / "empty"
    empty.mkdir()
    r = _run(low, f'git --work-tree="{empty.as_posix()}" commit -m x', tmp_path)
    assert r.returncode == 2 and "(3/10 active" in r.stderr


# --- a figure is never taken over zero, or over too few measured requirements -----------

def _unrun(manifest: dict, count: int) -> dict:
    for req in list(manifest["requirements"].values())[-count:]:
        for node in (req, req["acs"]["AC01"]):
            node["tests"]["unit"][0]["executed"] = "not_run"
    return manifest


def test_all_active_unrun_with_an_executed_inactive_link_is_not_evaluated(tmp_path):
    manifest = _unrun(collector_manifest(0, 3, executed_rest="fail"), 3)
    inactive = json.loads(json.dumps(next(iter(manifest["requirements"].values()))))
    inactive.update(id="FR-09.01", status="deprecated")
    inactive["tests"]["unit"][0]["executed"] = "pass"
    manifest["requirements"]["09::FR-09.01"] = inactive
    assert rmc.execution_problem(manifest)  # the inactive pass says nothing
    write_manifest(tmp_path, manifest)
    measured, warnings = rgs.measure(str(tmp_path))
    assert measured is None and "3 of 3 requirements not measured" in warnings[0]
    assert warnings[-1] == rgs.NOT_EVALUATING


def test_more_than_half_unmeasured_is_not_evaluated(tmp_path):
    assert rgs.MAX_UNMEASURED_SHARE == Fraction(1, 2)
    write_manifest(tmp_path, _unrun(collector_manifest(4, 10, executed_rest="fail"), 6))
    measured, warnings = rgs.measure(str(tmp_path))
    assert measured is None and "more than 50%" in warnings[-2]
    write_manifest(tmp_path, _unrun(collector_manifest(4, 10, executed_rest="fail"), 5))
    measured, _ = rgs.measure(str(tmp_path))  # exactly half: still evaluated
    assert measured["coverage"]["fr"] == {"covered": 4, "total": 5, "pct": 80, "not_measured": 5}


def test_a_comparison_that_raises_is_a_visible_warn(tmp_path, monkeypatch, capsys):
    write_manifest(tmp_path, collector_manifest(3, 10, executed_rest="fail"))
    spec = importlib.util.spec_from_file_location("_rtm_scope_hook", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "_resolve_project_root", lambda: str(tmp_path))

    def boom(*_args):
        raise ZeroDivisionError("0/0")

    monkeypatch.setattr(rgs, "meets", boom)
    assert mod._lib() is rgs
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {
        "command": "git commit -m x"}})))
    assert mod.main() == 0
    ctx = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
    assert "ZeroDivisionError" in ctx and "NOT evaluating" in ctx
