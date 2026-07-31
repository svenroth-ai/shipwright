"""What may we DO about a pull request's state?
(iterate-2026-07-31-f11-delivery-truth)

F11 arms GitHub-native auto-merge and then watches the PR to a terminal state. On a
base **without branch protection** the arm cannot be set at all —

    GraphQL: Pull request Protected branch rules not configured for this branch
    (enablePullRequestAutoMerge)

— which F11 tolerated fail-soft, and then nothing ever merged the PR: the watcher
only watched. Measured on throwaway PR #501; every iterate on such a repo ended
not-delivered after the 1800-second timeout. A private repo on GitHub Free cannot
have rulesets at all, so it could never be delivered to.

The answer is a **capability ladder with one delivery bar**: *delivered = the PR is
MERGED and every check that exists is green*. Only the actor differs — GitHub when it
can arm, this tool when it structurally cannot. The three permission questions live
here, pure, so every branch is testable without ``gh``, a clock or a subprocess:

* :func:`classify_arm_outcome` — was the refusal structural or transient;
* :func:`identity_problem` — is this PR even ours to touch;
* :func:`self_merge_allowed` — may we be the merger.

State-reading lives in ``lib/pr_readiness.py``; host calls in
``lib/pr_delivery_host.py``; the wait→refresh→verify→merge cycle in
``lib/pr_self_merge.py``; the ladder itself in ``tools/deliver_pr.py``.
"""

from __future__ import annotations

from collections.abc import Mapping

ARM_ARMED = "armed"
ARM_UNAVAILABLE = "unavailable"
ARM_BLOCKED = "blocked"
#: Arming is impossible, but the base is PROTECTED — so self-merge is refused on
#: purpose and the operator is pointed at the one-checkbox remedy (Stage 3).
ARM_SETTING_OFF = "setting_off"

# --- the delivery contract's exit codes ---------------------------------------
# Here rather than in the CLI because three places depend on them: `deliver_pr.py`
# returns them, `pr_self_merge.py` produces them, and F11's `case` block branches on
# them.
EXIT_DELIVERED = 0
EXIT_CHECKS_FAILED = 2
EXIT_CLOSED = 3
EXIT_PENDING = 4
EXIT_HOST_ERROR = 5
#: Arming is structurally impossible AND self-merge is not permitted. Distinct from
#: EXIT_PENDING precisely because re-running is futile, where on pending it is the remedy.
EXIT_NO_MERGER = 6
#: Identity mismatch, red re-verification, or the host refused the merge.
EXIT_REFUSED = 7

#: Watch verdicts that already carry their own meaning and exit code.
STATUS_EXITS = {
    "merged": EXIT_DELIVERED,
    "checks_failed": EXIT_CHECKS_FAILED,
    "closed": EXIT_CLOSED,
    "pending": EXIT_PENDING,
}

#: Host wording that, on its own, establishes the refusal is structural. It can only ever
#: PROMOTE a failure, never demote one, and it can never promote past a base that reads as
#: `protected: true` — there it yields `ARM_SETTING_OFF` (report, do not merge), because
#: believing a string over a readable fact would license a self-merge past required reviews
#: on an error message alone (external code review, HIGH). The facts remain the primary
#: discriminator, so a GitHub reword degrades to "transient, keep watching" rather than to a
#: wrong merge.
_STRUCTURAL_MARKERS = (
    "protected branch rules not configured",
    "auto merge is not allowed",
    "auto-merge is not allowed",
    "auto merge is not enabled",
)

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def delivery_result(status: str, exit_code: int, steps: list[str], **extra) -> dict:
    """One delivery verdict, in the shape every caller and every test reads."""
    return {"status": status, "exit_code": exit_code, "merged_by": None,
            "steps": steps, **extra}


def classify_arm_outcome(
    returncode: int,
    stderr: str = "",
    *,
    allow_auto_merge: bool | None = None,
    base_protected: bool | None = None,
) -> dict:
    """Was the arm refusal **structural** (it will never succeed) or transient?

    ``allow_auto_merge`` (``gh api repos/{o}/{r}``) and ``base_protected``
    (``gh api repos/{o}/{r}/branches/{base}``) are the discriminators: both are
    readable without admin rights, and ``protected`` covers rulesets **and** classic
    branch protection. An earlier draft used "the base has no rulesets", which a
    classic-protection repo answers ``[]`` to while arming works perfectly — that
    would have silently demoted a whole class of repositories to self-merge (external
    review, HIGH).

    ``None`` means the fact could not be read, and an unreadable picture stays
    **transient**: absence of evidence is not evidence, and this outcome is what
    licenses merging here.

    Returns ``{"outcome": ARM_*, "reason": str}``.
    """
    if returncode == 0:
        return {"outcome": ARM_ARMED, "reason": "auto-merge armed on the host"}

    detail = (stderr or "").strip()
    if allow_auto_merge is False and base_protected is False:
        return {"outcome": ARM_UNAVAILABLE,
                "reason": "the repository's 'Allow auto-merge' setting is off AND the base "
                          "branch has no protection, so the host cannot arm auto-merge"}
    if allow_auto_merge is False:
        # DELIBERATELY not self-merge-eligible. The base IS protected, so it carries an
        # intent — required reviews, required checks — and an iterate typically runs with
        # the operator's own token, which on their own repo may bypass exactly those
        # requirements. "The host will refuse us" is an untested assumption for a
        # bypass-capable actor (Stage 3), and the remedy here is one checkbox rather than
        # a new authority. Reported, not merged.
        return {"outcome": ARM_SETTING_OFF,
                "reason": "the repository's 'Allow auto-merge' setting is off, but the base "
                          "branch IS protected — turn 'Allow auto-merge' on rather than "
                          "having the change merged on your behalf past those rules"}
    if base_protected is False:
        return {"outcome": ARM_UNAVAILABLE,
                "reason": "the base branch has no protection, so the host cannot arm auto-merge"}

    lowered = detail.lower()
    if any(marker in lowered for marker in _STRUCTURAL_MARKERS):
        if base_protected is True:
            # The wording says "structural" while the readable fact says the base IS
            # protected. The FACT wins for the merge decision, because believing the
            # string here would license a self-merge past a protected base's required
            # reviews on an error message alone (external code review, HIGH security).
            return {"outcome": ARM_SETTING_OFF,
                    "reason": "the host refused to arm auto-merge on a base that reads as "
                              f"protected ({detail[:160]}) — check 'Allow auto-merge' and the "
                              "branch's rules rather than having the change merged on your behalf"}
        return {"outcome": ARM_UNAVAILABLE,
                "reason": f"the host refused structurally: {detail[:200]}"}

    unreadable = [name for name, value in
                  (("allow_auto_merge", allow_auto_merge), ("base protection", base_protected))
                  if value is None]
    suffix = f"; could not read {', '.join(unreadable)}" if unreadable else ""
    return {"outcome": ARM_BLOCKED,
            "reason": f"arming failed for a reason that may clear: "
                      f"{detail[:200] or 'no detail'}{suffix}"}


def campaign_defers(env: Mapping[str, str]) -> bool:
    """True when a campaign orchestrator owns the merge.

    ONE reader of ``SHIPWRIGHT_ITERATE_AUTOMERGE``. The ladder used to re-parse the same
    literal beside :func:`self_merge_allowed`, which is how two readers of one switch
    drift (Stage 2).
    """
    return (env.get("SHIPWRIGHT_ITERATE_AUTOMERGE") or "").strip() == "0"


def terminal_state_result(state: str, steps: list[str]) -> dict | None:
    """The verdict for a PR that has ALREADY finished — or ``None`` if it has not.

    Both places that read a PR's state need this, and only one of them had it: the
    preflight reported an already-merged PR as delivered, while the pre-merge re-read ran
    it through :func:`identity_problem` and returned a REFUSAL. So a PR merged by a human
    or the campaign orchestrator during the few seconds the refresh takes aborted the
    iterate over a PR that was merged and green (Stage 2).
    """
    upper = (state or "").upper()
    if upper == "MERGED":
        steps.append("the PR is already MERGED")
        result = delivery_result("merged", EXIT_DELIVERED, steps, checks_observed=None,
                                 reason="the PR was already MERGED when delivery looked")
        result["merged_by"] = "other"
        return result
    if upper == "CLOSED":
        steps.append("the PR is already CLOSED")
        return delivery_result("closed", EXIT_CLOSED, steps, checks_observed=None,
                               reason="the PR was CLOSED unmerged")
    return None


def wrong_pr(pr: Mapping, *, expected_head: str, expected_base: str,
             expected_repo: str = "") -> str:
    """Why this is not the pull request this run opened — ``""`` when it is.

    Deliberately says NOTHING about whether it is open. Conflating the two questions is
    what forced an ordering trade-off between "report a finished PR" and "check identity
    first", and the trade-off went the wrong way: a MERGED PR short-circuited to exit 0
    with no identity check at all, so any merged PR in the repo could be reported as this
    run's delivery (Stage 3). Now identity is checked unconditionally, first, and the
    terminal state is read afterwards.
    """
    # The repository, not just the branch names. A fork and its upstream both have a PR
    # with head `iterate/<slug>` and base `main`, so names alone let a `--repo
    # upstream/name` watch and a cwd-resolved merge point at different repositories.
    if expected_repo and f"/{expected_repo}/" not in f"{pr.get('url') or ''}/":
        return (f"the PR at {pr.get('url') or '(no url)'!r} is not in the expected "
                f"repository {expected_repo!r}")
    head = pr.get("headRefName") or ""
    if expected_head and head != expected_head:
        return f"the PR's head branch is {head!r}, not this run's {expected_head!r}"
    base = pr.get("baseRefName") or ""
    if expected_base and base != expected_base:
        return f"the PR targets {base!r}, not the expected {expected_base!r}"
    return ""


def identity_problem(pr: Mapping, *, expected_head: str, expected_base: str,
                     expected_repo: str = "") -> str:
    """Why this PR is not the one this run may touch — ``""`` when it is.

    Checked before **any** mutating call, and the arm counts as one: ``gh pr merge
    --auto --squash --delete-branch`` on a stale PR number or a reused checkout would
    merge and delete somebody else's branch the moment their checks went green. The
    first version of this ladder checked identity only before the merge, ~80 lines
    below the arm; Stage 1 review rejected that.
    """
    mismatch = wrong_pr(pr, expected_head=expected_head, expected_base=expected_base,
                        expected_repo=expected_repo)
    if mismatch:
        return mismatch
    if (pr.get("state") or "").upper() != "OPEN":
        return f"the PR is {pr.get('state') or 'in an unknown state'}, not OPEN"
    return ""


def self_merge_allowed(env: Mapping[str, str]) -> dict:
    """May this run merge the PR itself?

    On by default — the operator's decision, so a repository that cannot arm still
    delivers out of the box. Two ways it is refused:

    * ``SHIPWRIGHT_ITERATE_AUTOMERGE=0`` — a campaign. The orchestrator merges each PR
      in turn, interleaved-serial; this outranks the switch below, because a
      sub-iterate merging itself would break the one-PR-at-a-time invariant the
      campaign relies on.
    * ``SHIPWRIGHT_ITERATE_SELF_MERGE`` set to a false value, or to anything
      unrecognised. A typo must not silently grant merge authority, so an unusable
      value fails **closed** and is named back (external review).

    Returns ``{"allowed": bool, "reason": str}``.
    """
    if (env.get("SHIPWRIGHT_ITERATE_AUTOMERGE") or "").strip() == "0":
        return {"allowed": False,
                "reason": "a campaign is running (SHIPWRIGHT_ITERATE_AUTOMERGE=0) — "
                          "the orchestrator merges each PR in turn"}

    raw = env.get("SHIPWRIGHT_ITERATE_SELF_MERGE")
    if raw is None or not raw.strip():
        return {"allowed": True, "reason": "enabled by default"}
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return {"allowed": True, "reason": f"enabled by SHIPWRIGHT_ITERATE_SELF_MERGE={raw!r}"}
    if value in _FALSE_VALUES:
        return {"allowed": False,
                "reason": f"switched off by SHIPWRIGHT_ITERATE_SELF_MERGE={raw!r}"}
    return {"allowed": False,
            "reason": f"SHIPWRIGHT_ITERATE_SELF_MERGE={raw!r} is neither on nor off — "
                      "failing closed rather than guessing at merge authority"}


__all__ = [
    "ARM_ARMED",
    "ARM_BLOCKED",
    "ARM_SETTING_OFF",
    "ARM_UNAVAILABLE",
    "EXIT_CHECKS_FAILED",
    "EXIT_CLOSED",
    "EXIT_DELIVERED",
    "EXIT_HOST_ERROR",
    "EXIT_NO_MERGER",
    "EXIT_PENDING",
    "EXIT_REFUSED",
    "STATUS_EXITS",
    "campaign_defers",
    "classify_arm_outcome",
    "delivery_result",
    "identity_problem",
    "self_merge_allowed",
    "terminal_state_result",
    "wrong_pr",
]
