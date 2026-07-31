"""What F11 SEES in an iterate commit — `check_no_derived_snapshots_committed`.

Split from test_derived_snapshots_integrate.py, which tests what `integrate` DOES to
the derived snapshots. This one tests what the gate afterwards can and cannot see;
they share only the fixture helpers.

The gate is ERROR severity and NOT `--strict`-exempt, because F11 invokes the verifier
without `--strict` — a warning there is indistinguishable from no check at all, and
the stray commit merges anyway.

**Its subject is the BRANCH, not the commit at the tip.** F11 runs `ensure_current`
before the verifier, so on a behind branch HEAD is a merge commit whose changed-path
set does not contain what the iterate's own commit carried. Measured on PR #493: the
merge showed 5 paths and 0 forbidden while the commit below it carried 11. Five of
main's last forty commits reached main that way, all after this gate went live. Hence
`_iterate_changed_paths`, and hence the SKIPPED-not-PASS rule when even that comes
back empty.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402

_DASH = ".shipwright/compliance/dashboard.md"
_RUN_ID = "iterate-2026-07-27-derived-snapshots-off-branch"


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


# --- the blindness the gate had while HEAD was a merge commit ----------------

def test_the_gate_sees_a_snapshot_carried_by_an_earlier_commit(git_origin_repo, make_worktree):
    """PR #493's shape, which the gate passed while eleven forbidden files landed.

    F11 runs `ensure_current` (integrate-if-behind) BEFORE the verifier, and hands it
    `--commit $(git rev-parse HEAD)`. When the branch was behind, HEAD is the MERGE
    that integrate just made — and a merge commit's changed-path set does not contain
    what the iterate's own commit carried. The gate inspected that merge, reported
    "none derived", and the snapshots merged into main.

    The measurement is in `git_helpers._iterate_changed_paths`. The subject is the
    BRANCH, not the tip — so this builds exactly that shape: the offending commit is
    not HEAD, a merge sits on top of it, and the gate must still see it.
    """
    from tools.verifiers.derived_snapshot_gate import check_no_derived_snapshots_committed

    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, "app.py", "base\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "gate-sees-branch")
    _write(wt, "app.py", "the real change\n")
    _write(wt, _DASH, "a derived view that must not ship\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "feat: something, plus an accident")   # <- carries it

    # main moves, so the branch must integrate -> a MERGE commit lands on top.
    _write(work, "other.py", "main moved on\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "main moves")
    _git(work, "push", "origin", "main")
    _git(wt, "fetch", "origin")
    _git(wt, "merge", "--no-ff", "--no-edit", "origin/main")

    head = _git(wt, "rev-parse", "HEAD").stdout.strip()
    parents = _git(wt, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()
    assert len(parents) == 3, "the fixture must really put a MERGE commit on top"

    result = check_no_derived_snapshots_committed(wt, _RUN_ID, head)

    assert result.ok is False, (
        "the gate inspected only the merge commit and missed the snapshot below it"
    )
    assert _DASH in result.detail


def test_the_gate_still_ignores_what_MAIN_changed(git_origin_repo, make_worktree):
    """The other direction, so the widening cannot become a false accusation.

    Looking at a RANGE risks blaming the branch for a derived snapshot that arrived
    from mainline through the merge. It does not, because the range is measured from
    the merge-base with the default branch: whatever main contributed sits on the base
    side and is not part of what this branch changed.
    """
    from tools.verifiers.derived_snapshot_gate import check_no_derived_snapshots_committed

    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, "app.py", "base\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "gate-not-blaming-main")
    _write(wt, "app.py", "only a source change\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "feat: source only")

    # MAIN commits the derived snapshot (that is the defect this fixes elsewhere) and
    # the branch merges it in. The branch itself never touched it.
    _write(work, _DASH, "mainline wrote this\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "main carries a derived snapshot")
    _git(work, "push", "origin", "main")
    _git(wt, "fetch", "origin")
    _git(wt, "merge", "--no-ff", "--no-edit", "origin/main")

    head = _git(wt, "rev-parse", "HEAD").stdout.strip()
    result = check_no_derived_snapshots_committed(wt, _RUN_ID, head)

    assert result.ok is True, f"blamed the branch for mainline's snapshot: {result.detail}"
    # ...and it SAW something while saying so. Without this, a helper that always
    # returned [] would satisfy the assertion above — and that helper is exactly the
    # blindness this iterate removes, so the guard has to exclude it.
    assert "0 path(s)" not in result.detail, result.detail


def test_a_diff_the_gate_cannot_obtain_is_SKIPPED_not_passed(git_origin_repo, monkeypatch):
    """`None` is "I could not see" and must never be reported as clean.

    `_iterate_changed_paths` returns `None` when the merge-base view was unavailable
    AND the single-commit fallback said nothing — on a merge HEAD that fallback always
    says nothing, so the two are indistinguishable there. Reporting it as a pass is the
    false-green this iterate removes, arriving through the side door.

    Fail-OPEN remains the posture; fail-open means SKIPPED, not PASS.
    """
    from tools.verifiers import derived_snapshot_gate as dsg
    from tools.verifiers.common import Severity

    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, "app.py", "x\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")

    monkeypatch.setattr(dsg, "_iterate_changed_paths", lambda *_a, **_k: None)
    result = dsg.check_no_derived_snapshots_committed(work, _RUN_ID, "HEAD")

    assert result.ok is not True, "a gate that cannot see must not report clean"
    assert result.severity == Severity.SKIPPED.value
    assert "unavailable" in result.detail


def test_an_empty_branch_diff_is_clean_not_blind(git_origin_repo, make_worktree):
    """The other side of the coin, so the SKIPPED rule cannot over-fire.

    `[]` from the merge-base path is a FACT: the branch has no net change vs the
    trunk. Only the fallback's emptiness is ignorance. Confusing them would make
    every no-op branch skip a gate it should have passed.

    The branch COMMITS and then REVERTS, so the range is genuinely empty while HEAD
    is still ahead of the base. An earlier version just branched and changed nothing —
    which made HEAD == base and quietly exercised the on-the-trunk fallback instead,
    passing on a 1-path answer while claiming to pin the empty-range rule.
    """
    from tools.verifiers import derived_snapshot_gate as dsg

    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, "app.py", "x\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "gate-noop-branch")
    _write(wt, "app.py", "changed\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "change it")
    _write(wt, "app.py", "x\n")                    # ...and put it back
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "revert it")

    head = _git(wt, "rev-parse", "HEAD").stdout.strip()
    base = _git(wt, "merge-base", "origin/main", "HEAD").stdout.strip()
    assert head != base, "the fixture must leave HEAD ahead, or it tests the trunk path"

    result = dsg.check_no_derived_snapshots_committed(wt, _RUN_ID, head)

    assert result.ok is True, result.detail
    assert result.severity != "skipped", "an empty RANGE is a fact, not ignorance"
    assert "0 path(s)" in result.detail, result.detail


