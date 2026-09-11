"""Delivery mechanics for :mod:`layer_promotion_sweep`'s "own small PR" shape.

Split out purely to keep that module under the file-size guideline. Every
network call here reuses an EXISTING hardened helper rather than a third
hand-rolled "never raise" wrapper (Stage-2 review, round 2: a first attempt
at this duplicated ``lib.pr_delivery_host``'s own ``gh``/``_run`` almost
line-for-line, with strictly worse safety properties) — ``git push``/
``rev-parse``/``reset`` all go through ``lib.git_base.run_git_soft``, and
every ``gh`` call goes through ``lib.pr_delivery_host.gh``. Both degrade a
timeout or a missing binary into a failed ``CompletedProcess`` instead of
raising: an ESCAPING exception here would abort ``setup_iterate_worktree``
AFTER ``git worktree add`` already succeeded, orphaning the new worktree
(the exact hazard both helpers' own docstrings name). ``deliver_as_own_pr``
checks the final reset's own returncode rather than firing it from an
unconditional ``finally`` (Stage-2 review, round 3: the ``finally`` shape
discarded that returncode, so an unreadable ``pre_sha`` or a failing reset
went unreported — the ``"rollback_failed"`` status below exists for exactly
that case). See ``layer_promotion_sweep``'s module docstring for why this
exists at all (never lets the promotion commit reach the iterate's own
branch) and its "duplicate-PR tradeoff, accepted" note for why the
pre-flight check below is advisory, not a lock.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.git_base import HOOK_GIT_TIMEOUT, run_git_soft  # noqa: E402
from lib.pr_delivery_host import gh, gh_json  # noqa: E402
from repo_identity import resolve_repo_identity  # noqa: E402

#: Best-effort budget for each individual git/gh network call this module
#: makes once a promotion is found (push, PR create, automerge arm).
_DELIVERY_SUBPROCESS_TIMEOUT = 30.0

BRANCH_PREFIX = "chore/layer-promotion-"


def _repo_args(worktree_path: Path) -> list[str]:
    """``["--repo", "owner/name"]``, or ``[]`` when it cannot be resolved.

    Every other ``gh``-calling module in this repo pins ``--repo`` explicitly
    (``lib.pr_delivery_host``'s own docstring: "the repository is never
    inferred from a remote") — this module dropped that property when it
    first reused ``gh``/``gh_json`` directly instead of ``Host`` (doubt-review
    finding). An unresolvable identity (non-GitHub origin, detached worktree)
    still falls back to ``gh``'s own remote inference rather than blocking."""
    repo = resolve_repo_identity(worktree_path)
    return ["--repo", repo] if repo else []


def _existing_promotion_pr(worktree_path: Path, default_branch: str) -> str:
    """URL of an already-open ``chore/layer-promotion-*`` PR against
    ``default_branch``, or ``""``. Best-effort — any ``gh`` failure reads as
    "none found", never as a reason to block.

    Filters client-side rather than via ``gh pr list --search head:...``:
    GitHub's ``head:`` search qualifier matches an EXACT branch name, and
    every real branch here carries a unique ``<sha12>`` suffix, so a prefix
    search would never match anything — a silent no-op dedup check."""
    rows = gh_json(
        ["pr", "list", "--state", "open", "--base", default_branch,
         "--json", "url,headRefName", "--limit", "100", *_repo_args(worktree_path)],
        cwd=worktree_path,
    )
    for row in rows or []:
        if str(row.get("headRefName") or "").startswith(BRANCH_PREFIX):
            return row.get("url") or ""
    return ""


def _attempt_delivery(
    worktree_path: Path, default_branch: str, subject: str,
) -> tuple[str, str, str, str]:
    """The delivery attempt itself, with no knowledge of rollback — every
    call here goes through :func:`run_git_soft`/``gh``, neither of which
    raises, so this always returns rather than propagating an exception past
    :func:`deliver_as_own_pr`'s own, separate rollback step."""
    rev_parse = run_git_soft(["rev-parse", "HEAD"], cwd=worktree_path)
    if rev_parse.returncode != 0:
        return "not_delivered", f"rev-parse failed: {rev_parse.stderr.strip()[:300]}", "", ""
    branch = f"{BRANCH_PREFIX}{rev_parse.stdout.strip()[:12]}"

    existing = _existing_promotion_pr(worktree_path, default_branch)
    if existing:
        return "not_delivered", f"a promotion PR is already open: {existing}", "", branch

    push = run_git_soft(
        ["push", "origin", f"HEAD:refs/heads/{branch}"],
        cwd=worktree_path, timeout=_DELIVERY_SUBPROCESS_TIMEOUT,
    )
    if push.returncode != 0:
        return "not_delivered", f"push failed: {push.stderr.strip()[:300]}", "", branch

    repo_args = _repo_args(worktree_path)
    create = gh(
        ["pr", "create", "--base", default_branch, "--head", branch,
         "--title", subject, "--body",
         "Opportunistic FR Layers promotion from CI-confirmed execution "
         "evidence, opened at iterate worktree setup — see "
         "shared/scripts/tools/promote_required_layers.py.", *repo_args],
        cwd=worktree_path,
    )
    if create.returncode != 0:
        return "not_delivered", f"pr create failed: {create.stderr.strip()[:300]}", "", branch
    pr_url = create.stdout.strip().splitlines()[-1] if create.stdout.strip() else ""

    gh(["pr", "merge", branch, "--auto", "--squash", *repo_args], cwd=worktree_path)
    return "delivered", "", pr_url, branch


def deliver_as_own_pr(
    worktree_path: Path, default_branch: str, pre_sha: str, subject: str,
) -> tuple[str, str, str, str]:
    """Push the just-made local commit to its own remote branch, open a PR
    against ``default_branch``, best-effort-arm automerge, then ALWAYS reset
    ``worktree_path`` back to ``pre_sha`` — the commit must never remain part
    of the iterate's own branch, whether delivery succeeds or not.

    Returns ``(status, reason, pr_url, branch)``. ``status`` is
    ``"delivered"``/``"not_delivered"`` when the reset back to ``pre_sha``
    itself succeeds — the commit is rolled back out of ``worktree_path``
    either way, so ``not_delivered`` never loses anything, it only means the
    next run's sweep will find the same promotion again. ``status`` is the
    loud, distinct ``"rollback_failed"`` when ``pre_sha`` was never captured
    or the reset call itself failed/timed out — the one outcome where the
    commit may still be sitting on the iterate's own branch (Stage-2 review
    finding: the previous ``finally``-based reset discarded this signal).
    """
    status, reason, pr_url, branch = _attempt_delivery(worktree_path, default_branch, subject)

    if not pre_sha:
        return "rollback_failed", f"{reason + '; ' if reason else ''}no pre-promotion HEAD sha captured", pr_url, branch

    reset = run_git_soft(["reset", "--hard", pre_sha], cwd=worktree_path, timeout=HOOK_GIT_TIMEOUT)
    if reset.returncode != 0:
        detail = f"reset to {pre_sha[:12]} failed: {reset.stderr.strip()[:300]}"
        return "rollback_failed", f"{reason + '; ' if reason else ''}{detail}", pr_url, branch

    return status, reason, pr_url, branch


__all__ = ["deliver_as_own_pr", "BRANCH_PREFIX"]
