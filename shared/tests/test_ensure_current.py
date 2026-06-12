"""`tools/ensure_current.py` — the F11 / campaign "refresh-if-behind" guard
(iterate-2026-06-12-automerge-serial-integrate — Auto-merge churn fix, Option A).

`ensure_current` is the single primitive both the F11 single-iterate guard and
the campaign serial drain call before a branch merges: bring it current with
`origin/<default>` through `integrate_main` (regenerating the derived snapshots)
so the merge never relies on GitHub's server-side 3-way merge, which CANNOT run
the regenerate-at-merge resolver. The JSON contract it returns
(`status`/`action`/`behind`/`integrated`/`steps`) is the producer->consumer
boundary the F11 + campaign prose parse, so these tests round-trip those keys.

Reuses the shared `git_origin_repo` + `make_worktree` conftest fixtures and the
`_git` / `_set_repo_identity` / `_write` helpers from `test_integrate_main` (same
import pattern as `test_integrate_campaign_status`).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # so a standalone run resolves the helper module

from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402
from tools import ensure_current as ec  # noqa: E402
from tools import integrate_main  # noqa: E402  (monkeypatch target: ec delegates to integrate_main.integrate)

_DASH = ".shipwright/compliance/dashboard.md"
_RUN_ID = "iterate-2026-06-12-automerge-serial-integrate"


def test_ensure_current_noop_when_current(git_origin_repo, make_worktree, monkeypatch) -> None:
    """A branch already current with origin/<default> is a clean no-op: no
    integrate, no new commit, `action == already-current`, `integrated == False`.
    This pins the regression AC — the common single-iterate auto-merge path is
    unchanged (the guard adds nothing when the branch is current)."""
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "ensure-current-noop")
    head_before = _git(wt, "rev-parse", "HEAD").stdout.strip()

    # integrate() must NOT be reached when the branch is current.
    monkeypatch.setattr(
        integrate_main.rcc, "regenerate_tracked_snapshots",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("regen must not run when current")),
    )

    result = ec.ensure_current(wt, "iterate-x", do_fetch=True)

    assert result["status"] == "ok", result
    assert result["action"] == "already-current", result
    assert result["integrated"] is False, result
    assert result["behind"] == 0, result
    assert _git(wt, "rev-parse", "HEAD").stdout.strip() == head_before, "branch must not advance"


def test_ensure_current_integrates_when_behind(git_origin_repo, make_worktree, monkeypatch) -> None:
    """A branch behind origin/<default> integrates: the merge + a regenerated
    snapshot follow-up commit land, the branch advances, and the contract reports
    `action == integrated`, `integrated == True`, `behind > 0`."""
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, _DASH, "base dashboard\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed dashboard")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "ensure-current-behind")
    _write(wt, _DASH, "iterate dashboard\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "iterate changes dashboard")
    head_before = _git(wt, "rev-parse", "HEAD").stdout.strip()

    # origin/main advances divergently on the same churn MD -> branch goes behind.
    _write(work, _DASH, "main dashboard\n")
    _git(work, "commit", "-am", "main changes dashboard")
    _git(work, "push", "origin", "main")

    def fake_regen(project_root, run_id, **kw):
        _write(Path(project_root), _DASH, f"regenerated ({run_id})\n")
        _git(Path(project_root), "add", "--", _DASH)
        return {_DASH: "regenerated"}

    monkeypatch.setattr(integrate_main.rcc, "regenerate_tracked_snapshots", fake_regen)

    result = ec.ensure_current(wt, _RUN_ID, do_fetch=True)

    assert result["status"] == "ok", result
    assert result["action"] == "integrated", result
    assert result["integrated"] is True, result
    assert result["behind"] >= 1, result
    assert "merge-committed" in result["steps"]
    assert "regenerated-followup" in result["steps"]
    assert _git(wt, "rev-parse", "HEAD").stdout.strip() != head_before, "branch must advance"


def test_ensure_current_blocks_on_source_conflict(git_origin_repo, make_worktree, monkeypatch) -> None:
    """A behind branch whose merge collides on real source (a non-churn file)
    surfaces `status == blocked` and never regenerates — same hard safety gate as
    integrate(): the merge is aborted, the tree restored, `integrated == False`."""
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, "app.py", "base\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed app.py")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "ensure-current-block")
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

    result = ec.ensure_current(wt, "iterate-x", do_fetch=True)

    assert result["status"] == "blocked", result
    assert result["integrated"] is False, result
    assert "app.py" in result.get("blocking", ""), result
    assert called["regen"] is False, "regeneration must not run when blocked"
    assert _git(wt, "diff", "--name-only", "--diff-filter=U").stdout.strip() == ""


def test_ensure_current_cli(git_origin_repo, make_worktree, capsys) -> None:
    """`ensure_current.py` on a current branch prints the already-current contract
    as JSON and exits 0 (the F11 guard's happy path)."""
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    wt = make_worktree(work, "ensure-current-cli")

    rc = ec.main(["--project-root", str(wt), "--run-id", "iterate-x", "--no-fetch"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"action": "already-current"' in out
    assert '"integrated": false' in out
