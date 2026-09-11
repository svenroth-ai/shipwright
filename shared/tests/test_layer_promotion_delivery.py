"""Pins the delivery half of ``lib.layer_promotion_sweep`` (mechanics live in
``lib.layer_promotion_delivery``): a found promotion is ALWAYS rolled back
out of the caller's own branch, whether it ships as its own PR or not. This
is the direct regression test for the F11 layer-coverage hazard a spec-review
found in the original design (a promotion committed onto the iterate's own
branch sits inside the range that gate diffs, so an iterate that never
touched the promoted FR could be HARD-failed by a promotion its own build
never asked for) — see ``lib.layer_promotion_sweep``'s module docstring.

``git push`` in ``deliver_as_own_pr`` runs through ``lib.git_base``'s
``Popen``-based helpers, never ``subprocess.run``, so it cannot be stubbed
the way ``gh`` calls are below — the ``repo`` fixture gives every test a real
local bare ``origin`` remote so push is exercised for real."""

from __future__ import annotations

import json
import subprocess

import pytest

import lib.layer_promotion_delivery as delivery_mod
from lib.git_base import TIMEOUT_RETURNCODE
from lib.layer_promotion_delivery import deliver_as_own_pr
from lib.layer_promotion_sweep import run_layer_promotion_sweep, sweep_warnings


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    origin_bare = tmp_path / "origin.git"
    _git(["init", "--bare", str(origin_bare)], tmp_path)

    root = tmp_path / "repo"
    root.mkdir()
    _git(["init"], root)
    _git(["config", "user.email", "test@example.com"], root)
    _git(["config", "user.name", "Test"], root)
    (root / "spec.md").write_text("placeholder\n", encoding="utf-8")
    ledger_dir = root / ".shipwright" / "compliance"
    ledger_dir.mkdir(parents=True)
    (ledger_dir / "layer_promotion_ledger.json").write_text('{"decisions": []}\n', encoding="utf-8")
    _git(["add", "spec.md", ".shipwright"], root)
    _git(["commit", "-m", "init"], root)
    _git(["remote", "add", "origin", str(origin_bare)], root)
    _git(["push", "origin", "HEAD:refs/heads/main"], root)
    return root


def _break_origin(repo):
    """Repoint ``origin`` at a path with no git repo, so a real ``git push``
    fails fast (no network involved, no timeout needed)."""
    _git(["remote", "set-url", "origin", str(repo / "does-not-exist")], repo)


def _origin_branch_subject(repo, branch):
    """Commit subject of ``branch`` in ``repo``'s bare ``origin`` remote, or
    ``""`` if the branch does not exist there."""
    url = _git(["remote", "get-url", "origin"], repo).stdout.strip()
    proc = subprocess.run(
        ["git", "log", "-1", "--format=%s", f"refs/heads/{branch}"],
        cwd=url, capture_output=True, text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _head_sha(repo):
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip()


def _head_subject(repo):
    return subprocess.run(
        ["git", "log", "-1", "--format=%s"], cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip()


_REAL_RUN = subprocess.run
_PROMOTE_REPORT = {
    "promoted": [{"fr": "FR-01.01", "action": "promote"}],
    "written_spec_paths": ["spec.md"], "skipped": [], "escalated": [],
}


def _stub_run(*, gh_list_result=None, gh_create_ok=True, gh_create_url="https://example.com/pull/1"):
    """Intercept every ``gh`` call and the promote tool's own subprocess
    invocation — ``git push`` is deliberately NOT intercepted here (see
    module docstring): it always hits the real git binary against the
    ``repo`` fixture's bare ``origin`` remote."""
    def _fake(cmd, *args, **kwargs):
        if cmd[0] == "gh" and cmd[1:3] == ["pr", "list"]:
            return subprocess.CompletedProcess(cmd, 0, json.dumps(gh_list_result or []), "")
        if cmd[0] == "gh" and cmd[1:3] == ["pr", "create"]:
            if gh_create_ok:
                return subprocess.CompletedProcess(cmd, 0, gh_create_url + "\n", "")
            return subprocess.CompletedProcess(cmd, 1, "", "create failed")
        if cmd[0] == "gh" and cmd[1:3] == ["pr", "merge"]:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if len(cmd) >= 2 and str(cmd[1]).endswith("promote_required_layers.py"):
            return subprocess.CompletedProcess(cmd, 0, json.dumps(_PROMOTE_REPORT), "")
        return _REAL_RUN(cmd, *args, **kwargs)
    return _fake


def test_promotion_is_delivered_as_its_own_pr_and_local_branch_is_untouched(monkeypatch, repo):
    pre_sha = _head_sha(repo)
    (repo / "spec.md").write_text("Layers: unit, e2e\n", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", _stub_run(gh_create_url="https://example.com/pull/42"))
    result = run_layer_promotion_sweep(repo, "iterate-x", "main")

    assert result.status == "delivered"
    assert result.promoted == ["FR-01.01"]
    assert result.pr_url == "https://example.com/pull/42"
    assert result.branch.startswith("chore/layer-promotion-")

    # The commit was pushed to its OWN branch, never left on this worktree's
    # branch: F11's own merge-base diff for THIS branch must never see it.
    assert _head_sha(repo) == pre_sha
    assert _head_subject(repo) == "init"
    assert (repo / "spec.md").read_text(encoding="utf-8") == "placeholder\n"

    # ...but it DID land on the bare origin remote, on its own branch.
    subject = _origin_branch_subject(repo, result.branch)
    assert "promote" in subject.lower() and "FR" in subject
    assert any("opened its own PR" in w and "FR-01.01" in w for w in sweep_warnings(result))


def test_ledger_only_promotion_is_still_committed_and_delivered(monkeypatch, repo):
    """Finding 4: the tool writes the ledger unconditionally whenever ANY FR
    is promoted, even when every promoted FR's spec.md write was itself
    skipped (SKIP_LIVE_CELL_HAS_RESIDUAL_TEXT) — ``written_spec_paths`` is
    empty but ``promoted`` is not, and that alone must still trigger delivery."""
    pre_sha = _head_sha(repo)
    (repo / ".shipwright" / "compliance" / "layer_promotion_ledger.json").write_text(
        '{"decisions": [{"fr": "FR-01.01", "action": "promoted"}]}\n', encoding="utf-8",
    )
    report = {**_PROMOTE_REPORT, "written_spec_paths": []}

    def _fake(cmd, *args, **kwargs):
        if len(cmd) >= 2 and str(cmd[1]).endswith("promote_required_layers.py"):
            return subprocess.CompletedProcess(cmd, 0, json.dumps(report), "")
        return _stub_run()(cmd, *args, **kwargs)
    monkeypatch.setattr(subprocess, "run", _fake)
    result = run_layer_promotion_sweep(repo, "iterate-x", "main")
    assert result.status == "delivered"
    assert _head_sha(repo) == pre_sha
    assert _origin_branch_subject(repo, result.branch) != ""


def test_existing_open_pr_skips_push_and_reports_not_delivered(monkeypatch, repo):
    pre_sha = _head_sha(repo)
    (repo / "spec.md").write_text("Layers: unit\n", encoding="utf-8")
    monkeypatch.setattr(
        subprocess, "run",
        _stub_run(gh_list_result=[
            {"url": "https://example.com/pull/9", "headRefName": "chore/layer-promotion-deadbeefcafe"},
        ]),
    )
    result = run_layer_promotion_sweep(repo, "iterate-x", "main")
    assert result.status == "not_delivered"
    assert "already open" in result.reason
    assert _head_sha(repo) == pre_sha  # rolled back even though never pushed
    assert _origin_branch_subject(repo, result.branch) == ""  # never reached origin
    assert any("did not ship it" in w for w in sweep_warnings(result))


def test_malformed_gh_list_response_is_treated_as_no_existing_pr(monkeypatch, repo):
    """External review, PR #725 round 4: gh_json's output could be a
    well-formed JSON document of the WRONG shape (a mapping instead of a
    list) — _existing_promotion_pr must never raise on it, just treat it as
    'no existing PR found' and proceed with delivery."""
    (repo / "spec.md").write_text("Layers: unit\n", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", _stub_run(gh_list_result={"unexpected": "shape"}))
    result = run_layer_promotion_sweep(repo, "iterate-x", "main")
    assert result.status == "delivered"


def test_gh_list_response_with_non_mapping_rows_is_treated_as_no_existing_pr(monkeypatch, repo):
    """Same boundary, the list-of-wrong-shape-rows variant: a row that isn't
    itself a mapping must be skipped, never raise past _existing_promotion_pr."""
    (repo / "spec.md").write_text("Layers: unit\n", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", _stub_run(gh_list_result=["not-a-mapping"]))
    result = run_layer_promotion_sweep(repo, "iterate-x", "main")
    assert result.status == "delivered"


def test_push_failure_still_resets_local_branch(monkeypatch, repo):
    pre_sha = _head_sha(repo)
    (repo / "spec.md").write_text("Layers: unit\n", encoding="utf-8")
    _break_origin(repo)
    monkeypatch.setattr(subprocess, "run", _stub_run())
    result = run_layer_promotion_sweep(repo, "iterate-x", "main")
    assert result.status == "not_delivered"
    assert "push failed" in result.reason
    assert _head_sha(repo) == pre_sha


def test_pr_create_failure_still_resets_local_branch(monkeypatch, repo):
    pre_sha = _head_sha(repo)
    (repo / "spec.md").write_text("Layers: unit\n", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", _stub_run(gh_create_ok=False))
    result = run_layer_promotion_sweep(repo, "iterate-x", "main")
    assert result.status == "not_delivered"
    assert "create failed" in result.reason
    assert _head_sha(repo) == pre_sha


def test_deliver_as_own_pr_with_empty_pre_sha_is_rollback_failed(monkeypatch, repo):
    """Stage-2 review, round 3: an unreadable pre-promotion HEAD must be
    reported as the loud, distinct ``rollback_failed`` status, never
    silently attempted as a `git reset --hard ""` (which itself fails)."""
    monkeypatch.setattr(subprocess, "run", _stub_run())
    status, reason, _pr_url, _branch = deliver_as_own_pr(repo, "main", "", "chore: test")
    assert status == "rollback_failed"
    assert "pre-promotion" in reason


def test_final_reset_failure_reports_rollback_failed(monkeypatch, repo):
    """Stage-2 review, round 3: the final reset's own returncode must be
    checked, not fired from an unconditional ``finally`` that discards it —
    the one outcome where the commit may still be on the iterate's branch."""
    (repo / "spec.md").write_text("Layers: unit\n", encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", _stub_run())
    real_run_git_soft = delivery_mod.run_git_soft

    def _fake_run_git_soft(args, *a, **kw):
        if args[:1] == ["reset"]:
            return subprocess.CompletedProcess(["git", *args], 1, "", "reset rejected")
        return real_run_git_soft(args, *a, **kw)

    monkeypatch.setattr(delivery_mod, "run_git_soft", _fake_run_git_soft)
    result = run_layer_promotion_sweep(repo, "iterate-x", "main")
    assert result.status == "rollback_failed"
    assert "reset" in result.reason.lower()
    assert any("CRITICAL" in w for w in sweep_warnings(result))


def test_push_timeout_degrades_to_not_delivered_and_still_resets_local_branch(monkeypatch, repo):
    """Direct regression test for the Stage-1 re-review finding: an escaping
    ``subprocess.TimeoutExpired`` from ``git push`` would abort
    ``setup_iterate_worktree`` AFTER ``git worktree add`` already succeeded,
    orphaning the new worktree — the exact hazard ``run_git_soft`` exists to
    prevent. ``run_git_soft`` itself already proves (its own test suite) that
    a real timeout never raises; this test instead pins that
    ``deliver_as_own_pr`` correctly treats the DEGRADED result it produces
    (returncode :data:`TIMEOUT_RETURNCODE`) as an ordinary push failure."""
    pre_sha = _head_sha(repo)
    (repo / "spec.md").write_text("Layers: unit\n", encoding="utf-8")
    real_run_git_soft = delivery_mod.run_git_soft

    def _fake_run_git_soft(args, *a, **kw):
        if args[:1] == ["push"]:
            return subprocess.CompletedProcess(["git", *args], TIMEOUT_RETURNCODE, "", "timed out")
        return real_run_git_soft(args, *a, **kw)

    monkeypatch.setattr(delivery_mod, "run_git_soft", _fake_run_git_soft)
    monkeypatch.setattr(subprocess, "run", _stub_run())
    result = run_layer_promotion_sweep(repo, "iterate-x", "main")  # must not raise
    assert result.status == "not_delivered"
    assert "push failed" in result.reason
    assert _head_sha(repo) == pre_sha
