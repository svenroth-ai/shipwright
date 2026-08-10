from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared" / "scripts"))
from lib.compliance_lifecycle import coverage_for, may_mirror
from lib.worktree_isolation import write_run_pointer


class _Finding:
    def __init__(self, group, check_id):
        self.group = group
        self.check_id = check_id
        self.status = "fail"


class _StopReport:
    def __init__(self, groups, findings=()):
        self.groups_run = groups
        self.import_gate_error = None
        self.groups_skipped = []
        self.findings = list(findings)


class _StopStdin:
    def read(self):
        return "{}"


class Report:
    def __init__(self, groups, error=None, findings=()):
        self.groups_run = groups
        self.import_gate_error = error
        self.findings = list(findings)

    def to_dict(self):
        return {"groups_run": list(self.groups_run), "finding_count": len(self.findings)}


def test_merge_e_is_not_applicable_but_not_missing():
    coverage = coverage_for(Report(list("ABCDFGHI")), "merge")
    assert coverage.complete
    assert coverage.not_applicable == frozenset({"E"})
    assert coverage.missing == frozenset()
    assert may_mirror(coverage)


def test_merge_absent_expected_group_is_missing_and_cannot_mirror():
    coverage = coverage_for(Report(list("ABCDFGH")), "merge")
    assert coverage.not_applicable == frozenset({"E"})
    assert coverage.missing == frozenset({"I"})
    assert not coverage.complete and not may_mirror(coverage)


def test_branch_feedback_never_has_backlog_authority_even_when_complete():
    coverage = coverage_for(Report(list("ABCDEFGHI")), "branch_feedback")
    assert coverage.complete
    assert not may_mirror(coverage)


def test_release_is_full_authority_including_group_e():
    coverage = coverage_for(Report(list("ABCDEFGHI")), "release")
    assert coverage.complete and coverage.not_applicable == frozenset()
    assert may_mirror(coverage)


def test_import_gate_error_is_incomplete_even_with_every_group_run():
    """Every group ran, but the import gate tripped: `missing` stays empty
    (not the same incompleteness as an absent group) while complete/may_mirror
    still go false — the two states must not be confused."""
    coverage = coverage_for(
        Report(list("ABCDEFGHI"), error="ImportGateError: group_j failed to import"), "release")
    assert coverage.missing == frozenset()
    assert not coverage.complete
    assert not may_mirror(coverage)


def test_coverage_for_rejects_an_unknown_scope():
    with pytest.raises(ValueError, match="unknown compliance lifecycle scope"):
        coverage_for(Report(list("ABCDEFGHI")), "sometimes")


HOOK = ROOT / "shared" / "scripts" / "hooks" / "audit_compliance_on_stop.py"
hook_spec = importlib.util.spec_from_file_location("p2_59_stop_hook", HOOK)
stop_hook = importlib.util.module_from_spec(hook_spec)
assert hook_spec and hook_spec.loader
hook_spec.loader.exec_module(stop_hook)

TOOL = ROOT / "shared" / "scripts" / "tools" / "audit_compliance_lifecycle.py"
spec = importlib.util.spec_from_file_location("lifecycle_tool", TOOL)
lifecycle_tool = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(lifecycle_tool)


def test_exact_delivered_merge_sha_is_selected(monkeypatch):
    sha = "a" * 40
    monkeypatch.setattr(lifecycle_tool.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 0, json.dumps({"state": "MERGED", "mergeCommit": {"oid": sha}}), ""))
    assert lifecycle_tool._merge_sha("7", "o/r") == sha


def test_not_delivered_pr_has_no_merge_sha(monkeypatch):
    monkeypatch.setattr(lifecycle_tool.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 0, json.dumps({"state": "OPEN", "mergeCommit": None}), ""))
    with pytest.raises(RuntimeError, match="exact merge"):
        lifecycle_tool._merge_sha("7", "o/r")


def _run_with_report(monkeypatch, scope, report):
    calls = []

    def fake_run_all(root, **kwargs):
        calls.append(("run", root, kwargs))
        return report

    def fake_mirror(root, seen_report, **kwargs):
        calls.append(("mirror", root, seen_report, kwargs))
        return {"appended": 1, "dismissed": 2}

    monkeypatch.setattr(lifecycle_tool, "_audit_api", lambda: (lambda: calls.append(("register",)), fake_run_all, fake_mirror))
    result = lifecycle_tool.run(scope, Path("/audit-tree"), Path("/backlog-tree"),
                                commit="a" * 40, run_id="iterate-p2-59")
    return result, calls


def test_branch_feedback_keeps_expected_e_drift_local(monkeypatch):
    findings = [_Finding("E", f"E{i}") for i in range(1, 6)]
    result, calls = _run_with_report(
        monkeypatch, "branch_feedback", Report(list("ABCDEFGHI"), findings=findings))
    assert result["coverage"]["complete"] is True
    assert result["findings"]["finding_count"] == 5
    assert result["mirror"]["reason"] == "local_or_incomplete"
    assert [call[0] for call in calls] == ["register", "run"]


def test_branch_feedback_keeps_real_non_e_finding_local(monkeypatch):
    result, calls = _run_with_report(
        monkeypatch, "branch_feedback", Report(list("ABCDEFGHI"), findings=[_Finding("D", "D1")]))
    assert result["findings"]["groups_run"] == list("ABCDEFGHI")
    assert result["findings"]["finding_count"] == 1
    assert not any(call[0] == "mirror" for call in calls)

def test_incomplete_merge_cannot_mutate_backlog(monkeypatch):
    result, calls = _run_with_report(monkeypatch, "merge", Report(list("ABCDFGH")))
    assert result["coverage"]["missing"] == ["I"]
    assert result["mirror"]["reason"] == "local_or_incomplete"
    assert not any(call[0] == "mirror" for call in calls)


def test_merge_refreshes_only_non_release_groups(monkeypatch):
    result, calls = _run_with_report(monkeypatch, "merge", Report(list("ABCDFGHI")))
    run = next(call for call in calls if call[0] == "run")
    mirror = next(call for call in calls if call[0] == "mirror")
    assert run[2]["only"] == list("ABCDFGHI")
    assert result["coverage"]["not_applicable"] == ["E"]
    assert mirror[3]["preserve_groups"] == frozenset({"E"})


def test_release_full_a_to_i_refresh_can_dismiss(monkeypatch):
    result, calls = _run_with_report(monkeypatch, "release", Report(list("ABCDEFGHI")))
    assert result["coverage"]["complete"] is True
    mirror = next(call for call in calls if call[0] == "mirror")
    assert mirror[3]["preserve_groups"] == frozenset()


def test_5_to_13_to_5_regression_never_mutates_on_branch(monkeypatch):
    five = [_Finding("E", f"E{i}") for i in range(5)]
    thirteen = five + [_Finding("D", f"D{i}") for i in range(8)]
    first, first_calls = _run_with_report(monkeypatch, "branch_feedback", Report(list("ABCDEFGHI"), findings=five))
    second, second_calls = _run_with_report(monkeypatch, "branch_feedback", Report(list("ABCDEFGHI"), findings=thirteen))
    release, release_calls = _run_with_report(monkeypatch, "release", Report(list("ABCDEFGHI"), findings=five))
    assert [first["findings"]["finding_count"], second["findings"]["finding_count"], release["findings"]["finding_count"]] == [5, 13, 5]
    assert first["mirror"]["reason"] == second["mirror"]["reason"] == "local_or_incomplete"
    assert not any(call[0] == "mirror" for call in first_calls + second_calls)
    assert any(call[0] == "mirror" for call in release_calls)
    assert release["coverage"]["expected"] == list("ABCDEFGHI")

def test_release_audit_start_failure_is_not_reported_as_verified(monkeypatch, tmp_path, capsys):
    """Exit 1 still blocks tagging (gated on exit code, not this string), but
    the token stays distinguishable from a bad stamp: the commit verified fine,
    only the follow-up audit could not run."""
    refresh_path = ROOT / "shared" / "scripts" / "tools" / "refresh_compliance_docs.py"
    refresh_spec = importlib.util.spec_from_file_location("refresh_lifecycle_tool", refresh_path)
    refresh = importlib.util.module_from_spec(refresh_spec)
    assert refresh_spec and refresh_spec.loader
    refresh_spec.loader.exec_module(refresh)
    monkeypatch.setattr(refresh, "verify_commit", lambda root, sha: {"status": "verified", "commit": sha, "unstamped": []})
    monkeypatch.setattr(refresh, "spawn_compliance_audit",
                        lambda argv, **kw: {"ran": False, "detail": "OSError"})
    assert refresh.main(["--project-root", str(tmp_path), "--verify-commit", "a" * 40, "--release-audit"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "verified_release_audit_incomplete"
    assert payload["release_compliance_audit"]["ran"] is False

def test_merge_cli_audits_the_exact_delivered_commit_in_a_detached_worktree(git_origin_repo, monkeypatch):
    work, _origin = git_origin_repo
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, text=True,
                         capture_output=True, check=True).stdout.strip()
    seen = {}

    monkeypatch.setattr(lifecycle_tool, "_merge_sha", lambda pr, repo: sha)

    def fake_run(scope, audit_root, backlog_root, *, commit, run_id=None):
        seen.update(scope=scope, audit_root=audit_root, backlog_root=backlog_root,
                    commit=commit, run_id=run_id)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=audit_root, text=True,
                              capture_output=True, check=True).stdout.strip()
        assert head == sha
        assert audit_root != work
        return {"coverage": {"complete": True}, "mirror": {"dismissed": 0}}

    monkeypatch.setattr(lifecycle_tool, "run", fake_run)
    assert lifecycle_tool.main([
        "--scope", "merge", "--project-root", str(work), "--pr", "42", "--repo", "o/r",
        "--run-id", "iterate-p2-59",
    ]) == 0
    assert seen == {
        "scope": "merge", "audit_root": seen["audit_root"], "backlog_root": work,
        "commit": sha, "run_id": "iterate-p2-59",
    }


def test_real_linked_worktree_stop_keeps_main_backlog_bytes_unchanged(
    git_origin_repo, make_worktree, monkeypatch,
):
    """Regression: branch A-I feedback remains visible across 5→13→5 and
    never changes the main-tree global backlog."""
    work, _origin = git_origin_repo
    # A real main tree always carries a marker (plain_root's greenfield check).
    (work / "shipwright_run_config.json").write_text(json.dumps({"status": "complete"}), encoding="utf-8")
    active = make_worktree(work, "p259")  # short slug: keep Windows MAX_PATH headroom
    (active / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "run_id": "iterate-p2-59"}), encoding="utf-8")
    triage = work / ".shipwright" / "triage.jsonl"
    triage.write_text('{"id":"main-card","status":"triage"}\n', encoding="utf-8")
    before = triage.read_bytes()
    sw = ".shipwright"
    active_triage, main_outbox, active_outbox = active / sw / "triage.jsonl", work / sw / "triage.outbox.jsonl", active / sw / "triage.outbox.jsonl"
    five = [_Finding("E", f"E{i}") for i in range(5)]
    thirteen = five + [_Finding("D", f"D{i}") for i in range(8)]
    reports = iter([_StopReport(list("ABCDEFGHI"), five),
                    _StopReport(list("ABCDEFGHI"), thirteen),
                    _StopReport(list("ABCDEFGHI"), five)])
    seen = []

    def fake_run_all(root, **kwargs):
        seen.append(root)
        return next(reports)

    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/x/plugins/shipwright-iterate")
    monkeypatch.setattr(stop_hook.Path, "cwd", staticmethod(lambda: work))
    monkeypatch.setattr(stop_hook, "_git_head_sha", lambda root: "d" * 40)
    monkeypatch.setattr(stop_hook, "_load_audit_api", lambda: (lambda: None, fake_run_all))
    monkeypatch.setattr(stop_hook.sys, "stdin", _StopStdin())

    diagnostics = []
    for i in range(3):
        session = f"s{i}"
        write_run_pointer(work, run_id="iterate-p2-59", slug="p259",
                          branch="iterate/p259", worktree_path=active,
                          session_id=session)
        assert stop_hook.pq.pointer_worktree_root(work, session) == active
        monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", session)
        assert stop_hook.main() == 0
        marker = json.loads(stop_hook._marker_path(active, "d" * 40, session).read_text(encoding="utf-8"))
        diagnostics.append(marker["result"]["local_failures"])

    assert seen == [active, active, active]
    assert [len(rows) for rows in diagnostics] == [5, 13, 5]
    assert all(row.startswith("E/") for row in diagnostics[0])
    assert "D/D0" in diagnostics[1]
    assert triage.read_bytes() == before
    assert not active_triage.exists() and not main_outbox.exists() and not active_outbox.exists()

def test_release_cli_refuses_unverified_evidence_commit(git_origin_repo, monkeypatch):
    work, _origin = git_origin_repo
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, text=True,
                         capture_output=True, check=True).stdout.strip()
    monkeypatch.setattr(lifecycle_tool, "_release_commit_verified", lambda root, commit: False)
    monkeypatch.setattr(lifecycle_tool, "run", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("must not audit")))
    assert lifecycle_tool.main(["--scope", "release", "--project-root", str(work), "--commit", sha]) == 1


def test_incomplete_release_audit_returns_nonzero_and_never_mirrors(git_origin_repo, monkeypatch):
    work, _origin = git_origin_repo
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=work, text=True,
                         capture_output=True, check=True).stdout.strip()
    monkeypatch.setattr(lifecycle_tool, "_release_commit_verified", lambda root, commit: True)
    monkeypatch.setattr(lifecycle_tool, "run", lambda *a, **kw: {
        "coverage": {"complete": False, "missing": ["I"]},
        "mirror": {"reason": "local_or_incomplete"},
    })
    assert lifecycle_tool.main(["--scope", "release", "--project-root", str(work), "--commit", sha]) == 1
