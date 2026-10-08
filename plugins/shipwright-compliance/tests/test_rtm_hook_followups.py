"""check_rtm_coverage follow-ups carried from U9 (U13 items 1, 3-7)."""

from __future__ import annotations

import importlib.util
import io
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "lib"))
import git_commit_command as gcc  # noqa: E402
import git_commit_target as gct  # noqa: E402
import rtm_commit_scope as rcs  # noqa: E402
import rtm_manifest_coverage as rmc  # noqa: E402

if str(Path(__file__).parent) not in sys.path:  # sibling support module; tests/ is no package root
    sys.path.insert(0, str(Path(__file__).parent))
from rtm_hook_test_support import (  # noqa: E402
    REL, collector_manifest, commit_all, hook_env, init_repo, write_manifest)
from rtm_hook_test_support import scrub_git_env  # noqa: E402,F401 - autouse

pytestmark = pytest.mark.covers("FR-01.10")
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
HOOK = Path(__file__).parent.parent / "scripts" / "hooks" / "check_rtm_coverage.py"


def _run(cwd: Path, command: str = "git commit -m x", tmp_root: Path | None = None):
    payload = {"tool_input": {"command": command}, "cwd": str(cwd)}
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, cwd=str(cwd),
                          env=hook_env(tmp_root or cwd), timeout=60)


def _manifest(passing: int, failing: int, unrun: int) -> dict:
    m = collector_manifest(passing, passing + failing + unrun, executed_rest="fail")
    for i, req in enumerate(m["requirements"].values()):
        if i >= passing + failing:
            for node in (req, req["acs"]["AC01"]):
                node["tests"]["unit"][0]["executed"] = "not_run"
    return m


# --- item 1: a requirement whose tests did not run is "not measured" ----------------------

def test_unrun_requirements_leave_the_figure_and_are_counted():
    m = _manifest(2, 1, 3)
    m["requirements"]["99::FR-09.99"] = {"id": "FR-09.99", "status": "active", "tests": {}}
    cov = rmc.compute_coverage(m)
    assert cov["fr"] == {"covered": 2, "total": 4, "pct": 50, "not_measured": 3}
    assert cov["uncovered_requirements"] == ["FR-01.02", "FR-09.99"]  # no test = uncovered
    assert cov["ac"]["total"] == 3  # the not-measured requirements' ACs are left out too


def test_one_executed_link_makes_a_requirement_measured():
    m = _manifest(0, 0, 1)
    req = next(iter(m["requirements"].values()))
    req["acs"]["AC01"]["tests"]["unit"][0]["executed"] = "fail"
    assert rmc.compute_coverage(m)["fr"] == {"covered": 0, "total": 1, "pct": 0,
                                              "not_measured": 0}


def test_hook_warns_with_the_count_and_gates_on_the_measured_rest(tmp_path):
    write_manifest(tmp_path, _manifest(8, 0, 2))
    allowed = _run(tmp_path)
    assert allowed.returncode == 0
    ctx = json.loads(allowed.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "2 of 10 requirements not measured" in ctx and "Requirement coverage 100%" in ctx
    write_manifest(tmp_path, _manifest(3, 2, 5))
    blocked = _run(tmp_path)
    assert blocked.returncode == 2 and "(3/5 active" in blocked.stderr
    assert "5 more not measured" in blocked.stderr


def test_nothing_executed_stays_unmeasurable(tmp_path):
    write_manifest(tmp_path, _manifest(0, 0, 4))
    r = _run(tmp_path)
    assert r.returncode == 0 and "not measurable" in r.stdout and "NOT evaluating" in r.stdout


# --- item 3: the gate measures the repo the commit goes to --------------------------------

def _repo(root: Path, passing: int) -> Path:
    root.mkdir(parents=True)
    init_repo(root)
    write_manifest(root, collector_manifest(passing, 10, executed_rest="fail"))
    (root / "shipwright_run_config.json").write_text("{}", encoding="utf-8")  # a project
    commit_all(root)
    return root


@needs_git
def test_dash_c_and_work_tree_name_the_measured_repo(tmp_path):
    low, high = _repo(tmp_path / "low", 3), _repo(tmp_path / "high", 10)
    assert _run(high, f'git -C "{low.as_posix()}" commit -m x', tmp_path).returncode == 2
    assert _run(low, f'git -C "{high.as_posix()}" commit -m x', tmp_path).returncode == 0
    assert _run(high, "git -C .. -C low commit -m x", tmp_path).returncode == 2
    command = f'git --git-dir="{low.as_posix()}/.git" --work-tree="{low.as_posix()}" commit'
    assert _run(high, command, tmp_path).returncode == 2


@needs_git
def test_a_bare_git_dir_is_read_through_git_dir(tmp_path):
    """Only --git-dir: the cwd is the work tree, and the index lives in the named git dir."""
    work, gitdir = tmp_path / "work", tmp_path / "store.git"
    work.mkdir()
    env = hook_env(tmp_path)
    subprocess.run(["git", "init", "-q", f"--separate-git-dir={gitdir}", str(work)],
                   check=True, capture_output=True, env=env, timeout=30)
    (work / ".git").unlink()  # nothing in the work tree points at the git dir any more
    write_manifest(work, collector_manifest(3, 10, executed_rest="fail"))
    subprocess.run(["git", f"--git-dir={gitdir}", f"--work-tree={work}", "add", REL.as_posix()],
                   check=True, capture_output=True, env=env, cwd=str(work), timeout=30)
    write_manifest(work, collector_manifest(10, 10))  # working tree says 100%, the index 30%
    assert _run(work, f'git --git-dir="{gitdir.as_posix()}" commit', tmp_path).returncode == 2


def test_commit_target_applies_git_option_order(tmp_path):
    base = tmp_path
    assert gct.commit_target("git commit -m x", base) is None
    assert gct.commit_target("git -C a status", base) is None
    assert gct.commit_target("git -C a -C '' -C b commit", base).project_root == base / "a" / "b"
    target = gct.commit_target("git -C a --git-dir g --work-tree=w commit", base)
    assert target[:4] == (base / "a" / "w", base / "a" / "g", base / "a" / "w", base / "a")
    assert gct.commit_target("git -c k=v -C x commit", base).project_root == base / "x"


@needs_git
def test_a_line_committing_to_two_repos_is_judged_on_the_failing_one(tmp_path):
    low, high = _repo(tmp_path / "low", 3), _repo(tmp_path / "high", 10)
    command = f'git -C "{high.as_posix()}" commit -m a && git -C "{low.as_posix()}" commit -m b'
    r = _run(high, command, tmp_path)
    assert r.returncode == 2 and "(3/10 active" in r.stderr
    scope = rcs.commit_scope(command, str(tmp_path), str)
    assert Path(scope.root) == low and "commits to 2 repos" in scope.warnings[0]
    assert scope.below == [str(low)] and scope.measured[0]["coverage"]["fr"]["covered"] == 3


@needs_git
def test_dash_c_naming_a_subdirectory_measures_the_project(tmp_path):
    low = _repo(tmp_path / "low", 3)
    (low / "src" / "deep").mkdir(parents=True)
    assert _run(tmp_path, "git -C low/src/deep commit -m x", tmp_path).returncode == 2
    assert gct.commit_target("git -C low/src commit", tmp_path).project_root == low


def test_git_bash_drive_paths_are_native_on_windows_only(monkeypatch):
    monkeypatch.setattr(gct.os, "name", "nt")
    assert (gct._native("/c/repo"), gct._native("/d"), gct._native("/cd/x")) == (
        "c:/repo", "d:", "/cd/x")
    monkeypatch.setattr(gct.os, "name", "posix")
    assert gct._native("/c/repo") == "/c/repo"


def test_a_missing_target_falls_back_with_a_warn(tmp_path):
    scope = rcs.commit_scope(f'git -C "{tmp_path / "nope"}" commit', str(tmp_path),
                             lambda: "DEFAULT")
    assert scope[:2] == ("DEFAULT", {}) and "not a directory" in scope.warnings[0]
    scope = rcs.commit_scope(f'git --git-dir="{tmp_path}" commit', str(tmp_path), str)
    assert scope.root == str(tmp_path) and scope.env["GIT_DIR"] == str(tmp_path)


# --- item 4: heredoc bodies are data -------------------------------------------------------

@pytest.mark.parametrize("command", [
    "cat > notes.md <<'EOF'\ngit commit -m x\nEOF",
    'cat <<"EOF" > f\nIt\'s fine to git commit later\nEOF',  # unbalanced quote in the body
    "cat <<EOF\ngit commit\nEOF\necho done",
    "cat <<-EOF\n\tgit commit\n\tEOF",
    "cat <<EOF\ngit commit -m x",  # never terminated: bash reads the rest as the body
])
def test_heredoc_bodies_are_not_scanned(command):
    assert not gcc.is_git_commit(command)


@pytest.mark.parametrize("command", [
    "git commit -F - <<EOF\nmessage\nEOF",
    "cat <<EOF > f\nbody\nEOF\ngit commit -m x",
    'echo "a <<EOF"\ngit commit -m x',  # a quoted operator starts nothing
    "echo hi # <<EOF\ngit commit -m x",  # nor does one inside a comment
    "cat <<EOF\n$(git commit -m x)\nEOF",  # unquoted delimiter: the shell runs it
    "cat <<<x\ngit commit -m y",  # a here-string is not a heredoc
    # a body fed to a shell or interpreter is commands, not data
    "bash <<EOF\ngit commit -m x\nEOF", "bash <<'EOF'\ngit commit -m x\nEOF",
    "ssh host <<EOF\ngit commit -m x\nEOF", "cat <<EOF | sh\ngit commit -m x\nEOF",
    "pwsh.exe -NoProfile <<EOF\ngit commit -m x\nEOF", "sudo -s <<EOF\ngit commit\nEOF",
    "cat <<A; bash <<B\nmessage\nA\ngit commit -m x\nB",  # data first, then commands
    "echo $((x<<y))\ngit commit -m x",  # a shift inside $((...)) is no heredoc
    "echo $((1<<2))\ngit commit -m x",  # nor is a delimiter starting with a digit
    'echo "first\n<<EOF"\ngit commit -m x',  # quoted across lines
    "echo 'first\n<<EOF'\ngit commit -m x",
])
def test_commits_around_heredocs_still_fire(command):
    assert gcc.is_git_commit(command)


# --- item 5: ACs under a sub-heading of the FR section -------------------------------------

def test_ac_inventory_keeps_acs_under_sub_headings(tmp_path):
    (tmp_path / "spec.md").write_text(
        "# Spec\n## FR-01.01 Login\n### Acceptance\n- [AC01] a\n#### Edge\n- [AC02] b\n"
        "## FR-01.02 Logout\n- [AC01] c\n## Notes\n- [AC09] not an FR's\n"
        "### FR-01.03 Nested\n- [AC01] d\n### Other\n- [AC05] e\n", encoding="utf-8")
    assert rmc.spec_ac_inventory(tmp_path, "spec.md") == {
        "FR-01.01": {"AC01", "AC02"}, "FR-01.02": {"AC01"}, "FR-01.03": {"AC01"}}


# --- item 6: the legacy section-line block carries no staging hint on either stream -------

def _load_hook():
    spec = importlib.util.spec_from_file_location("check_rtm_coverage_followups", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_legacy_block_has_override_advice_and_no_staging_hint(tmp_path, monkeypatch, capsys):
    mod = _load_hook()
    d = tmp_path / ".shipwright" / "compliance"
    d.mkdir(parents=True)
    (d / "traceability-matrix.md").write_text("| Traceability coverage | 40% |\n", encoding="utf-8")
    monkeypatch.setattr(mod, "_resolve_project_root", lambda: str(tmp_path))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {
        "command": "git commit -m x"}})))
    assert mod.main() == 2
    out, err = capsys.readouterr()
    assert "uncovered_sections" in out
    assert ("RTM build-section coverage 40% (share of build sections with a commit; "
            "no requirement manifest)") in err
    assert "staging_hint" not in out and "separate command first" not in out + err
    assert "Continue anyway" in err and "| check_rtm_coverage | OVERRIDE |" in err
    log = tmp_path / ".shipwright" / "agent_docs" / "compliance_overrides.log"
    log.parent.mkdir(parents=True)
    log.write_text(f"{datetime.now(timezone.utc).isoformat()} | check_rtm_coverage | OVERRIDE "
                   "| legacy leg\n", encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {
        "command": "git commit -m x"}})))
    assert mod.main() == 0  # the override applies to the legacy block too
    assert "OVERRIDDEN once" in capsys.readouterr().out


# --- item 7: cheap parser misses -----------------------------------------------------------

@pytest.mark.parametrize("command", [
    "git.cmd commit -m x", "git.exe commit -m x", "GIT.CMD commit",
    '"C:/Program Files/Git/cmd/git.cmd" commit -m x', "command git commit -m x",
])
def test_git_cmd_exe_and_command_git_are_commits(command):
    assert gcc.is_git_commit(command)


def test_a_user_alias_is_not_covered():
    assert not gcc.is_git_commit("git ci -m x")
