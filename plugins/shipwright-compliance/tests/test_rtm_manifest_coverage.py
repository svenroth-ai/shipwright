"""Requirement coverage computed from the committed traceability manifest (U9)."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "lib"))
import rtm_manifest_coverage as rmc  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.10")


def _link(executed="pass", status="enabled"):
    return {"id": "t::x", "layer": "unit", "status": status, "executed": executed}


def _req(tests, acs=None, status="active"):
    return {"id": "FR-01.01", "status": status, "tests": {"unit": tests},
            "acs": {k: {"tests": {"unit": v}} for k, v in (acs or {}).items()}}


def test_fr_and_ac_are_separate_metrics():
    m = {"requirements": {"a": _req([_link()], {"AC01": [_link()], "AC02": [_link("fail")]})}}
    cov = rmc.compute_coverage(m)
    assert cov["fr"] == {"covered": 1, "total": 1, "pct": 100}
    assert cov["ac"] == {"covered": 1, "total": 2, "pct": 50, "source": "manifest"}


@pytest.mark.parametrize("link", [
    _link("not_run"), _link("fail"), _link(status="skipped"),
    {"id": "t::y", "status": "enabled"},  # missing result
    "garbage",
])
def test_skipped_failed_missing_or_malformed_results_are_not_covered(link):
    cov = rmc.compute_coverage({"requirements": {"a": _req([link])}})
    assert cov["fr"] == {"covered": 0, "total": 1, "pct": 0}
    assert cov["uncovered_requirements"] == ["FR-01.01"]


def test_one_passing_test_among_failing_ones_covers():
    cov = rmc.compute_coverage({"requirements": {"a": _req([_link("fail"), _link()])}})
    assert cov["fr"]["pct"] == 100


def test_inactive_requirements_are_excluded_not_counted():
    m = {"requirements": {"a": _req([_link()]), "b": _req([], status="removed")}}
    cov = rmc.compute_coverage(m)
    assert cov["fr"]["total"] == 1 and cov["excluded_inactive"] == 1


def test_nothing_to_measure_is_none_not_100():
    assert rmc.compute_coverage({})["fr"]["pct"] is None
    assert rmc.compute_coverage({"requirements": {"a": _req([_link()])}})["ac"]["pct"] is None


def test_read_manifest_distinguishes_absent_corrupt_and_ok(tmp_path):
    assert rmc.read_manifest(tmp_path) == (None, None)
    path = tmp_path / rmc.MANIFEST_RELPATH
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    data, problem = rmc.read_manifest(tmp_path)
    assert data is None and "cannot read" in problem
    path.write_text("[]", encoding="utf-8")
    assert rmc.read_manifest(tmp_path)[0] is None
    path.write_text(json.dumps({"requirements": {}}), encoding="utf-8")
    assert rmc.read_manifest(tmp_path) == ({"requirements": {}}, None)


def test_staleness_by_age_and_unreadable_timestamp(tmp_path):
    now = datetime(2026, 10, 8, tzinfo=timezone.utc)
    fresh = {"generated_at": (now - timedelta(days=2)).isoformat()}
    old = {"generated_at": (now - timedelta(days=40)).isoformat()}
    assert rmc.staleness_warning(fresh, tmp_path, now) is None
    assert "40 days old" in rmc.staleness_warning(old, tmp_path, now)
    assert "no readable generated_at" in rmc.staleness_warning({}, tmp_path, now)


def test_staleness_by_commits_behind(tmp_path, monkeypatch):
    now = datetime(2026, 10, 8, tzinfo=timezone.utc)
    m = {"generated_at": now.isoformat(), "source_commit": "abcdef0"}
    monkeypatch.setattr(rmc, "commits_behind", lambda *_: 999)
    assert "999 commits behind" in rmc.staleness_warning(m, tmp_path, now)
    monkeypatch.setattr(rmc, "commits_behind", lambda *_: None)
    assert rmc.staleness_warning(m, tmp_path, now) is None


def test_commits_behind_is_none_outside_a_repo(tmp_path):
    assert rmc.commits_behind(tmp_path, "deadbeef") is None


def test_read_manifest_tolerates_utf8_bom_and_crlf(tmp_path):
    """Boundary probe: an editor-saved manifest (BOM / CRLF) must not read as corrupt."""
    path = tmp_path / rmc.MANIFEST_RELPATH
    path.parent.mkdir(parents=True)
    body = json.dumps({"requirements": {}}, indent=1).replace("\n", "\r\n")
    path.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    assert rmc.read_manifest(tmp_path) == ({"requirements": {}}, None)


_SPEC = """# Spec

### FR-01.01 - alpha

- (E) [AC01] Given a, when b, then c.
- (E) [AC02] Given d, when e, then f.
- (E) [AC03] Given g, when h, then i.

### FR-01.02 - beta

- (E) [AC01] Given j, when k, then l.
"""


def _spec_project(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text(_SPEC, encoding="utf-8")
    req = _req([_link()], {"AC01": [_link()], "AC03": [_link("fail")]})
    req["id"], req["spec_path"] = "FR-01.01", "spec.md"
    return {"requirements": {"01::FR-01.01": req}}


def test_untagged_ac_counts_as_uncovered_via_the_spec_inventory(tmp_path):
    """AC02 has no tagged test so the manifest has no node for it; the spec still counts it."""
    cov = rmc.compute_coverage(_spec_project(tmp_path), tmp_path)
    assert cov["ac"] == {"covered": 1, "total": 3, "pct": 33, "source": "spec"}


def test_fully_untagged_requirement_reads_zero_not_absent(tmp_path):
    m = _spec_project(tmp_path)
    m["requirements"]["01::FR-01.01"]["acs"] = {}
    cov = rmc.compute_coverage(m, tmp_path)
    assert cov["ac"]["total"] == 3 and cov["ac"]["covered"] == 0


def test_unreadable_spec_degrades_to_manifest_source_and_says_so(tmp_path):
    m = _spec_project(tmp_path)
    (tmp_path / "spec.md").unlink()
    cov = rmc.compute_coverage(m, tmp_path)
    assert cov["ac"]["source"] == "manifest" and cov["ac"]["total"] == 2


def test_spec_inventory_parses_per_fr_sections(tmp_path):
    (tmp_path / "spec.md").write_text(_SPEC, encoding="utf-8")
    assert rmc.spec_ac_inventory(tmp_path, "spec.md") == {
        "FR-01.01": {"AC01", "AC02", "AC03"}, "FR-01.02": {"AC01"}}
    assert rmc.spec_ac_inventory(tmp_path, "missing.md") is None


def test_spec_inventory_ignores_fenced_code_blocks(tmp_path):
    text = (
        "### FR-01.01 - a\n\n- (E) [AC01] one.\n\n```\n# x\n- (E) [AC99] in a fence.\n```\n\n"
        "- (E) [AC02] two.\n"
    )
    (tmp_path / "spec.md").write_text(text, encoding="utf-8")
    assert rmc.spec_ac_inventory(tmp_path, "spec.md") == {"FR-01.01": {"AC01", "AC02"}}


def test_non_hex_source_commit_never_reaches_git(tmp_path, monkeypatch):
    now = datetime(2026, 10, 8, tzinfo=timezone.utc)
    called = []
    monkeypatch.setattr(rmc, "commits_behind", lambda *a: called.append(a) or 999)
    m = {"generated_at": now.isoformat(), "source_commit": "--upload-pack=evil"}
    assert rmc.staleness_warning(m, tmp_path, now) is None and not called


def test_zero_sha_is_provenance_unknown_and_never_reaches_git(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(rmc, "commits_behind", lambda *a: called.append(a) or 999)
    m = {"generated_at": datetime.now(timezone.utc).isoformat(), "source_commit": "0" * 40}
    assert "provenance is unknown" in rmc.staleness_warning(m, tmp_path) and not called
    epoch = {"generated_at": "1970-01-01T00:00:00+00:00", "source_commit": "abcdef0"}
    assert "provenance is unknown" in rmc.staleness_warning(epoch, tmp_path) and not called


def test_schema_and_execution_problems():
    ok = {"schema_version": 4, "requirements": {"a": _req([_link("fail")])}}
    assert rmc.schema_problem(ok) is None and rmc.execution_problem(ok) is None
    assert "not the current 4" in rmc.schema_problem({"schema_version": 3})
    assert rmc.schema_problem({"schema_version": True}) is not None
    unrun = {"requirements": {"a": _req([_link("not_run")], {"AC01": [_link("not_run")]}),
                              "b": "junk", "c": {"tests": [], "acs": []}}}
    assert "no executed test result" in rmc.execution_problem(unrun)
    ac_only = {"requirements": {"a": _req([_link("not_run")], {"AC01": [_link("pass")]})}}
    assert rmc.execution_problem(ac_only) is None


def test_read_manifest_non_object_and_undecodable(tmp_path):
    path = tmp_path / rmc.MANIFEST_RELPATH
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe{")
    assert "cannot read" in rmc.read_manifest(tmp_path)[1]
    path.write_text("[]", encoding="utf-8")
    assert "not a JSON object" in rmc.read_manifest(tmp_path)[1]


def _working_tree_manifest(tmp_path):
    path = tmp_path / rmc.MANIFEST_RELPATH
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"requirements": {}}), encoding="utf-8")


@pytest.mark.parametrize("error, reason", [
    (FileNotFoundError("git"), "git is not runnable (FileNotFoundError)"),
    (subprocess.TimeoutExpired("git", 5), "git show HEAD timed out after 5 s"),
])
def test_a_failed_head_read_says_why_and_warns_on_the_working_tree_read(
        tmp_path, monkeypatch, error, reason):
    def broken(*_a, **_k):
        raise error

    monkeypatch.setattr(rmc.subprocess, "run", broken)
    assert rmc._committed_bytes(tmp_path) == (None, reason)
    assert rmc.read_manifest_noted(tmp_path) == (None, None, [])  # nothing to fall back to
    _working_tree_manifest(tmp_path)
    data, problem, notes = rmc.read_manifest_noted(tmp_path)
    assert data == {"requirements": {}} and problem is None
    assert notes == [f"reading working-tree manifest: {reason}"]


@pytest.mark.parametrize("stderr, reason, warns", [
    (b"fatal: not a git repository (or any of the parent directories): .git",
     "not a git repo", False),
    (b"fatal: path 'x' does not exist in 'HEAD'", "HEAD has no such file", False),
    (b"fatal: path 'x' exists on disk, but not in 'HEAD'", "HEAD has no such file", False),
    (b"fatal: invalid object name 'HEAD'.", "HEAD has no commit yet", True),
    (b"fatal: something odd", "git show HEAD failed (fatal: something odd)", True),
    (b"", "git show HEAD failed (exit 128)", True),
])
def test_git_failure_reasons_are_classified(tmp_path, monkeypatch, stderr, reason, warns):
    monkeypatch.setattr(rmc.subprocess, "run", lambda *_a, **_k: subprocess.CompletedProcess(
        [], 128, stdout=b"", stderr=stderr))
    assert rmc._committed_bytes(tmp_path) == (None, reason)
    _working_tree_manifest(tmp_path)
    assert bool(rmc.read_manifest_noted(tmp_path)[2]) is warns


def test_spec_path_outside_the_project_root_is_never_read(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "outside.md").write_text(_SPEC, encoding="utf-8")
    assert rmc.spec_ac_inventory(root, "../outside.md") is None
    assert rmc.spec_ac_inventory(root, str(tmp_path / "outside.md")) is None
    m = _spec_project(root)
    m["requirements"]["01::FR-01.01"]["spec_path"] = "../outside.md"
    cov = rmc.compute_coverage(m, root)
    assert cov["ac"]["source"] == "manifest" and cov["ac"]["total"] == 2
