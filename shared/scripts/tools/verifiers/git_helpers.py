"""Generic git-invocation helpers shared across iterate verifier modules.

Extracted from ``iterate_checks.py``
(iterate-2026-06-13-risk-detector-extract) so the gates share ONE copy instead of
duplicating the wrappers or forcing a circular import. Callers today:
``integration_coverage``, ``derived_snapshot_gate``, ``ci_supplychain``,
``decision_log_gate`` and ``iterate_checks``. All functions are read-only and
never raise.

Two ways to ask what changed, and picking the wrong one is a measured defect
class: :func:`_commit_changed_paths` answers for ONE commit,
:func:`_iterate_changed_paths` for the whole branch. A gate that runs at F11 wants
the second — see its docstring for why.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal


def _run_git(
    project_root: Path, *args: str, timeout: float | None = None,
) -> tuple[int, str, str]:
    """Run ``git -C <project_root> <args>``; never raises. Returns (rc, out, err).

    ``timeout`` (seconds) is passed through to ``subprocess.run`` only when
    set; the default ``None`` preserves the original no-timeout behaviour for
    existing callers. On any failure (git missing, bad args, or — when a
    timeout is set — the command exceeding it) returns ``(1, "", "")`` so
    callers can branch on ``rc != 0`` / ``rc == 0`` uniformly.
    """
    import subprocess
    # Pass ``timeout`` to subprocess.run only when the caller set it, so an
    # un-timed call keeps the exact kwarg shape it had before this param existed.
    kwargs: dict = {"capture_output": True, "text": True,
                    "encoding": "utf-8", "errors": "ignore"}
    if timeout is not None:
        kwargs["timeout"] = timeout
    try:
        proc = subprocess.run(["git", "-C", str(project_root), *args], **kwargs)
        return proc.returncode, proc.stdout, proc.stderr
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 1, "", ""


def git_context(project_root: Path) -> Literal["work_tree", "not_git", "git_error"]:
    """Tri-state git probe: ``work_tree`` | ``not_git`` | ``git_error``.

    Callers MUST proceed only on an explicit ``work_tree`` and treat every other
    value as a refusal. Branching on the two failure names and falling through
    otherwise puts an unrecognised state on the fail-OPEN path — the one direction
    this classification exists to close. The return type is pinned in the signature
    for the same reason.

    A binary "did git exit 0" answer conflates "not a git repo" (an inapplicable
    context → SKIP) with a git SUBPROCESS failure on a real work tree (a wedged
    ``index.lock``, a stalled filesystem, a broken git binary, a permission
    failure, corrupt repo metadata, or a >10s stall). The second is an
    infrastructure failure that must fail CLOSED — reading it as "not a repo"
    green-skips a gate from inside the repository it was meant to enforce.

    Only a DEFINITIVE non-git answer is ``not_git``: rc 0 with stdout that is not ``true``,
    or git ran and said so on stderr. A synthesized failure (``_run_git`` maps OSError /
    ValueError / TimeoutExpired to ``(1, "", "")``) or any other non-zero rc without that
    stderr message is ``git_error``, so an exception can never escape unstructured.

    That first clause is a RULE, not a sample: ANY context where git exits 0 without printing
    ``true`` is ``not_git``, so a caller migrating off ``rev-parse --git-dir`` (rc only) now
    SKIPs where it proceeded — a bare repo, a ``.git`` dir, a ``GIT_WORK_TREE`` elsewhere,
    whatever else is in that set. Accepted as for the non-repo SKIP: nothing to merge.

    Lives here rather than in one verifier because both ``layer_coverage`` (which
    first drew the distinction) and ``integration_coverage`` need the same
    classification, and two copies would drift
    (iterate-2026-08-01-coverage-gate-recompute-order).
    """
    rc, out, err = _run_git(
        project_root, "rev-parse", "--is-inside-work-tree", timeout=10.0
    )
    if rc == 0:
        return "work_tree" if out.strip() == "true" else "not_git"
    lowered = (err or "").lower()
    if "not a git repository" in lowered or "not a work tree" in lowered:
        return "not_git"
    # EMPTY stderr means git never ran at all: `_run_git` synthesizes (1, "", "") for
    # OSError / ValueError / TimeoutExpired. That is unambiguously environmental, and
    # must stay git_error no matter what the filesystem looks like.
    if not lowered.strip():
        return "git_error"
    # git RAN and said something this parser does not recognise. The English
    # substrings above are not sufficient alone: git uses gettext and Git-for-Windows
    # ships translations, so a localized install returns a translated `fatal:` for a
    # genuine non-git dir — classifying that git_error would turn the documented SKIP
    # into a hard block on every non-git project. Answer structurally instead:
    # `--show-toplevel` succeeding proves a repo IS there (so the failure was
    # environmental), and no `.git` anywhere up the tree is the locale-independent
    # form of "not a repository". Filesystem errors stay fail-CLOSED.
    rc2, _, _ = _run_git(project_root, "rev-parse", "--show-toplevel", timeout=10.0)
    if rc2 == 0:
        return "git_error"
    try:
        root = Path(project_root).resolve()
        has_git = any((c / ".git").exists() for c in (root, *root.parents))
    except OSError:
        return "git_error"
    return "git_error" if has_git else "not_git"


def _commit_changed_paths(project_root: Path, commit: str) -> list[str] | None:
    """Return the repo-relative paths a commit touched, or None on git failure.

    ``core.quotePath=false`` so a non-ASCII path arrives addressable rather than
    octal-escaped inside quotes; an escaped name resolves to no file, which turned a
    content fingerprint over it into a content-INDEPENDENT one
    (iterate-2026-07-28-ci-ack-per-run-home, Stage-3 doubt review).
    """
    rc, out, _ = _run_git(
        project_root, "-c", "core.quotePath=false",
        "show", "--name-only", "--pretty=format:", commit
    )
    if rc != 0:
        return None
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


#: Bounded like ``git_context``: a wedged ``index.lock`` or a stalled filesystem
#: must degrade to a reported failure, not hang F11 with no output.
_GIT_TIMEOUT_SECONDS = 30.0


def _branch_base_commit(project_root: Path, commit: str) -> str | None:
    """Where this branch left the trunk — the NARROWEST merge-base, or ``None``.

    Not "resolve the default branch, then merge-base against it". Naming the trunk is
    the part that goes wrong, and it goes wrong while looking healthy:

    - git never prunes ``refs/remotes/origin/master`` on an upstream master→main
      rename, and ``origin/HEAD`` keeps symref'ing it. The name resolves. It is simply
      no longer the trunk.
    - a rewound or force-pushed default branch has the same shape.

    Either way the merge-base lands back at the fork point, the range sweeps in
    everything main did since, and a gate reports paths the branch never touched — at
    ERROR severity, with a printed remedy that cannot clear them. Verifying that the
    ref RESOLVES does not help: a stale ref resolves perfectly well. (Measured while
    writing this: the first version of the guarding test pointed the symref at a
    MISSING ref, which merely made ``merge-base`` fail and fall through, so it passed
    against the unhardened code and proved nothing.)

    So every candidate is scored instead of one being trusted: take the merge-base of
    each, and keep the one all the others are ancestors of. That is the fork point
    closest to ``commit`` — the narrowest honest range — and it is right for both the
    stale-symref and the rewound-trunk case without needing to tell them apart.
    """
    rc, ref, _ = _run_git(project_root, "symbolic-ref", "--short",
                          "refs/remotes/origin/HEAD", timeout=_GIT_TIMEOUT_SECONDS)
    candidates: list[str] = []
    if rc == 0 and ref.strip():
        candidates.append(ref.strip())
    # Every candidate must be a TRUNK name. More candidates is safer only under that
    # condition, and the condition is the whole point — it is not "more is safer" in
    # general. The loop keeps the NARROWEST base, so a non-trunk candidate does not
    # merely add noise: it WINS, and the narrowest possible answer is the worst one.
    #
    # `@{u}` is the trap, and it was in this list until an external review caught it.
    # A pushed PR branch tracks `origin/<its own name>`, so `merge-base(@{u}, HEAD)` is
    # HEAD itself — the narrowest base of all. It wins, the caller reads `base == commit`
    # as "already contained in the trunk", falls back to the single-commit view, and the
    # blindness this whole change removes is back through the side door. Reproduced
    # before removing it; pinned by test_the_branch_own_upstream_is_not_a_trunk_candidate.
    #
    # The local names stay: a branch is not called `main`, and if it genuinely is, the
    # on-the-trunk fallback is the correct answer anyway. They are what give the scoring
    # something to score against when only one remote ref resolves — the
    # `--single-branch`-clone-after-a-rename shape, where the lone stale candidate would
    # otherwise be returned unscored because `all(...)` over an empty rest is True.
    candidates += ["origin/main", "origin/master", "main", "master"]
    seen: set[str] = set()               # origin/HEAD usually names one of these,
    candidates = [c for c in candidates  # and re-running merge-base on it buys nothing
                  if not (c in seen or seen.add(c))]

    bases: list[str] = []
    resolved = 0
    for cand in candidates:
        rc, mb, _ = _run_git(project_root, "merge-base", cand, commit,
                             timeout=_GIT_TIMEOUT_SECONDS)
        if rc == 0 and mb.strip():
            resolved += 1
            if mb.strip() not in bases:
                bases.append(mb.strip())
    if not bases:
        return None
    if resolved == 1:
        # Exactly ONE trunk name resolved, so nothing corroborates it — and an
        # uncorroborated name is precisely the stale-`origin/master`-after-a-rename
        # shape (a `--single-branch` clone with no local trunk either). Scoring cannot
        # help: `all(...)` over an empty rest is vacuously true, so the lone base would
        # be returned as if it had been checked.
        #
        # Count RESOLUTIONS, not distinct bases. In the healthy case `origin/HEAD`,
        # `origin/main` and local `main` all resolve and all agree, which dedups to one
        # base — demanding two BASES would skip every normal run. Two independent names
        # agreeing is the corroboration; one name alone is a guess.
        return None

    def _is_ancestor(other: str, base: str) -> bool:
        """``other`` is an ancestor of ``base``. Ambiguity is NOT read as "no".

        ``merge-base --is-ancestor`` answers in the exit code: 0 yes, 1 no. But
        ``_run_git`` also returns 1 for a timeout, a missing git or a bad spawn — so
        this would be the first caller for which rc=1 is DATA rather than failure, and
        reading a dead probe as a real "no" would conclude "the candidates are
        unordered" and skip three ERROR gates at once. ``rev-list --count`` puts the
        answer in STDOUT instead: rc=0 means git answered, and a count of 0 means
        ancestor. A failure keeps rc!=0 and stays distinguishable.
        """
        rc, out, _ = _run_git(project_root, "rev-list", "--count", f"{base}..{other}",
                              timeout=_GIT_TIMEOUT_SECONDS)
        return rc == 0 and out.strip() == "0"

    for base in bases:
        # Keep the base every other base is an ancestor of: the one furthest DOWN the
        # branch, so it yields the least history and cannot import mainline's work.
        if all(_is_ancestor(other, base) for other in bases if other != base):
            return base
    # Unrelated candidates with no ordering between them: refuse rather than guess,
    # because guessing wide is what produces the false accusation above.
    return None


def _iterate_changed_paths(project_root: Path, commit: str) -> list[str] | None:
    """All paths the iterate branch changed vs its merge-base with the default
    branch — the robust full-branch view (NOT one commit), so a gate sees an edit
    even if it landed in an earlier commit than HEAD. Falls back to the
    single-commit paths when the merge-base can't be resolved.

    **Why any commit-scoped gate wants THIS and not** :func:`_commit_changed_paths`.
    F11 runs ``ensure_current`` (integrate-if-behind) BEFORE the verifier, and the
    verifier is invoked with ``--commit "$(git rev-parse HEAD)"``. When the branch
    was behind, that integrate leaves a MERGE commit on top — and a merge commit's
    changed-path set does not contain what the iterate's own commit carried.
    Measured on PR #493: the merge commit showed 5 paths and 0 forbidden ones while
    the iterate commit below it carried 11 forbidden derived snapshots, so
    ``check_no_derived_snapshots_committed`` passed and they landed on main. Five of
    main's last forty commits reached it that way, all after the gate went live.

    Lives here rather than in one verifier because the blindness is a property of
    the F11 ORDERING, not of any single check: it applies to every gate that asks
    "what did this branch change?".

    **``None`` means "I could not see", and that is not ``[]``.** An empty list from
    the merge-base path is trustworthy: the branch genuinely has no net change. An
    empty list from the FALLBACK is not — ``git show --name-only`` prints nothing for
    a merge commit, so "clean" and "blind" arrive identically. Callers already treat
    ``None`` as unavailable (skip, or fail in ``ci_supplychain``'s stricter posture),
    so folding the blind case into it fixes every gate at once instead of each
    re-deriving the distinction and getting it differently.
    """
    if not commit:
        return None
    base = _branch_base_commit(project_root, commit)
    rc, head_sha, _ = _run_git(project_root, "rev-parse", commit,
                               timeout=_GIT_TIMEOUT_SECONDS)
    on_the_trunk = rc == 0 and base is not None and head_sha.strip() == base
    # `merge-base(trunk, C) == C` means C is already CONTAINED in the trunk — not
    # merely that C is its tip. Either way there is no branch range to measure
    # (`base..commit` is empty), so "what did this branch add" is the wrong question
    # and the commit view is the honest one. Note the stray-`git add -A`-onto-main
    # case goes down the RANGE path instead: at F11 that commit is not pushed yet, so
    # the base is origin/main's tip and the range holds it.
    if base and not on_the_trunk:
        # core.quotePath=false: by default git QUOTES a non-ASCII path and escapes
        # its bytes octally (`"…r\303\251sum\303\251-check.yml"`). Consumers then
        # hold a name that addresses no file, so a content read returns "absent" on
        # BOTH sides and a content fingerprint over it becomes content-independent —
        # a measured false-green in the CI supply-chain gate
        # (iterate-2026-07-28-ci-ack-per-run-home, Stage-3 doubt review). Same idiom
        # as `lib/worktree_isolation.py`.
        rc2, out, _ = _run_git(project_root, "-c", "core.quotePath=false",
                               "diff", "--name-only", f"{base}..{commit}",
                               timeout=_GIT_TIMEOUT_SECONDS)
        if rc2 == 0:
            return [ln.strip() for ln in out.splitlines() if ln.strip()]
    # No usable base, or the range failed. The single-commit view is all that is
    # left, and on a merge commit it says nothing — so an empty answer HERE is
    # ignorance, not cleanliness, and must not be handed out as a fact.
    return _commit_changed_paths(project_root, commit) or None
