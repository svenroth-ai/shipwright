"""check_rtm_coverage reads the COMMITTED manifest and refuses unmeasurable ones (U9 doubt fixes).

Manifests here are collector-shaped (``test_links/1.0.0`` keys and link fields) so the
hook sees what the real pipeline writes: a fail-closed all-``not_run`` regeneration, a
v3 manifest, and an epoch/zero-SHA placeholder stamp.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.covers("FR-01.10")

PLUGIN = Path(__file__).parent.parent
HOOK = PLUGIN / "scripts" / "hooks" / "check_rtm_coverage.py"
REL = Path(".shipwright") / "compliance" / "test-traceability.json"
_GIT_ENV_DROP = ("SHIPWRIGHT_PROJECT_ROOT", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")


def _collector_manifest(passing: int, total: int, *, executed_rest="not_run",
                        schema_version=4, generated_at=None, source_commit="a" * 40):
    reqs = {}
    for i in range(total):
        fr = f"FR-01.{i:02d}"
        link = {"id": f"plugins/x/tests/test_x.py::test_{i}",
                "path": f"plugins/x/tests/test_x.py::test_{i}", "layer": "unit",
                "status": "enabled", "executed": "pass" if i < passing else executed_rest,
                "tag_source": "pytest_marker", "ac_id": "AC01"}
        reqs[f"01::{fr}"] = {
            "id": fr, "spec_path": ".shipwright/planning/01-adopted/spec.md",
            "title": f"req {i}", "priority": "Must", "status": "active",
            "required_layers": ["unit"], "required_layers_source": "inferred_legacy",
            "tests": {"unit": [link]}, "acs": {"AC01": {"tests": {"unit": [dict(link)]}}},
        }
    return {
        "schema_version": schema_version, "collector_version": "test_links/1.0.0",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit, "spec_hash": "sha256:" + "0" * 64,
        "requirements": reqs, "orphans": [], "invalid_tags": [], "invalid_layers": [],
        "untagged_tests": [],
    }


def _write(root: Path, manifest: dict) -> None:
    path = root / REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in _GIT_ENV_DROP}


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                   env=_env(), timeout=30)


def _repo(root: Path) -> None:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "config", "core.hooksPath", str(root / ".no-hooks"))


def _commit_all(root: Path) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "manifest")


def _run(root: Path, command: str = "git commit -m x"):
    r = subprocess.run([sys.executable, str(HOOK)],
                       input=json.dumps({"tool_input": {"command": command}}),
                       capture_output=True, text=True, cwd=str(root), env=_env(), timeout=60)
    return r.returncode, r.stdout.strip()


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


def test_schema_version_mirrors_the_group_d_reader():
    src = (PLUGIN / "scripts" / "audit" / "_group_d_manifest.py").read_text(encoding="utf-8")
    group_d = int(re.search(r"^MANIFEST_SCHEMA_VERSION = (\d+)", src, re.M).group(1))
    lib = (PLUGIN / "scripts" / "lib" / "rtm_manifest_coverage.py").read_text(encoding="utf-8")
    assert int(re.search(r"^MANIFEST_SCHEMA_VERSION = (\d+)", lib, re.M).group(1)) == group_d
