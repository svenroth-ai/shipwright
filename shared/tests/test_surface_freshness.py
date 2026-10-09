"""F11 ``check_surface_verification``: is the staged evidence about the verified code?

Freshness against trunk merges (both staging shapes), later fixes and amends,
a soft-reset consolidation, stray untracked files, staged retries, a
plugin-located runner, and the staging guard that refuses reports older than
the code. Real git, evidence staged by the production emit-side
(``_surface_check_fixtures``).
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))  # after shared/scripts: tests/ has its own `tools`

import pytest  # noqa: E402

from _cascade_trigger_fixtures import git, hermetic_git, make_repo  # noqa: E402, F401 - autouse fixture
from _surface_check_fixtures import (  # noqa: E402
    NONE_BLOCK,
    advance_trunk,
    check,
    cli_block,
    commit,
    land_branch,
    stage,
    write_entry,
)
from lib import evidence_drop  # noqa: E402

TEST_FILE = {"tests/test_a.py": "def test_x():\n    pass\n"}
SHARED = "src/shared.py"
ORIGINAL = [f"v{i} = {i}\n" for i in range(40)]


def _text(first: str | None = None, last: str | None = None) -> str:
    lines = list(ORIGINAL)
    lines[0] = first or lines[0]
    lines[-1] = last or lines[-1]
    return "".join(lines)


def _shared_file_on_trunk(tmp_path: Path) -> Path:
    root, _ = make_repo(tmp_path, {**TEST_FILE, SHARED: _text()})
    land_branch(root)
    write_entry(root, cli_block())
    return root


# --- trunk merges, later fixes, amends ------------------------------------------

@pytest.mark.covers("FR-01.11/AC07")
@pytest.mark.parametrize("staged", ["before_its_commit", "after_its_commit"])
def test_a_trunk_merge_into_a_file_the_branch_also_edited_stays_fresh(tmp_path, staged):
    root = _shared_file_on_trunk(tmp_path)
    if staged == "before_its_commit":  # F0 tested the uncommitted tree, F6 committed it later
        (root / SHARED).write_text(_text(first="v0 = 'branch'\n"), encoding="utf-8")
        stage(root)
        commit(root, SHARED, _text(first="v0 = 'branch'\n"), "feat: the unit's change")
    else:
        stage(root, head=commit(root, SHARED, _text(first="v0 = 'branch'\n"), "feat: the unit's change"))
    advance_trunk(root, SHARED, _text(last="v39 = 'sibling'\n"))
    git(root, "merge", "-q", "--no-edit", "main")  # what ensure_current does before F11
    merged = git(root, "rev-parse", "HEAD")
    assert "'sibling'" in (root / SHARED).read_text(encoding="utf-8")
    result = check(root, merged)
    assert result.ok, result.detail
    fixed = commit(root, SHARED, (root / SHARED).read_text(encoding="utf-8") + "v40 = 40\n", "fix: review")
    stale = check(root, fixed)
    assert stale.is_failure and "stale" in stale.detail and SHARED in stale.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_an_amend_after_staging_at_the_units_own_commit_is_stale(tmp_path):
    root, sha = make_repo(tmp_path, {**TEST_FILE, "src/a.py": "x = 1\n"})
    write_entry(root, cli_block())
    stage(root, head=sha)  # committed before staging
    amended = commit(root, "src/a.py", "x = 'edited after the tests ran'\n", "", amend=True)
    result = check(root, amended)
    assert result.is_failure and "not the verified commit" in result.detail and "'src/a.py'" in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_evidence_staged_over_another_branchs_tree_is_stale(tmp_path):
    root, sha = make_repo(tmp_path, {**TEST_FILE, "src/a.py": "x = 1\n"})
    git(root, "checkout", "-q", "-b", "elsewhere", "main")
    foreign = commit(root, "other.txt", "x\n", "elsewhere")
    write_entry(root, cli_block())
    stage(root, head=foreign)  # staged while the other branch was checked out
    git(root, "checkout", "-q", "iterate/probe")
    result = check(root, sha)
    assert result.is_failure and "not the verified commit" in result.detail and "'src/a.py'" in result.detail


# --- consolidation and strays ----------------------------------------------------

@pytest.mark.covers("FR-01.11/AC07")
def test_a_soft_reset_consolidation_with_the_tested_content_stays_fresh(tmp_path):
    root, sha = make_repo(tmp_path, {**TEST_FILE, "src/a.py": "x = 1\n"})
    write_entry(root, cli_block())
    stage(root, head=sha)
    git(root, "reset", "-q", "--soft", "main")
    git(root, "commit", "-q", "-m", "feat: consolidated")
    consolidated = git(root, "rev-parse", "HEAD")
    result = check(root, consolidated)
    assert result.ok, result.detail
    assert "not an ancestor" in result.detail
    git(root, "reset", "-q", "--soft", "main")
    changed = commit(root, "src/a.py", "x = 2\n", "feat: consolidated, plus a change")
    assert check(root, changed).is_failure


@pytest.mark.covers("FR-01.11/AC07")
def test_a_stray_untracked_file_in_the_tested_tree_does_not_make_it_stale(tmp_path):
    root, sha = make_repo(tmp_path, {**TEST_FILE, "src/a.py": "x = 1\n"})
    write_entry(root, cli_block())
    stray = root / "tools" / "leak_probe.py"
    stray.parent.mkdir(parents=True)
    stray.write_text("leak = 1\n", encoding="utf-8")
    stage(root)
    stray.unlink()
    result = check(root, sha)
    assert result.ok, result.detail
    assert "ignored 1 tested-only path" in result.detail and "leak_probe.py" in result.detail


# --- results: retries and the runner's own paths ----------------------------------

@pytest.mark.covers("FR-01.11/AC07")
def test_a_staged_retry_that_passed_wins_for_the_runners_tests(tmp_path):
    root, sha = make_repo(tmp_path, {**TEST_FILE})
    write_entry(root, cli_block())  # names tests/test_a.py
    stage(root, cases={"tests.test_a::test_x": "pass", "tests.test_a::test_y": "fail"},
          retry={"tests.test_a::test_y": "pass"})
    result = check(root, sha)
    assert result.ok, result.detail
    assert "latest staged attempt" in result.detail
    write_entry(root, cli_block(runner="uv run pytest -q"))  # names no path: whole suite, fail-closed
    whole = check(root, sha)
    assert whole.is_failure and "whole staged suite" in whole.detail and "test_y" in whole.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_a_failure_outside_the_runners_test_paths_does_not_count(tmp_path):
    root, sha = make_repo(tmp_path, {**TEST_FILE, "tests/test_b.py": "def test_z():\n    pass\n"})
    write_entry(root, cli_block())
    stage(root, cases={"tests.test_a::test_x": "pass", "tests.test_a::test_y": "pass",
                       "tests.test_b::test_z": "fail"})
    assert check(root, sha).ok


@pytest.mark.covers("FR-01.11/AC07")
@pytest.mark.parametrize("runner", [
    "cd plugins/p && uv run pytest tests/test_c.py -q",
    "uv run --directory plugins/p pytest tests/test_c.py",
    "uv run --project=plugins/p pytest tests/test_c.py",
])
def test_a_plugin_located_runner_is_tied_to_its_staged_results(tmp_path, runner):
    root, sha = make_repo(tmp_path, {"plugins/p/tests/test_c.py": "def test_x():\n    pass\n",
                                     "server/routes/tasks.ts": "export const t = 1;\n"})
    write_entry(root, {**cli_block(tests_run=1, runner=runner), "surface": "api"})
    stage(root, cases={"tests.test_c::test_x": "pass"}, base="plugins/p")
    result = check(root, sha)
    assert result.ok, result.detail
    assert "under the runner's 1 test path" in result.detail


# --- the staging guard: older reports never vouch for newer code ------------------

def _report(root: Path) -> Path:
    report = root.parent / "old-junit.xml"
    report.write_text('<testsuite name="pytest"><testcase classname="tests.test_a" name="test_x"/></testsuite>',
                      encoding="utf-8")
    return report


def _touch_later(path: Path) -> None:
    later = time.time() + 60  # unambiguously after the report, whatever the clock resolution
    os.utime(path, (later, later))


@pytest.mark.covers("FR-01.11/AC07")
def test_staging_reports_older_than_a_code_change_is_refused(tmp_path, capsys):
    root, _ = make_repo(tmp_path, {**TEST_FILE, "src/a.py": "x = 1\n"})
    report = _report(root)
    (root / "README.md").write_text("prose after the run does not matter\n", encoding="utf-8")
    evidence_drop.stage_reports(root, run_id="r", head_commit="h", junit_reports=[("", report)])
    commit(root, "src/a.py", "x = 'fixed after the run'\n", "fix: review")
    _touch_later(root / "src" / "a.py")
    with pytest.raises(evidence_drop.ReportsOlderThanCodeError, match="src/a.py"):
        evidence_drop.stage_reports(root, run_id="r", head_commit="h", junit_reports=[("", report)])
    assert evidence_drop.read_provenance(root)["run_id"] == "r", "nothing was cleared"
    code = evidence_drop.main(["stage", "--project-root", str(root), "--run-id", "r2", "--junit", str(report)])
    assert code == 1 and "Re-run the tests" in capsys.readouterr().err
    assert evidence_drop.read_provenance(root)["run_id"] == "r"


@pytest.mark.covers("FR-01.11/AC07")
def test_a_gitignored_scratch_tree_inside_the_repo_is_not_guarded_against_the_outer_branch(tmp_path):
    root, _ = make_repo(tmp_path, {**TEST_FILE, "src/a.py": "x = 1\n", ".gitignore": ".scratch/\n"})
    report = _report(root)
    (root / "src" / "a.py").write_text("x = 2  # uncommitted\n", encoding="utf-8")
    scratch = root / ".scratch" / "acr-1"
    (scratch / "src").mkdir(parents=True)
    (scratch / "src" / "a.py").write_text("x = 2  # uncommitted\n", encoding="utf-8")
    _touch_later(scratch / "src" / "a.py")
    _touch_later(root / "src" / "a.py")
    with pytest.raises(evidence_drop.ReportsOlderThanCodeError):  # the real tree stays guarded
        evidence_drop.stage_reports(root, run_id="r", head_commit="h", junit_reports=[("", report)])
    evidence_drop.stage_reports(scratch, run_id="r", head_commit="h", junit_reports=[("", report)])
    assert evidence_drop.read_provenance(scratch)["run_id"] == "r"


@pytest.mark.covers("FR-01.11/AC07")
def test_a_nested_checkout_in_an_ignored_dir_other_than_scratch_stays_guarded(tmp_path):
    outer, _ = make_repo(tmp_path, {"README.md": "x\n", ".gitignore": "vendored/\n"})
    (outer / "vendored").mkdir()
    inner, _ = make_repo(outer / "vendored", {**TEST_FILE, "src/a.py": "x = 1\n"})
    report = _report(inner)
    commit(inner, "src/a.py", "x = 2\n", "fix: later")
    _touch_later(inner / "src" / "a.py")
    with pytest.raises(evidence_drop.ReportsOlderThanCodeError, match="src/a.py"):
        evidence_drop.stage_reports(inner, run_id="r", head_commit="h", junit_reports=[("", report)])


# --- the detector reads a deleted file whose path has spaces ----------------------

@pytest.mark.covers("FR-01.11/AC07")
def test_a_deleted_route_file_whose_path_has_spaces_is_still_detected(tmp_path):
    root, _ = make_repo(tmp_path, {"server/routes/old tasks.ts": "export const t = 1;\n"})
    land_branch(root)
    (root / "server" / "routes" / "old tasks.ts").unlink()
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "remove the old route")
    write_entry(root, NONE_BLOCK)
    result = check(root, git(root, "rev-parse", "HEAD"))
    assert result.is_failure and "refused" in result.detail and "server/routes/old tasks.ts" in result.detail
