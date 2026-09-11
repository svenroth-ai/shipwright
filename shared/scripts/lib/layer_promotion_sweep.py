"""Opportunistic FR ``Layers`` promotion at iterate-worktree setup.

``tools/promote_required_layers.py`` (P3.5) decides, per active requirement,
whether CI-confirmed execution evidence now justifies promoting its ``Layers``
binding from advisory (``inferred``) to explicit — but until this module, no
SKILL.md, plugin, or workflow ever invoked it: an iterate that pushed a higher
observable layer left that FR's cell stale until an operator remembered to run
the CLI by hand (`.shipwright/planning/iterate/` follow-up tracking triage card
trg-a05c4aba's sibling gap, "wire the existing promotion into the iterate
flow"). This module is the wiring, not a second writer — see that tool's own
module docstring for the promotion predicate itself.

**Why this never lands on the iterate's own branch.** F11's cross-layer
coverage gate (``tools/verifiers/_layer_coverage_core.behavior_changed_keys``)
treats ANY change to an FR's ``required_layers`` between the branch's
merge-base and HEAD as a behaviour change, and then demands an
executed-passing test at the newly-required layer from THIS RUN'S OWN
freshly-regenerated evidence (``tools/verifiers/_layer_coverage_regen.py``) —
never from the ledger this promotion just wrote (R3: an enforcing gate must
recompute, never trust a self-reported ledger). A worktree branches from
``origin/<default>``'s tip, so a promotion committed onto that branch sits
INSIDE the range the gate diffs: an iterate that never touched the promoted
FR can be HARD-failed by a promotion its own build never asked for. There is
no honest way to make F11 skip that diff without weakening the exact
recompute-don't-trust guarantee the gate exists for, so the fix is
structural: the promotion must never become part of any iterate's own
reviewed diff at all.

Instead, a found promotion ships as its **own small PR against
``origin/<default>``**, decoupled from this run — the same shape as
``references/main-repair.md``'s "repair main as its own small PR" ritual, for
the same reason (a change that belongs on the shared branch, not mixed into
whichever iterate happened to trigger noticing it). Concretely: commit the
promotion in THIS worktree (so the tool's normal working-tree write lands
somewhere real), push that one commit straight to a fresh
``chore/layer-promotion-<sha12>`` branch, then immediately hard-reset this
worktree back to its pre-promotion HEAD — the commit exists on the remote
branch, never on the iterate's own. ``gh pr create`` + a best-effort
``gh pr merge --auto --squash`` land it on its own schedule; this sweep never
waits for that PR to merge (unlike F11's own delivery — see
``lib.pr_delivery`` — this is an opportunistic side artifact, not the run's
deliverable, so "fire and forget" is the correct contract here, not the
anti-pattern it would be for the iterate's own PR).

**Never a gate.** Unlike the F11 verifiers this repo also carries, a sweep
that cannot run — no traceability manifest (most consumer projects), no
network, no ``gh`` auth, GitHub API hiccups — must never block iterate setup.
Every non-decisive outcome degrades to :func:`sweep_warnings`, exactly like
the sibling outbox sweep (``lib.sweep_outbox``) this module's shape mirrors.

**Cost + opt-out.** The subprocess call resolves CI execution evidence via
GitHub's Actions API (``ci_execution_evidence.py``) and, when HEAD itself
is not yet CI-verified, walks up to 50 first-parent commits looking for one
that is (``ci_verified_anchor.DEFAULT_MAX_COMMITS``) — the anchor walk, not
call frequency, is what makes the budget below generous. On top of that this
sweep pushes a branch and calls ``gh`` twice more. All of it is genuinely
optional network work, so ``SHIPWRIGHT_ITERATE_NO_FETCH=1`` (the same offline
override B1a's own fetch already honors) skips this sweep entirely too.

**Duplicate-PR tradeoff, accepted.** Two iterates racing through setup at
nearly the same moment can each independently decide to promote the same FR
and each open their own small PR for it — a pre-flight check for any already-
open ``chore/layer-promotion-*`` PR against the default branch closes the
common case, but it is a best-effort check, not a lock (there is no claim
step here the way ``main-repair.md`` needs one for attribution). A duplicate
is wasted CI cycles, never a correctness problem: once either merges, the
ledger's "widen never narrow" rule means every later run sees the FR already
promoted and stops proposing it.

**Orphan branches, accepted (doubt-review).** A push that succeeds but whose
``gh pr create``/auth then fails leaves a real ``chore/layer-promotion-*``
branch on the remote with no PR ever opened and nothing that later deletes
it — the local worktree is still cleanly rolled back either way, so nothing
is lost or corrupted, only a stray remote branch accumulates over repeated
occurrences. Accepted for the same reason as the duplicate-PR tradeoff above:
real cleanup would need its own claim/ownership story, and a stray branch is
inert (it never blocks a later retry, since the dedup check above only looks
at OPEN PRs).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.git_base import HOOK_GIT_TIMEOUT, TIMEOUT_RETURNCODE, run_git_soft  # noqa: E402
from lib.layer_promotion_delivery import deliver_as_own_pr  # noqa: E402
from lib.layer_promotion_ledger import DEFAULT_LEDGER_RELPATH  # noqa: E402
from lib.layer_promotion_rollback import bail as _bail  # noqa: E402
from lib.layer_promotion_rollback import extract_report_fields as _extract_report_fields  # noqa: E402
from lib.layer_promotion_rollback import untracked_paths as _untracked_paths  # noqa: E402
from lib.layer_promotion_sweep_result import (  # noqa: E402
    LayerPromotionSweepResult,
    sweep_warnings,
)

_PROMOTE_TOOL = _SCRIPTS_ROOT / "tools" / "promote_required_layers.py"
_NO_FETCH_ENV = "SHIPWRIGHT_ITERATE_NO_FETCH"

#: Generous budget for a subprocess whose dominant cost is the CI-verified-
#: anchor walk (up to 50 first-parent commits queried against the GitHub
#: Actions API when HEAD itself is not yet CI-verified — the routine case
#: right after a fresh fetch), not call frequency.
_PROMOTE_SUBPROCESS_TIMEOUT = 120.0

#: The tool's own exit codes that still carry a normal decisions report
#: (0 = every FR decided; 3 = at least one hit a named undecidable case, but
#: every FR that DID decide cleanly is still written) — see that module's
#: docstring. Anything else is this tool's own operational-failure exit (2),
#: which on a project with no traceability manifest at all is the routine case.
_REPORT_EXIT_CODES = (0, 3)


def run_layer_promotion_sweep(
    worktree_path: Path, run_id: str, default_branch: str = "main",
) -> LayerPromotionSweepResult:
    """Run the promotion tool against ``worktree_path``'s current ``HEAD``.

    Any resulting write is delivered as its own PR against ``default_branch``
    (see the module docstring) and never remains part of this worktree's own
    branch. Never raises: every failure mode this function cannot itself
    recover from is reported on the returned result, not propagated — see
    the module docstring's "never a gate" rule.
    """
    if os.environ.get(_NO_FETCH_ENV) == "1":
        return LayerPromotionSweepResult(status="skipped", reason=f"{_NO_FETCH_ENV}=1 — offline")

    # Both captured BEFORE the subprocess ever runs, not after parsing its
    # report: the tool can write the ledger/spec directly to the worktree's
    # filesystem before timing out, exiting oddly, or emitting something
    # unparseable, and every one of those early returns must still be able
    # to roll that partial write back — an unknown rollback target is the
    # one state this module must never create, since it is exactly what
    # could leave promotion residue sitting on the iterate's own branch for
    # a later, unrelated commit to sweep up (external review, PR #725 round 6).
    # ``pre_untracked`` is what keeps that rollback's cleanup scoped to only
    # what the subprocess itself newly wrote — see its use in
    # ``lib.layer_promotion_rollback.rollback_staged`` (round 7): a blanket
    # ``git clean -fd`` would delete unrelated untracked content that
    # predates this sweep entirely.
    pre_sha_result = run_git_soft(["rev-parse", "HEAD"], cwd=worktree_path)
    if pre_sha_result.returncode != 0:
        return LayerPromotionSweepResult(
            status="error", reason=f"pre_sha_rev_parse_failed: {pre_sha_result.stderr.strip()[:300]}",
        )
    pre_sha = pre_sha_result.stdout.strip()
    if not pre_sha:
        return LayerPromotionSweepResult(
            status="error", reason="pre_sha_rev_parse_failed: rev-parse HEAD exited 0 with empty stdout",
        )
    pre_untracked = _untracked_paths(worktree_path)

    try:
        # encoding="utf-8", errors="replace" (not text=True's locale-default
        # strict decoding): non-UTF-8 bytes in the tool's stdout/stderr must
        # never raise UnicodeDecodeError past this "never raises" boundary —
        # same convention as lib.git_base.run_git (external review, PR #725).
        proc = subprocess.run(
            [sys.executable, str(_PROMOTE_TOOL),
             "--project-root", str(worktree_path), "--run-id", run_id],
            cwd=worktree_path, capture_output=True,
            encoding="utf-8", errors="replace",
            timeout=_PROMOTE_SUBPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return _bail(worktree_path, pre_sha, pre_untracked, "skipped", "promote_required_layers timed out", [], 0)
    except OSError as exc:
        return _bail(
            worktree_path, pre_sha, pre_untracked, "skipped",
            f"promote_required_layers could not start: {exc}", [], 0,
        )

    if proc.returncode not in _REPORT_EXIT_CODES:
        return _bail(
            worktree_path, pre_sha, pre_untracked, "skipped",
            (proc.stdout.strip() or proc.stderr.strip() or f"exit {proc.returncode}")[:300], [], 0,
        )

    try:
        report = json.loads(proc.stdout)
    except ValueError:
        return _bail(
            worktree_path, pre_sha, pre_untracked, "error",
            "promote_required_layers produced non-JSON stdout", [], 0,
        )

    try:
        promoted, escalated, written_paths = _extract_report_fields(report)
    except ValueError as exc:
        return _bail(worktree_path, pre_sha, pre_untracked, "error", f"malformed report: {exc}", [], 0)

    # The tool writes the ledger unconditionally whenever ANY FR is promoted
    # (its own "ledger BEFORE spec.md" ordering) even on a run that, for
    # every promoted FR, hit SKIP_LIVE_CELL_HAS_RESIDUAL_TEXT and so wrote no
    # spec.md — gate on EITHER signal, not just ``written_spec_paths``.
    if not promoted and not written_paths:
        return _bail(worktree_path, pre_sha, pre_untracked, "no_change", "", promoted, escalated)

    paths = [*written_paths, DEFAULT_LEDGER_RELPATH]

    add = run_git_soft(["add", "--", *paths], cwd=worktree_path)
    if add.returncode != 0:
        # `git add` with multiple pathspecs can partially stage before hitting
        # the one that fails — roll back rather than leave that residue for a
        # later, unrelated commit to pick up.
        return _bail(
            worktree_path, pre_sha, pre_untracked, "error",
            f"add_failed: {add.stderr.strip()[:300]}", promoted, escalated,
        )

    # Gate the commit on a REAL staged delta (mirrors lib.sweep_outbox's same
    # guard): an EOL-only rewrite of an already-tracked spec.md can leave
    # nothing staged even though the tool reported a write.
    staged = run_git_soft(["diff", "--cached", "--quiet", "--", *paths], cwd=worktree_path)
    if staged.returncode == TIMEOUT_RETURNCODE:
        return _bail(worktree_path, pre_sha, pre_untracked, "error", "git_timeout: diff --cached", promoted, escalated)
    if staged.returncode == 0:
        return _bail(worktree_path, pre_sha, pre_untracked, "no_change", "", promoted, escalated)
    if staged.returncode != 1:
        # `git diff --cached --quiet` uses exit 1 for "a real staged delta
        # exists" — any OTHER nonzero (128 = a real git error, e.g. a corrupt
        # index) is a genuine failure, not a delta, and must roll back rather
        # than proceed to commit whatever got staged (external review, PR #725).
        return _bail(
            worktree_path, pre_sha, pre_untracked, "error",
            f"diff_cached_failed: exit {staged.returncode}: {staged.stderr.strip()[:300]}", promoted, escalated,
        )

    subject = f"chore(compliance): promote {len(promoted)} FR Layer(s) from confirmed CI evidence"
    commit = run_git_soft(
        ["commit", "-m", subject, "--", *paths], cwd=worktree_path, timeout=HOOK_GIT_TIMEOUT,
    )
    if commit.returncode == TIMEOUT_RETURNCODE:
        return _bail(worktree_path, pre_sha, pre_untracked, "error", "commit_timeout", promoted, escalated)
    if commit.returncode != 0:
        return _bail(
            worktree_path, pre_sha, pre_untracked, "error",
            f"commit_failed: {commit.stderr.strip()[:300]}", promoted, escalated,
        )

    status, reason, pr_url, branch = deliver_as_own_pr(worktree_path, default_branch, pre_sha, subject)
    return LayerPromotionSweepResult(
        status=status, reason=reason, promoted=promoted, escalated=escalated,
        pr_url=pr_url, branch=branch,
    )


__all__ = ["LayerPromotionSweepResult", "run_layer_promotion_sweep", "sweep_warnings"]
