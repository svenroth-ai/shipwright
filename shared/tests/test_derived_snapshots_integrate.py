"""Real-git half of the derived-snapshot suite: `integrate` and the F11 gate
(iterate-2026-07-27-derived-snapshots-off-branch).

The unit half — the registry and `restore_derived_to_head` — is in
test_derived_snapshots.py. The run-written path is its own subject and its own pair of
files: test_derived_snapshots_run_written.py (unit) and
test_run_written_ledger_integrate.py (real git). Helpers come from test_integrate_main
rather than being duplicated, the same way test_integrate_main_commit_failures does.

What these pin, beyond "the snapshot is absent": a BEHIND branch must still merge.
F5a/F5b regenerate the snapshots mid-run and F6 no longer commits them, so they sit
tracked-and-dirty — and `git merge` refuses outright once mainline touches the same
path, which is the normal case since every other iterate rewrites them too. That is
why the restore runs BEFORE the merge, and why a probe (not reasoning) found it.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402
from tools import integrate_main, integrate_merge  # noqa: E402

_DASH = ".shipwright/compliance/dashboard.md"
_RUN_ID = "iterate-2026-07-27-derived-snapshots-off-branch"


# --- integrate --------------------------------------------------------------

def test_integrate_makes_no_followup_for_derived_snapshots(
    git_origin_repo, make_worktree, monkeypatch
) -> None:
    """End-to-end: a branch that is behind integrates, and the derived snapshot
    ends up matching ``main`` — so it contributes nothing to the PR diff and cannot
    collide with a sibling iterate."""
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, _DASH, "base dashboard\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed dashboard")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "derived-off-branch")
    _write(wt, "app.py", "iterate source change\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "iterate changes source only")

    # main advances on the derived snapshot, exactly as a sibling iterate would.
    _write(work, _DASH, "main dashboard, moved on\n")
    _git(work, "commit", "-am", "main regenerates dashboard")
    _git(work, "push", "origin", "main")

    # A producer that still writes AND stages the snapshot — the hostile case.
    def fake_regen(project_root, run_id, **kw):
        _write(Path(project_root), _DASH, f"branch-local derivation ({run_id})\n")
        _git(Path(project_root), "add", "--", _DASH)
        return {_DASH: "regenerated"}

    monkeypatch.setattr(integrate_merge.rcc, "regenerate_tracked_snapshots", fake_regen)

    result = integrate_main.integrate(wt, _RUN_ID, do_fetch=True)

    assert result["status"] == "ok", result
    assert "regenerate-noop" in result["steps"], "no derived-snapshot follow-up commit"
    assert (wt / _DASH).read_text(encoding="utf-8") == "main dashboard, moved on\n"
    assert not _git(wt, "status", "--porcelain").stdout.strip(), "worktree must be clean"
    # The branch carries no diff against main on the snapshot → nothing to conflict.
    diff = _git(wt, "diff", "--name-only", "origin/main", "HEAD").stdout.split()
    assert _DASH not in diff
    assert "app.py" in diff, "the real change must still be there"


def test_a_behind_branch_still_merges_and_the_run_stays_evidenced(
    git_origin_repo, make_worktree, monkeypatch
) -> None:
    """The regression a probe caught after reasoning had it backwards.

    F5a/F5b regenerate the derived snapshots and F6 no longer commits them, so they
    sit tracked-and-dirty. ``git merge`` REFUSES outright the moment mainline
    touches the same path — the normal case, since every other iterate rewrites
    them too. With the restore placed AFTER the merge, integrate returned
    ``merge_failed`` and the branch could not advance at all. It must run BEFORE.

    Second half: once the merge succeeds the dashboard necessarily holds MAINLINE's
    marker, not this run's. That is by design, so the F11 check must read the run's
    landing from the F5c per-run entry (which ships) instead of warning on every
    behind-iterate — a by-design warning is how a gate teaches people to stop
    reading warnings.
    """
    from tools.verifiers.iterate_checks import check_build_dashboard_has_run_id

    dashb = ".shipwright/agent_docs/build_dashboard.md"
    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, dashb, "| Run: iterate-OLD-run\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed dashboard")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "behind-dash")
    _write(wt, dashb, f"| Run: {_RUN_ID}\n")        # F5b regenerated it...
    _write(wt, "app.py", "the real change\n")
    _git(wt, "add", "--", "app.py")                 # ...F6 stages ONLY the source
    _git(wt, "commit", "-m", "F6: source only")

    _write(work, dashb, "| Run: iterate-SOMEONE-ELSE\n")
    _git(work, "commit", "-am", "main regenerates dashboard")
    _git(work, "push", "origin", "main")

    monkeypatch.setattr(integrate_merge.rcc, "regenerate_tracked_snapshots", lambda *a, **k: {})
    result = integrate_main.integrate(wt, _RUN_ID, do_fetch=True)

    assert result["status"] == "ok", f"a dirty snapshot must not wedge the merge: {result}"
    assert "restored-derived" in result["steps"], "the restore must run BEFORE the merge"
    assert not _git(wt, "status", "--porcelain").stdout.strip(), "worktree must be clean"
    # The dashboard now carries mainline's marker — by design, not by accident.
    assert "iterate-SOMEONE-ELSE" in (wt / dashb).read_text(encoding="utf-8")

    # No F5c entry yet → the check still reports a real finding (it is not blind).
    assert check_build_dashboard_has_run_id(wt, _RUN_ID).ok is False

    # With the entry present the run IS evidenced, and the check stands down.
    entry = f'{{"run_id": "{_RUN_ID}", "type": "change"}}\n'
    _write(wt, f".shipwright/agent_docs/iterates/{_RUN_ID}.json", entry)
    assert check_build_dashboard_has_run_id(wt, _RUN_ID).is_skipped


# --- the F11 gate -----------------------------------------------------------

def test_gate_catches_a_derived_snapshot_that_reached_the_commit(git_origin_repo) -> None:
    """F6's add-list is prose; this is the mechanism. A stray `git add -A` is the
    realistic way the conflict class comes back, so the gate must SEE it."""
    from tools.verifiers.derived_snapshot_gate import check_no_derived_snapshots_committed

    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, "app.py", "real change\n")
    _write(work, _DASH, "a derived view that should not be here\n")
    _git(work, "add", "-A")  # the stray blanket add
    _git(work, "commit", "-m", "feat: something, plus an accident")

    result = check_no_derived_snapshots_committed(work, _RUN_ID, "HEAD")

    assert result.ok is False
    assert _DASH in result.detail
    # ERROR, not WARNING — external review's point: F11 runs the verifier WITHOUT
    # --strict, so a warning here is indistinguishable from no check at all and the
    # stray commit merges anyway. A thing called a gate has to gate.
    from tools.verifiers.common import Severity
    assert result.severity == Severity.ERROR.value


def test_gate_passes_a_commit_that_touches_only_real_files(git_origin_repo) -> None:
    from tools.verifiers.derived_snapshot_gate import check_no_derived_snapshots_committed

    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, "app.py", "real change\n")
    _git(work, "add", "--", "app.py")
    _git(work, "commit", "-m", "feat: source only")

    assert check_no_derived_snapshots_committed(work, _RUN_ID, "HEAD").ok is True


def test_gate_skips_rather_than_invents_when_it_cannot_read_the_commit(git_origin_repo) -> None:
    """Fail-open on an unreadable repo — the same posture as the other
    commit-scoped iterate checks. A gate that manufactures findings from a bad
    ref trains people to ignore it."""
    from tools.verifiers.derived_snapshot_gate import check_no_derived_snapshots_committed

    work, _origin = git_origin_repo
    _set_repo_identity(work)

    assert check_no_derived_snapshots_committed(work, _RUN_ID, "").is_skipped
    assert check_no_derived_snapshots_committed(work, _RUN_ID, "no-such-ref").is_skipped


# --- the remedy the gate prints (trg-ad29a709) -------------------------------

def test_the_remedy_never_offers_worktree_for_a_run_written_path():
    """The gate's own instructions must not destroy the ledger the carve-out saves.

    `git restore --staged --worktree` on `shipwright_test_results.json` resets the file
    on disk to its pre-iterate state, wiping the block F5 just wrote — trg-ad29a709
    verbatim, reachable by following this gate's printed remedy, which is exactly what
    an operator copies under time pressure. Unstaging alone clears the gate.
    """
    from lib.churn_merge import TEST_RESULTS
    from tools.verifiers.derived_snapshot_gate import _restore_flags

    assert _restore_flags([TEST_RESULTS]) == "--staged"
    # ...and mixed offenders take the safe flag too: one run-written path in the list
    # is enough, because the operator pastes ONE command for all of them.
    assert _restore_flags([TEST_RESULTS, ".shipwright/compliance/sbom.md"]) == "--staged"


def test_the_remedy_still_cleans_the_worktree_for_derived_paths():
    """The other branch, pinned so a future edit cannot quietly drop `--worktree` for
    the paths where it is correct: a derived snapshot left dirty keeps the tree unclean
    and a later merge can refuse."""
    from tools.verifiers.derived_snapshot_gate import _restore_flags

    assert _restore_flags([".shipwright/compliance/sbom.md"]) == "--staged --worktree"
    assert _restore_flags([".shipwright/compliance/dashboard.md",
                           ".shipwright/agent_docs/triage_inbox.md"]) == "--staged --worktree"
