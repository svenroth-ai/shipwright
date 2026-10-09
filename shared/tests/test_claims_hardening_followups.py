"""Follow-ups to U5/U6 (campaign 2026-10-07-finalization-claims-hardening).

(1) requirement catalogs are outside every no-FR label, (2) finalize's idempotent
re-run still runs the requirement gates, (3) a stacked unit's diff starts at its
parent branch, (4) surface-evidence freshness counts a hand-resolved merge
conflict as a branch write and dates a deleted file.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))  # after shared/scripts: tests/ has its own `tools`

import pytest  # noqa: E402

from _cascade_trigger_fixtures import git, hermetic_git, make_repo  # noqa: E402, F401 - autouse fixture
from _surface_check_fixtures import (  # noqa: E402
    advance_trunk, check, cli_block, commit, land_branch, stage, write_entry,
)
from lib import evidence_drop  # noqa: E402
from lib.change_type_diff import change_type_diff_error  # noqa: E402
from lib.change_type_paths import SHAPE_GENERIC, SHAPE_SHIPWRIGHT_MONOREPO, unclassified_paths  # noqa: E402
from test_requirement_gate_change_type_diff import _event, _git, _repo, _write  # noqa: E402

LABELS = ("docs", "tooling", "infra", "compliance")
CATALOGS = [".shipwright/planning/01-adopted/spec.md", ".shipwright/planning/02-api/spec.md"]
TEST_A = {"tests/test_a.py": "def test_x():\n    pass\n"}


# --- (1) requirement catalogs ---------------------------------------------------

def _no_label_covers_catalogs(shape):
    for label in LABELS:
        assert unclassified_paths(CATALOGS, label, shape) == CATALOGS


@pytest.mark.covers("FR-01.11/AC03")
def test_no_label_covers_a_requirement_catalog_in_a_generic_project():
    _no_label_covers_catalogs(SHAPE_GENERIC)


@pytest.mark.covers("FR-01.11/AC03")
def test_no_label_covers_a_requirement_catalog_in_the_monorepo():
    _no_label_covers_catalogs(SHAPE_SHIPWRIGHT_MONOREPO)


@pytest.mark.covers("FR-01.11/AC03")
def test_an_iterates_own_spec_and_other_records_stay_bookkeeping():
    records = [".shipwright/planning/iterate/iterate-2026-10-08-x/spec.md",
               ".shipwright/planning/iterate/x.md", ".shipwright/agent_docs/iterates/x.json",
               ".shipwright/planning/campaigns/c/campaign.md"]
    for label in LABELS:
        assert unclassified_paths(records, label, SHAPE_GENERIC) == []


# --- (2) finalize re-run --------------------------------------------------------

@pytest.mark.covers("FR-01.11/AC04")
def test_a_finalize_rerun_with_unclassified_extras_is_refused_not_short_circuited(tmp_path):
    from tools.finalize_iterate import FinalizeGateError, _record_event
    log = tmp_path / "shipwright_events.jsonl"
    log.write_text("", encoding="utf-8")
    good = {"change_type": "tooling", "none_reason": "probe"}
    first = _record_event(tmp_path, "", "iterate-2026-10-08-probe", "d", event_extras=good)
    assert first
    assert _record_event(tmp_path, "", "iterate-2026-10-08-probe", "d", event_extras=good) == first
    with pytest.raises(FinalizeGateError):
        _record_event(tmp_path, "", "iterate-2026-10-08-probe", "d", event_extras={"intent": "feature"})
    # the Stop-hook repair pass supplies no claims: nothing to judge, the recorded id comes back
    assert _record_event(tmp_path, "", "iterate-2026-10-08-probe", "d") == first
    assert len([json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]) == 1


# --- (3) stacked unit -----------------------------------------------------------

def _stack(tmp_path):
    root = _repo(tmp_path, ["README.md"])
    _git(root, "checkout", "-q", "-b", "iterate/parent")
    _write(root, "src/app.py", "runtime\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "parent unit")
    _git(root, "checkout", "-q", "-b", "iterate/child")
    _write(root, "docs/child.md", "doc\n")
    return root


@pytest.mark.covers("FR-01.11/AC03")
def test_a_stacked_unit_is_measured_from_its_parent_branch(tmp_path):
    root = _stack(tmp_path)
    whole = change_type_diff_error(_event("docs"), root, "t")
    assert whole and "src/app.py" in whole["detail"]  # trunk fork point: sees the whole stack
    assert change_type_diff_error(_event("docs", campaign="c", sub_iterate_id="u1", stack_base_ref="iterate/parent"), root, "t") is None
    _write(root, "src/own.py")
    blamed = change_type_diff_error(_event("docs", campaign="c", sub_iterate_id="u1", stack_base_ref="iterate/parent"), root, "t")
    assert blamed and "src/own.py" in blamed["detail"] and "src/app.py" not in blamed["detail"]


def _refuses_stack_base(tmp_path, ref):
    err = change_type_diff_error(_event("docs", campaign="c", sub_iterate_id="u1", stack_base_ref=ref), _stack(tmp_path), "t")
    assert err and err["error"] == "change_type_diff_unavailable"


@pytest.mark.covers("FR-01.11/AC03")
def test_a_stack_base_naming_the_trunk_refuses(tmp_path):
    _refuses_stack_base(tmp_path, "main")


@pytest.mark.covers("FR-01.11/AC03")
def test_a_stack_base_naming_a_missing_branch_refuses(tmp_path):
    _refuses_stack_base(tmp_path, "iterate/missing")


@pytest.mark.covers("FR-01.11/AC03")
def test_a_stack_base_with_a_traversal_segment_refuses(tmp_path):
    _refuses_stack_base(tmp_path, "iterate/../main")


@pytest.mark.covers("FR-01.11/AC03")
def test_a_stack_base_on_another_branch_refuses(tmp_path):
    root = _stack(tmp_path)
    _git(root, "checkout", "-q", "-b", "iterate/other", "main")
    _write(root, "other.txt")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "other")
    _git(root, "checkout", "-q", "iterate/child")
    err = change_type_diff_error(_event("docs", campaign="c", sub_iterate_id="u1", stack_base_ref="iterate/other"), root, "t")
    assert err and "not an ancestor" in err["detail"]


# --- (4a) a hand-resolved conflict is a branch write ----------------------------

SHARED = "src/shared.py"


def _conflicting_merge(tmp_path, *, stage_after_merge: bool):
    root, _ = make_repo(tmp_path, {**TEST_A, SHARED: "v = 0\n"})
    land_branch(root)
    write_entry(root, cli_block())
    branch = commit(root, SHARED, "v = 'branch'\n", "feat: the unit's change")
    if not stage_after_merge:
        stage(root, head=branch)
    advance_trunk(root, SHARED, "v = 'trunk'\n")
    merge = subprocess.run(["git", "-C", str(root), "merge", "-q", "main"], capture_output=True, check=False)
    assert merge.returncode == 1, "the probe needs a real conflict"
    (root / SHARED).write_text("v = 'both, by hand'\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "merge main, resolved")
    merged = git(root, "rev-parse", "HEAD")
    if stage_after_merge:
        stage(root, head=merged)
    return root, merged


@pytest.mark.covers("FR-01.11/AC07")
def test_a_conflict_resolved_after_staging_makes_the_evidence_stale(tmp_path):
    root, merged = _conflicting_merge(tmp_path, stage_after_merge=False)
    result = check(root, merged)
    assert result.is_failure and "stale" in result.detail and SHARED in result.detail


@pytest.mark.covers("FR-01.11/AC07")
def test_a_conflict_resolved_before_staging_stays_fresh(tmp_path):
    root, merged = _conflicting_merge(tmp_path, stage_after_merge=True)
    result = check(root, merged)
    assert result.ok, result.detail


# --- (4b) a deleted file has no mtime -------------------------------------------

def _report(root: Path, *, mtime_offset: float = 0.0) -> Path:
    report = root.parent / "old-junit.xml"
    report.write_text('<testsuite name="pytest"><testcase classname="tests.test_a" name="test_x"/></testsuite>',
                      encoding="utf-8")
    if mtime_offset:
        later = time.time() + mtime_offset
        os.utime(report, (later, later))
    return report


def _stage(root: Path, report: Path) -> None:
    evidence_drop.stage_reports(root, run_id="r", head_commit="h", junit_reports=[("", report)])


def _repo_with_gone_file(tmp_path):
    root, _ = make_repo(tmp_path, {**TEST_A, "src/gone.py": "x = 1\n"})
    land_branch(root)
    return root


def _delete_and_commit(root: Path) -> None:
    (root / "src" / "gone.py").unlink()
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "remove gone")


@pytest.mark.covers("FR-01.11/AC07")
def test_a_branch_commit_that_deleted_a_file_after_the_run_refuses_staging(tmp_path):
    root = _repo_with_gone_file(tmp_path)
    report = _report(root)
    _delete_and_commit(root)
    with pytest.raises(evidence_drop.ReportsOlderThanCodeError, match="src/gone.py"):
        _stage(root, report)


@pytest.mark.covers("FR-01.11/AC07")
def test_a_deletion_committed_before_the_run_is_accepted(tmp_path):
    root = _repo_with_gone_file(tmp_path)
    _delete_and_commit(root)
    _stage(root, _report(root, mtime_offset=120))  # the reports were written after the commit
    assert evidence_drop.read_provenance(root)["run_id"] == "r"


@pytest.mark.covers("FR-01.11/AC07")
def test_an_uncommitted_deletion_after_the_run_is_dated_by_its_directory(tmp_path):
    root = _repo_with_gone_file(tmp_path)
    report = _report(root)
    (root / "src" / "gone.py").unlink()
    later = time.time() + 60
    os.utime(root / "src", (later, later))
    with pytest.raises(evidence_drop.ReportsOlderThanCodeError, match="src/gone.py"):
        _stage(root, report)


@pytest.mark.covers("FR-01.11/AC07")
def test_an_uncommitted_deletion_before_the_run_is_accepted(tmp_path):
    root = _repo_with_gone_file(tmp_path)
    (root / "src" / "gone.py").unlink()
    _stage(root, _report(root, mtime_offset=120))
    assert evidence_drop.read_provenance(root)["run_id"] == "r"


@pytest.mark.covers("FR-01.11/AC07")
def test_an_uncommitted_deletion_of_a_file_the_branch_already_edited_is_still_dated(tmp_path):
    root = _repo_with_gone_file(tmp_path)
    commit(root, "src/gone.py", "x = 2\n", "feat: edit")
    report = _report(root)
    (root / "src" / "gone.py").unlink()
    later = time.time() + 60
    os.utime(root / "src", (later, later))
    with pytest.raises(evidence_drop.ReportsOlderThanCodeError, match="src/gone.py"):
        _stage(root, report)


@pytest.mark.covers("FR-01.11/AC03")
def test_a_stack_base_naming_the_units_own_branch_refuses(tmp_path):
    root = _stack(tmp_path)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "child work")
    err = change_type_diff_error(_event("docs", campaign="c", sub_iterate_id="u1", stack_base_ref="iterate/child"), root, "t")
    assert err and "own branch" in err["detail"]
