"""Where a branch left the trunk — `git_helpers._branch_base_commit`.

Every F11 gate that asks "what did this branch change?" measures against this base, so
getting it wrong is not one gate's bug: an over-wide base makes several ERROR-severity
gates report paths the branch never touched, with remedies that cannot clear them.

**Resolving the ref is not the hard part; trusting it is.** git never prunes
`refs/remotes/origin/master` on an upstream master->main rename, and `origin/HEAD`
keeps symref'ing it — the name resolves perfectly, it is simply no longer the trunk. A
rewound or force-pushed default branch looks identical. So candidates are SCORED (take
each merge-base, keep the one all the others are ancestors of) rather than one being
believed.

That distinction is why the first version of the guarding test below was worthless: it
pointed the symref at a MISSING ref, which merely made `merge-base` fail and fall
through harmlessly, so it passed against the unhardened resolver and proved nothing.
The ref has to RESOLVE for the bug to bite.
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


def test_the_helper_returns_None_when_the_base_cannot_be_resolved(git_origin_repo, make_worktree):
    """End-to-end, not monkeypatched: the premise the SKIPPED rule rests on.

    Builds the #493 shape, then removes the remote — which drops the remote-tracking
    refs, so no base resolves at all. `git show --name-only` on the merge genuinely
    prints nothing. The helper must say `None` rather than hand out that emptiness.
    """
    from tools.verifiers.git_helpers import _iterate_changed_paths

    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, "app.py", "base\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "gate-no-remote")
    _write(wt, _DASH, "a derived view\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "carries it")

    _write(work, "other.py", "main moved\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "main moves")
    _git(work, "push", "origin", "main")
    _git(wt, "fetch", "origin")
    _git(wt, "merge", "--no-ff", "--no-edit", "origin/main")

    # Nothing may resolve: drop the remote (which drops its tracking refs) AND rename
    # the local trunk out of the candidate set. Removing the remote alone is no longer
    # enough, and that is the point — local `main` is a legitimate candidate now, so a
    # remote-less checkout still gets an honest base instead of a skip.
    _git(wt, "remote", "remove", "origin")
    _git(wt, "branch", "-m", "main", "trunk-renamed-away")
    head = _git(wt, "rev-parse", "HEAD").stdout.strip()

    assert _iterate_changed_paths(wt, head) is None, (
        "an unresolvable base plus a silent merge commit is ignorance, not an empty diff"
    )


def test_a_stale_but_LIVE_origin_HEAD_does_not_blame_the_branch(git_origin_repo, make_worktree):
    """The over-wide range a stale-but-resolvable symref produces.

    git never prunes `refs/remotes/origin/master` on an upstream master->main rename,
    so a clone made before it keeps a symref naming a ref that still RESOLVES and is no
    longer the trunk. Taking that name unverified puts the merge-base back at the fork
    point, sweeps in everything main did since, and reports paths the branch never
    touched — at ERROR severity, with a printed remedy that cannot clear it.

    The ref must RESOLVE for this to bite. A symref pointing at a missing ref merely
    makes `merge-base` fail and falls through harmlessly, which is why the first
    version of this test passed against the unhardened resolver and proved nothing.
    """
    from tools.verifiers.derived_snapshot_gate import check_no_derived_snapshots_committed

    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, "app.py", "base\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "origin", "main")

    # The stale trunk: a real ref, at the OLD tip, still named by origin/HEAD.
    old_tip = _git(work, "rev-parse", "HEAD").stdout.strip()
    _git(work, "update-ref", "refs/remotes/origin/master", old_tip)
    _git(work, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/master")

    # main moves on and carries a derived path itself (measured: 8 of main's last 40).
    _write(work, _DASH, "mainline's own derived view\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "main carries a derived snapshot")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "gate-stale-symref")
    _write(wt, "app.py", "only a source change\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "feat: source only")
    head = _git(wt, "rev-parse", "HEAD").stdout.strip()

    result = check_no_derived_snapshots_committed(wt, _RUN_ID, head)

    assert result.ok is not False, (
        f"blamed the branch for mainline's derived path via a stale symref: {result.detail}"
    )


def test_a_LONE_stale_candidate_is_not_trusted_unscored(git_origin_repo, make_worktree):
    """The hole the scoring left open: `all([])` is True.

    With exactly one resolvable candidate the comparison loop has nothing to compare
    against, so the lone base was returned UNSCORED — and the one shape that produces
    a lone candidate is the very bug being fixed: a `--single-branch` clone taken
    while upstream's default was `master`, after an upstream rename. Only
    `origin/master` exists, it still resolves at the pre-rename tip, and `origin/HEAD`
    still names it.

    The fix is counter-intuitive and worth pinning: adding MORE candidates is safer,
    because the loop keeps the NARROWEST base — an extra candidate can only pull the
    base closer, never widen the range.
    """
    from tools.verifiers.git_helpers import _branch_base_commit

    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, "app.py", "base\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "origin", "main")

    old_tip = _git(work, "rev-parse", "HEAD").stdout.strip()

    _write(work, _DASH, "mainline's own derived view\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "main moves on")
    _git(work, "push", "origin", "main")
    new_tip = _git(work, "rev-parse", "HEAD").stdout.strip()

    wt = make_worktree(work, "base-lone-stale")
    _write(wt, "app.py", "source only\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "feat: source only")

    # The single-branch shape: only a STALE origin/master exists, named by origin/HEAD.
    _git(wt, "update-ref", "refs/remotes/origin/master", old_tip)
    _git(wt, "update-ref", "-d", "refs/remotes/origin/main")
    _git(wt, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/master")

    head = _git(wt, "rev-parse", "HEAD").stdout.strip()
    base = _branch_base_commit(wt, head)

    assert base != old_tip, (
        "trusted a lone stale candidate unscored — the range would sweep in "
        "everything the trunk did since the rename"
    )
    assert base == new_tip, f"expected the narrowest base ({new_tip[:8]}), got {base}"


def test_the_branch_own_upstream_is_not_a_trunk_candidate(git_origin_repo, make_worktree):
    """The regression an external review caught in the fix for the lone-candidate hole.

    "More candidates can only NARROW the base, so more is safer" is true only for
    candidates that are genuinely TRUNK refs. `@{u}` is not: a pushed PR branch tracks
    `origin/<its own name>`, so `merge-base(@{u}, HEAD)` is HEAD itself. That is the
    narrowest base of all, it wins the scoring, and the caller then reads `base ==
    commit` as "already contained in the trunk" and falls back to the single-commit
    view — reinstating the exact blindness this iterate removes, by the back door.
    """
    from tools.verifiers.git_helpers import _branch_base_commit

    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, "app.py", "base\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "origin", "main")
    trunk_tip = _git(work, "rev-parse", "HEAD").stdout.strip()

    wt = make_worktree(work, "base-own-upstream")
    _write(wt, _DASH, "a derived view in an EARLY commit\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "carries it")
    _write(wt, "app.py", "later work\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "later")

    # The ordinary PR shape: pushed, with an upstream pointing at its own remote branch.
    _git(wt, "push", "-u", "origin", "HEAD:refs/heads/iterate/base-own-upstream")
    _git(wt, "branch", "--set-upstream-to=origin/iterate/base-own-upstream")

    head = _git(wt, "rev-parse", "HEAD").stdout.strip()
    base = _branch_base_commit(wt, head)

    assert base != head, (
        "the branch's own upstream was taken as a trunk candidate, so the base "
        "collapsed to HEAD and the whole branch became invisible"
    )
    assert base == trunk_tip, f"expected the trunk tip ({trunk_tip[:8]}), got {base}"


def test_an_UNCORROBORATED_lone_trunk_name_is_refused(git_origin_repo, make_worktree):
    """The half scoring cannot reach: one candidate, nothing to compare it against.

    `all(...)` over an empty rest is vacuously true, so a lone base would be handed
    back as though it had been checked — and the shape that produces a lone candidate
    is the stale one: a `--single-branch` clone taken before an upstream rename, with
    no local trunk either. Refusing yields a SKIP, which is the documented fail-open
    posture; guessing yields an over-wide range and a false ERROR.

    The count is of RESOLUTIONS, not distinct bases. In a healthy repo `origin/HEAD`,
    `origin/main` and local `main` all resolve and all agree, deduplicating to ONE
    base — so demanding two bases would skip every normal run instead.
    """
    from tools.verifiers.git_helpers import _branch_base_commit

    work, _origin = git_origin_repo
    _set_repo_identity(work)
    _write(work, "app.py", "base\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed")
    _git(work, "push", "origin", "main")
    old_tip = _git(work, "rev-parse", "HEAD").stdout.strip()

    _write(work, _DASH, "mainline's own derived view\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "main moves on")
    _git(work, "push", "origin", "main")

    wt = make_worktree(work, "base-uncorroborated")
    _write(wt, "app.py", "source only\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "feat: source only")

    # Only a STALE origin/master survives — no origin/main, no local trunk.
    _git(wt, "update-ref", "refs/remotes/origin/master", old_tip)
    _git(wt, "update-ref", "-d", "refs/remotes/origin/main")
    _git(wt, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/master")
    _git(wt, "branch", "-m", "main", "trunk-renamed-away")

    head = _git(wt, "rev-parse", "HEAD").stdout.strip()

    assert _branch_base_commit(wt, head) is None, (
        "handed back an uncorroborated lone base — the range would sweep in "
        "everything the trunk did since the rename"
    )
