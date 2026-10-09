"""Review follow-ups to ``test_claims_hardening_followups``: catalog predicate, stack-base
hardening (tag shadowing, trunk merged in, shape), evil merges, old git."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))  # after shared/scripts: tests/ has its own `tools`

import pytest  # noqa: E402

from _cascade_trigger_fixtures import git, hermetic_git, make_repo  # noqa: E402, F401 - autouse fixture
from _surface_check_fixtures import (  # noqa: E402
    advance_trunk, check, cli_block, commit, land_branch, stage, write_entry,
)
from lib.change_type_diff import change_type_diff_error  # noqa: E402
from lib.change_type_paths import SHAPE_GENERIC, unclassified_paths  # noqa: E402
from test_claims_hardening_followups import SHARED, TEST_A, _conflicting_merge, _stack  # noqa: E402
from test_requirement_gate_change_type_diff import _event, _git, _repo, _write  # noqa: E402


def _ten(name, first=None, last=None):
    lines = [f"{name}{i} = {i}\n" for i in range(40)]
    lines[0] = f"{name}0 = {first}\n" if first else lines[0]
    lines[-1] = f"{name}39 = {last}\n" if last else lines[-1]
    return "".join(lines)


# --- review follow-ups: catalog predicate, stack-base hardening, evil merge ------

@pytest.mark.covers("FR-01.11/AC03")
def test_catalog_predicate_matches_the_canonical_one():
    nested = ".shipwright/planning/a/b/spec.md"
    greenfield = ".shipwright/agent_docs/spec.md"
    assert unclassified_paths([nested, greenfield], "tooling", SHAPE_GENERIC) == [greenfield, nested]
    assert unclassified_paths([".shipwright/planning/iterate/spec.md"], "docs", SHAPE_GENERIC) == []


@pytest.mark.covers("FR-01.11/AC03")
def test_a_tag_named_like_the_parent_branch_cannot_shadow_it(tmp_path):
    root = _stack(tmp_path)
    _git(root, "tag", "iterate/shadow", "main")  # a tag, no such branch
    err = change_type_diff_error(_event("docs", campaign="c", sub_iterate_id="u1", stack_base_ref="iterate/shadow"), root, "t")
    assert err and err["error"] == "change_type_diff_unavailable" and "does not resolve" in err["detail"]
    assert "PARENT unit" in err["detail"]


@pytest.mark.covers("FR-01.11/AC03")
def test_trunk_merged_into_the_stacked_unit_drops_out_of_its_diff(tmp_path):
    root = _stack(tmp_path)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "child work")
    _git(root, "checkout", "-q", "main")
    _write(root, "src/trunk_only.py")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "trunk moves")
    _git(root, "update-ref", "refs/remotes/origin/main", "main")
    _git(root, "checkout", "-q", "iterate/child")
    _git(root, "merge", "-q", "--no-edit", "main")
    assert change_type_diff_error(_event("docs", campaign="c", sub_iterate_id="u1", stack_base_ref="iterate/parent"), root, "t") is None
    _write(root, "src/own.py")
    err = change_type_diff_error(_event("docs", campaign="c", sub_iterate_id="u1", stack_base_ref="iterate/parent"), root, "t")
    assert err and "src/own.py" in err["detail"] and "trunk_only" not in err["detail"]


@pytest.mark.covers("FR-01.11/AC03")
def test_a_stack_base_cannot_widen_the_project_shape(tmp_path):
    root = _repo(tmp_path, ["README.md"])
    _git(root, "checkout", "-q", "-b", "iterate/parent")
    _write(root, "shared/scripts/x.py")
    _write(root, ".claude-plugin/marketplace.json")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "parent adds the monorepo markers")
    _git(root, "checkout", "-q", "-b", "iterate/child")
    _write(root, "plugins/p/tool.py")
    err = change_type_diff_error(_event("tooling", campaign="c", sub_iterate_id="u1", stack_base_ref="iterate/parent"), root, "t")
    assert err and err["error"] == "change_type_not_covered_by_diff" and "plugins/p/tool.py" in err["detail"]


@pytest.mark.covers("FR-01.11/AC07")
def test_an_edit_inside_a_cleanly_merged_file_is_a_branch_write(tmp_path):
    root, _ = make_repo(tmp_path, {**TEST_A, SHARED: _ten("v")})
    land_branch(root)
    write_entry(root, cli_block())
    branch = commit(root, SHARED, _ten("v", first="'branch'"), "feat: the unit's change")
    stage(root, head=branch)
    advance_trunk(root, SHARED, _ten("v", last="'trunk'"))
    merge = subprocess.run(["git", "-C", str(root), "merge", "-q", "--no-commit", "--no-ff", "main"],
                           capture_output=True, check=False)
    assert merge.returncode == 0, "the probe needs a clean auto-merge"
    text = (root / SHARED).read_text(encoding="utf-8") + "sneaky = 1\n"
    (root / SHARED).write_text(text, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "merge main, with a hand edit")
    result = check(root, git(root, "rev-parse", "HEAD"))
    assert result.is_failure and "stale" in result.detail and SHARED in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_a_git_without_merge_tree_write_tree_names_the_version(tmp_path, monkeypatch):
    from tools.verifiers import _surface_revision as rev
    root, merged = _conflicting_merge(tmp_path, stage_after_merge=False)
    real = rev._run_git

    def fake(project_root, *args, **kw):
        return (129, "", "usage") if args[:1] == ("merge-tree",) else real(project_root, *args, **kw)

    monkeypatch.setattr(rev, "_run_git", fake)
    result = check(root, merged)
    assert result.is_failure and "older than 2.38" in result.detail


@pytest.mark.covers("FR-01.11/AC03")
def test_the_gate_runs_in_a_repository_before_its_first_commit(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    _write(tmp_path, "docs/a.md")
    assert change_type_diff_error(_event("docs"), tmp_path, "t") is None
    _write(tmp_path, "src/app.py")
    err = change_type_diff_error(_event("docs"), tmp_path, "t")
    assert err and err["error"] == "change_type_not_covered_by_diff"


@pytest.mark.covers("FR-01.11/AC03")
def test_a_stack_base_with_no_history_shared_with_the_trunk_refuses(tmp_path):
    root = _stack(tmp_path)
    _git(root, "checkout", "-q", "--orphan", "iterate/orphan")
    _git(root, "rm", "-rfq", ".")
    _write(root, "orphan.txt")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "unrelated lineage")
    _git(root, "checkout", "-q", "iterate/child")
    _git(root, "merge", "-q", "--allow-unrelated-histories", "--no-edit", "iterate/orphan")
    err = change_type_diff_error(_event("docs", campaign="c", sub_iterate_id="u1", stack_base_ref="iterate/orphan"), root, "t")
    assert err and "no history" in err["detail"]


@pytest.mark.covers("FR-01.11/AC04")
def test_a_rerun_that_states_different_claims_keeps_the_record_and_says_so(tmp_path, capsys):
    from tools.finalize_iterate import _record_event
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    first = _record_event(tmp_path, "", "iterate-2026-10-08-div", "d",
                          event_extras={"change_type": "tooling", "none_reason": "probe"})
    again = _record_event(tmp_path, "", "iterate-2026-10-08-div", "d",
                          event_extras={"change_type": "infra", "none_reason": "probe"})
    assert again == first
    assert "recorded event kept" in capsys.readouterr().err


@pytest.mark.covers("FR-01.11/AC07")
def test_the_staging_guard_judges_paths_relative_to_a_project_subdirectory(tmp_path):
    from lib import evidence_drop
    root, _ = make_repo(tmp_path, {"app/tests/test_a.py": "def test_x():\n    pass\n", "app/src/x.py": "x = 1\n"})
    project = root / "app"
    report = root.parent / "sub-junit.xml"
    report.write_text('<testsuite name="pytest"><testcase classname="tests.test_a" name="test_x"/></testsuite>',
                      encoding="utf-8")
    (project / "src" / "x.py").write_text("x = 2\n", encoding="utf-8")
    later = __import__("time").time() - 60
    __import__("os").utime(report, (later, later))  # the report predates the edit: refuse, naming the real path
    with pytest.raises(evidence_drop.ReportsOlderThanCodeError, match="src/x.py"):
        evidence_drop.stage_reports(project, run_id="r", head_commit="h", junit_reports=[("", report)])


@pytest.mark.covers("FR-01.11/AC03")
def test_a_stack_base_without_a_campaign_stamp_or_on_a_detached_head_refuses(tmp_path):
    root = _stack(tmp_path)
    plain = change_type_diff_error(_event("docs", stack_base_ref="iterate/parent"), root, "t")
    assert plain and "campaign unit" in plain["detail"]
    _git(root, "checkout", "-q", "--detach")
    err = change_type_diff_error(_event("docs", campaign="c", sub_iterate_id="u1", stack_base_ref="iterate/parent"),
                                 root, "t")
    assert err and "detached" in err["detail"]


@pytest.mark.covers("FR-01.11/AC07")
def test_an_uncommitted_deletion_in_a_project_subdirectory_is_still_dated(tmp_path):
    import os
    import time
    from lib import evidence_drop
    root, _ = make_repo(tmp_path, {"app/tests/test_a.py": "def test_x():\n    pass\n", "app/src/x.py": "x = 1\n"})
    land_branch(root)
    commit(root, "app/src/x.py", "x = 2\n", "feat: edit")
    project = root / "app"
    report = root.parent / "sub-del-junit.xml"
    report.write_text('<testsuite name="pytest"><testcase classname="tests.test_a" name="test_x"/></testsuite>',
                      encoding="utf-8")
    (project / "src" / "x.py").unlink()
    later = time.time() + 60
    os.utime(project / "src", (later, later))
    with pytest.raises(evidence_drop.ReportsOlderThanCodeError, match="src/x.py"):
        evidence_drop.stage_reports(project, run_id="r", head_commit="h", junit_reports=[("", report)])
