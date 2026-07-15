"""AC-6/AC-7 — `integrate_main.py` wrapper + the separate Run-ID follow-up commit.

Uses the shared `git_origin_repo` + `make_worktree` fixtures (a real bare
`origin` + a linked iterate worktree) so the merge is a genuine
`git merge origin/main` in a worktree — the real production scenario — instead
of a hand-built local-branch topology. Repo-level git identity is set so the
wrapper's OWN commits succeed on an identity-less CI runner.

The load-bearing claim (AC-6, confirmed against the real audit): regenerated MD
snapshots must live in a SEPARATE non-merge commit carrying the `Run-ID:`
trailer, because `audit_staleness.find_snapshot_commit` uses
`git log --diff-filter=AM`, which skips merge commits.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from tools import integrate_main  # noqa: E402

_AUDIT_STALENESS = (
    REPO_ROOT / "plugins" / "shipwright-compliance" / "scripts" / "audit" / "audit_staleness.py"
)
_DASH = ".shipwright/compliance/dashboard.md"
_CI_SEC = ".shipwright/compliance/ci-security.json"
_RUN_ID = "iterate-2026-05-31-churn-merge-resolver"


def _load_find_snapshot_commit():
    """Import the REAL `find_snapshot_commit` by file path (drift-proof)."""
    spec = importlib.util.spec_from_file_location("audit_staleness_probe", _AUDIT_STALENESS)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # @dataclass resolves __module__ via sys.modules
    spec.loader.exec_module(mod)
    return mod.find_snapshot_commit


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        GIT_AUTHOR_NAME="Integrate Test",
        GIT_AUTHOR_EMAIL="integrate@test.invalid",
        GIT_COMMITTER_NAME="Integrate Test",
        GIT_COMMITTER_EMAIL="integrate@test.invalid",
    )
    return env


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), env=_env(), capture_output=True, text=True, check=check
    )


def _set_repo_identity(work: Path) -> None:
    """Repo-level identity so integrate_main's OWN commits (which don't pass an
    author env) succeed even on a CI runner with no global git identity. The
    worktree shares this config via the common .git dir."""
    _git(work, "config", "user.email", "integrate@test.invalid")
    _git(work, "config", "user.name", "Integrate Test")


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_integrate_resolves_and_audit_finds_followup(git_origin_repo, make_worktree, monkeypatch) -> None:
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    # main: seed a tracked compliance MD, push.
    _write(work, _DASH, "base dashboard\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed dashboard")
    _git(work, "push", "origin", "main")
    # iterate worktree off main, with its own divergent MD change.
    wt = make_worktree(work, "churn-followup")
    _write(wt, _DASH, "iterate dashboard\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "iterate changes dashboard")
    # origin/main advances divergently on the same file.
    _write(work, _DASH, "main dashboard\n")
    _git(work, "commit", "-am", "main changes dashboard")
    _git(work, "push", "origin", "main")

    def fake_regen(project_root, run_id, **kw):
        _write(Path(project_root), _DASH, f"regenerated from merged tree ({run_id})\n")
        _git(Path(project_root), "add", "--", _DASH)
        return {_DASH: "regenerated"}

    monkeypatch.setattr(integrate_main.rcc, "regenerate_tracked_snapshots", fake_regen)

    result = integrate_main.integrate(wt, _RUN_ID, do_fetch=True)

    assert result["status"] == "ok", result
    assert "merge-committed" in result["steps"]
    assert "regenerated-followup" in result["steps"]

    # HEAD is the follow-up: a NON-merge commit (one parent) with a Run-ID trailer.
    head = _git(wt, "rev-parse", "HEAD").stdout.strip()
    parents = _git(wt, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()
    assert len(parents) == 2, "follow-up must be a non-merge commit (exactly one parent)"
    body = _git(wt, "log", "-1", "--format=%B", "HEAD").stdout
    assert f"Run-ID: {_RUN_ID}" in body

    # The REAL audit finds the follow-up (not the merge, not None) — AC-6.
    find_snapshot_commit = _load_find_snapshot_commit()
    assert find_snapshot_commit(wt) == head


def test_integrate_validates_events_on_clean_union_merge(git_origin_repo, make_worktree, monkeypatch) -> None:
    """H1 regression: when `merge=union` resolves events.jsonl silently (a clean
    merge, no conflict), validation must still run — a corrupt historic line
    introduced by the union aborts the integrate before any commit."""
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    base = '{"type":"phase_completed","id":"evt-base","v":1}'
    _write(work, ".gitattributes", "shipwright_events.jsonl merge=union\n")
    _write(work, "shipwright_events.jsonl", base + "\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed events + union attr")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "churn-events")
    _write(wt, "shipwright_events.jsonl", base + '\n{"type":"work_completed","adr_id":"iterate-x","id":"evt-run","v":1}\n')
    _git(wt, "commit", "-am", "iterate appends run event")

    _write(work, "shipwright_events.jsonl", base + "\nthis line is NOT json\n")  # corrupt
    _git(work, "commit", "-am", "main corrupts the log")
    _git(work, "push", "origin", "main")

    called = {"regen": False}
    monkeypatch.setattr(
        integrate_main.rcc, "regenerate_tracked_snapshots",
        lambda *a, **k: called.__setitem__("regen", True) or {},
    )

    result = integrate_main.integrate(wt, "iterate-x", do_fetch=True)

    assert result["status"] == "events_invalid", result
    assert called["regen"] is False
    # Aborted cleanly: no merge in progress, no unmerged paths.
    assert _git(wt, "rev-parse", "--verify", "--quiet", "MERGE_HEAD", check=False).returncode != 0
    assert _git(wt, "diff", "--name-only", "--diff-filter=U").stdout.strip() == ""


def test_integrate_aborts_and_restores_on_source_conflict(git_origin_repo, make_worktree, monkeypatch) -> None:
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, "app.py", "base\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed app.py")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "churn-source")
    _write(wt, "app.py", "iterate change\n")
    _git(wt, "commit", "-am", "iterate edits app.py")

    _write(work, "app.py", "origin change\n")
    _git(work, "commit", "-am", "main edits app.py")
    _git(work, "push", "origin", "main")

    called = {"regen": False}
    monkeypatch.setattr(
        integrate_main.rcc, "regenerate_tracked_snapshots",
        lambda *a, **k: called.__setitem__("regen", True) or {},
    )

    result = integrate_main.integrate(wt, "iterate-x", do_fetch=True)

    assert result["status"] == "blocked", result
    assert "app.py" in result["blocking"]
    assert called["regen"] is False, "regeneration must not run when blocked"
    # merge --abort restored a clean tree (no unmerged paths, nothing staged).
    assert _git(wt, "diff", "--name-only", "--diff-filter=U").stdout.strip() == ""
    assert _git(wt, "diff", "--cached", "--name-only").stdout.strip() == ""


def test_integrate_rollback_restores_ci_security_on_regen_failure(
    git_origin_repo, make_worktree, monkeypatch
) -> None:
    """Rollback parity: ci-security.json is admitted to CHURN_ALLOWLIST as a
    derived compliance snapshot, so integrate_main's restore-on-regenerate-failure
    path must restore it too — a best-effort ``refresh_ci_security`` can mutate it
    BEFORE another generator errors. Without CI_SECURITY_SUMMARY in the restore
    set, a ``regenerate_failed`` merge would leave ci-security.json dirty. Also
    pins that the merge placeholder is the mainline ``--theirs`` side (the merge
    always brings origin/<default> INTO the iterate branch — external-review F1).
    """
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, _CI_SEC, '{"critical": 0}\n')
    _write(work, _DASH, "base dashboard\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed ci-security + dashboard")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "cisec-rollback")
    _write(wt, _CI_SEC, '{"critical": 1}\n')   # iterate (ours) side
    _write(wt, _DASH, "iterate dashboard\n")
    _git(wt, "commit", "-am", "iterate")

    _write(work, _CI_SEC, '{"critical": 2}\n')  # main (theirs) side → both changed → conflict
    _write(work, _DASH, "main dashboard\n")
    _git(work, "commit", "-am", "main advances")
    _git(work, "push", "origin", "main")

    def failing_regen(project_root, run_id, **kw):
        # A best-effort ci-security refresh mutated the file BEFORE the dashboard
        # generator errored — the exact transactional hazard the rollback covers.
        _write(Path(project_root), _CI_SEC, '{"critical": 999, "mutated": true}\n')
        _git(Path(project_root), "add", "--", _CI_SEC)
        return {_DASH: "error", _CI_SEC: "regenerated"}

    monkeypatch.setattr(integrate_main.rcc, "regenerate_tracked_snapshots", failing_regen)

    result = integrate_main.integrate(wt, _RUN_ID, do_fetch=True)

    assert result["status"] == "regenerate_failed", result
    # The merge commit resolved ci-security.json to the MAINLINE --theirs side
    # (critical:2, NOT the iterate's critical:1) — external-review F1.
    committed = _git(wt, "show", "HEAD:" + _CI_SEC).stdout
    assert '"critical": 2' in committed, committed
    # Rollback restored the working tree to that merge-commit state: the mutated
    # bytes are gone and ci-security.json is clean.
    on_disk = (wt / _CI_SEC).read_text(encoding="utf-8")
    assert "mutated" not in on_disk, on_disk
    assert on_disk == committed, (on_disk, committed)
    assert _git(wt, "status", "--porcelain", "--", _CI_SEC).stdout.strip() == ""


# Campaign status.json concurrent-sibling regenerate (S3) lives in
# test_integrate_campaign_status.py (reuses _set_repo_identity / _write / _git here).
# ensure_current (the F11 / campaign refresh-if-behind guard) lives in
# test_ensure_current.py (also reuses _set_repo_identity / _write / _git here).
