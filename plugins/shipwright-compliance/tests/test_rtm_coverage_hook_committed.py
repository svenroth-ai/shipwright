"""check_rtm_coverage reads the COMMITTED manifest and refuses unmeasurable ones (U9 doubt fixes).

Manifests here are collector-shaped (``test_links/1.0.0`` keys and link fields) so the
hook sees what the real pipeline writes: a fail-closed all-``not_run`` regeneration, a
v3 manifest, and an epoch/zero-SHA placeholder stamp.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

if str(Path(__file__).parent) not in sys.path:  # sibling support module; tests/ is no package root
    sys.path.insert(0, str(Path(__file__).parent))
from rtm_hook_test_support import (  # noqa: E402
    REL,
    hook_env,
    scrub_git_env,  # noqa: F401 - autouse: in-process git reads see tmp_path only
)
from rtm_hook_test_support import collector_manifest as _collector_manifest  # noqa: E402
from rtm_hook_test_support import commit_all as _commit_all  # noqa: E402
from rtm_hook_test_support import git as _git  # noqa: E402
from rtm_hook_test_support import init_repo as _repo  # noqa: E402
from rtm_hook_test_support import write_manifest as _write  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.10")

PLUGIN = Path(__file__).parent.parent
HOOK = PLUGIN / "scripts" / "hooks" / "check_rtm_coverage.py"


def _run(root: Path, command: str = "git commit -m x", *, full: bool = False):
    r = subprocess.run([sys.executable, str(HOOK)],
                       input=json.dumps({"tool_input": {"command": command}}),
                       capture_output=True, text=True, cwd=str(root), env=hook_env(root),
                       timeout=60)
    return r if full else (r.returncode, r.stdout.strip())


needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


@needs_git
def test_committed_manifest_wins_over_a_fail_closed_working_tree_regen(tmp_path):
    """The verified bug: local regen dirties the file to all not_run -> FR 0% on every commit."""
    _repo(tmp_path)
    _write(tmp_path, _collector_manifest(10, 10))
    _commit_all(tmp_path)
    _write(tmp_path, _collector_manifest(0, 10))  # dirty, fail-closed regeneration
    rc, out = _run(tmp_path)
    assert rc == 0 and "Requirement coverage 100% (10/10" in out


@needs_git
def test_committed_low_coverage_blocks_even_when_working_tree_looks_good(tmp_path):
    _repo(tmp_path)
    _write(tmp_path, _collector_manifest(3, 10, executed_rest="fail"))
    _commit_all(tmp_path)
    _write(tmp_path, _collector_manifest(10, 10))
    rc, out = _run(tmp_path)
    assert rc == 2 and "Requirement coverage 30% (3/10" in out


@needs_git
def test_repo_whose_head_lacks_the_manifest_falls_back_to_the_working_tree(tmp_path):
    _repo(tmp_path)
    (tmp_path / "README").write_text("x", encoding="utf-8")
    _commit_all(tmp_path)
    _write(tmp_path, _collector_manifest(3, 10, executed_rest="fail"))
    assert _run(tmp_path)[0] == 2


@needs_git
def test_subdirectory_project_reads_its_own_committed_manifest(tmp_path):
    _repo(tmp_path)
    sub = tmp_path / "webui"
    _write(sub, _collector_manifest(10, 10))
    _commit_all(tmp_path)
    _write(sub, _collector_manifest(0, 10))
    sys.path.insert(0, str(PLUGIN / "scripts" / "lib"))
    try:
        import rtm_manifest_coverage as rmc  # noqa: PLC0415
        data, problem = rmc.read_manifest(sub)
    finally:
        sys.path.remove(str(PLUGIN / "scripts" / "lib"))
    assert problem is None and rmc.execution_problem(data) is None


@needs_git
def test_a_staged_correction_is_measured_not_the_low_head_copy(tmp_path):
    """Committing a regenerated manifest is gated on what is being committed (the index)."""
    _repo(tmp_path)
    _write(tmp_path, _collector_manifest(3, 10, executed_rest="fail"))
    _commit_all(tmp_path)
    _write(tmp_path, _collector_manifest(10, 10))
    _git(tmp_path, "add", REL.as_posix())
    _write(tmp_path, _collector_manifest(0, 10))  # dirtied again after staging
    rc, out = _run(tmp_path, "git commit -m regen")
    assert rc == 0 and "Requirement coverage 100% (10/10" in out
    assert "reading working-tree manifest" not in out


@needs_git
def test_a_manifest_staged_by_the_commit_command_itself_is_measured_from_head(tmp_path):
    """Documented PreToolUse ordering limit: the hook runs before ``git add`` does."""
    _repo(tmp_path)
    _write(tmp_path, _collector_manifest(3, 10, executed_rest="fail"))
    _commit_all(tmp_path)
    _write(tmp_path, _collector_manifest(10, 10))  # corrected, but NOT yet staged
    r = _run(tmp_path, f"git add {REL.as_posix()} && git commit -m x", full=True)
    assert r.returncode == 2 and "Requirement coverage 30% (3/10" in r.stdout
    assert "separate command first" in r.stderr
    _git(tmp_path, "add", REL.as_posix())  # staged in a separate command: measured
    assert _run(tmp_path)[0] == 0


@needs_git
def test_a_path_removed_from_the_index_falls_back_to_head_without_a_warn(tmp_path):
    _repo(tmp_path)
    _write(tmp_path, _collector_manifest(3, 10, executed_rest="fail"))
    _commit_all(tmp_path)
    _git(tmp_path, "rm", "-q", "--cached", REL.as_posix())
    _write(tmp_path, _collector_manifest(10, 10))
    rc, out = _run(tmp_path)
    assert rc == 2 and "Requirement coverage 30% (3/10" in out
    assert "reading working-tree manifest" not in out


@needs_git
def test_an_unborn_head_with_a_staged_manifest_reads_it_without_a_warn(tmp_path):
    _repo(tmp_path)
    _write(tmp_path, _collector_manifest(10, 10))
    _git(tmp_path, "add", "-A")
    _write(tmp_path, _collector_manifest(0, 10))
    rc, out = _run(tmp_path)
    assert rc == 0 and "100% (10/10" in out and "HEAD has no commit yet" not in out


def test_all_not_run_manifest_is_unmeasurable_not_zero_percent(tmp_path):
    _write(tmp_path, _collector_manifest(0, 21))
    rc, out = _run(tmp_path)
    assert rc == 0
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "no executed test result" in ctx and "NOT evaluating" in ctx
    assert "Requirement coverage" not in ctx and "blocked" not in out


def test_all_failing_manifest_is_measured_and_blocks(tmp_path):
    """'fail' IS an executed result: a genuinely red suite still gates."""
    _write(tmp_path, _collector_manifest(0, 10, executed_rest="fail"))
    assert _run(tmp_path)[0] == 2


@pytest.mark.parametrize("version", [3, None, "4"])
def test_non_current_schema_is_unmeasurable_and_says_regenerate(tmp_path, version):
    manifest = _collector_manifest(1, 10, schema_version=version)
    if version is None:
        del manifest["schema_version"]
    (tmp_path / ".shipwright" / "compliance").mkdir(parents=True)
    (tmp_path / ".shipwright" / "compliance" / "traceability-matrix.md").write_text(
        "| Traceability coverage | 5% |\n", encoding="utf-8")  # never the fallback
    _write(tmp_path, manifest)
    rc, out = _run(tmp_path)
    assert rc == 0
    assert "is not the current 4" in out and "regenerate" in out and "NOT evaluating" in out


@pytest.mark.parametrize("stamp", [
    {"generated_at": "1970-01-01T00:00:00+00:00"},
    {"source_commit": "0" * 40},
])
def test_epoch_or_zero_sha_reads_as_provenance_unknown(tmp_path, stamp):
    _write(tmp_path, _collector_manifest(10, 10, **stamp))
    rc, out = _run(tmp_path)
    assert rc == 0 and "provenance is unknown" in out
    assert "days old" not in out


@pytest.mark.parametrize("command", [
    "git -C /some/path commit -m x",
    'git -c user.name="A B" commit -m x',
    "cd sub && git commit -m x",
    "git add . ; git --no-pager commit",
    "FOO=1 git commit --amend --no-edit",
    "git add x\ngit commit -m y",
    'sh -c "git commit -m x"',
    "bash -lc 'git commit -m x'",
    "timeout 60 git commit -m x",
    "env FOO=1 git commit",
    "sudo git commit",
    "git -C repo \\\n  commit -m x",
    "nice -n 5 nohup git commit -m x",
    "/usr/bin/git.exe commit",
])
def test_real_commit_invocations_are_evaluated(tmp_path, command):
    _write(tmp_path, _collector_manifest(3, 10, executed_rest="fail"))
    assert _run(tmp_path, command)[0] == 2


@pytest.mark.parametrize("command", [
    "git -c core.pager=cat diff",
    'rg "git commit" docs/',
    "git log --grep 'git commit'",
    "echo git commit",
    "git commit-tree HEAD^{tree}",
    "bash -c 'echo git commit'",
    "sh script.sh git commit",
    "timeout 60 git status",
])
def test_commands_that_merely_mention_git_commit_are_not_evaluated(tmp_path, command):
    _write(tmp_path, _collector_manifest(3, 10, executed_rest="fail"))
    assert _run(tmp_path, command) == (0, "")


def test_is_git_commit_inproc_including_unbalanced_quote_fallback():
    spec = importlib.util.spec_from_file_location("check_rtm_coverage_cmd", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.is_git_commit("git -C a -c k=v commit")
    assert not mod.is_git_commit("git -c k=v diff | grep commit")
    assert not mod.is_git_commit("git")
    assert mod.is_git_commit('git commit -m "unbalanced')
    assert not mod.is_git_commit('rg "unbalanced')
    assert mod.is_git_commit("git commit \\\r\n  -m x")
    assert mod.is_git_commit("bash -c 'sh -c \"git commit\"'")  # nested shells
    import git_commit_command as gcc  # noqa: PLC0415 - on sys.path once the hook ran

    def _has_commit(tokens, depth=0):
        return next(gcc._segment_commits(tokens, depth), None) is not None

    assert _has_commit(["sh", "-c", "git commit"], 0)
    # past the depth cap the substring test decides: over-fire, never fail open
    assert _has_commit(["sh", "-c", "git commit"], gcc._MAX_SHELL_DEPTH)
    assert not _has_commit(["sh", "-c", "echo hi"], gcc._MAX_SHELL_DEPTH)
    assert not _has_commit(["bash", "-o", "pipefail", "script.sh"])


def test_parser_import_failure_falls_back_to_the_substring_test(monkeypatch):
    spec = importlib.util.spec_from_file_location("check_rtm_coverage_noparser", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setitem(sys.modules, "git_commit_command", None)  # import -> ImportError
    assert mod.is_git_commit("echo git commit")  # degraded: over-fires, never fails open
    assert not mod.is_git_commit("git status")


@needs_git
def test_unborn_head_warns_that_the_working_tree_copy_is_read(tmp_path):
    _repo(tmp_path)
    _write(tmp_path, _collector_manifest(10, 10))
    rc, out = _run(tmp_path)
    assert rc == 0 and "reading working-tree manifest: HEAD has no commit yet" in out


@needs_git
def test_head_without_the_file_reads_the_working_tree_without_a_warn(tmp_path):
    _repo(tmp_path)
    (tmp_path / "README").write_text("x", encoding="utf-8")
    _commit_all(tmp_path)
    _write(tmp_path, _collector_manifest(10, 10))
    rc, out = _run(tmp_path)
    assert rc == 0 and "reading working-tree manifest" not in out


def test_schema_version_mirrors_the_group_d_reader():
    src = (PLUGIN / "scripts" / "audit" / "_group_d_manifest.py").read_text(encoding="utf-8")
    group_d = int(re.search(r"^MANIFEST_SCHEMA_VERSION = (\d+)", src, re.M).group(1))
    lib = (PLUGIN / "scripts" / "lib" / "rtm_manifest_coverage.py").read_text(encoding="utf-8")
    assert int(re.search(r"^MANIFEST_SCHEMA_VERSION = (\d+)", lib, re.M).group(1)) == group_d
