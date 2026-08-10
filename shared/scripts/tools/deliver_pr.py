#!/usr/bin/env python3
"""Deliver an iterate PR — the F11 capability ladder
(iterate-2026-07-31-f11-delivery-truth).

**One delivery bar, three repositories.** *Delivered = the PR is MERGED and every
check that exists is green.* Only the actor differs:

0. **Is this PR ours?** Before anything mutating — and the arm IS mutating, since
   ``--auto --squash --delete-branch`` merges and deletes a branch once its checks go
   green — the PR's open state, head branch and base branch must match this run.
1. **Arm** ``gh pr merge --auto --squash --delete-branch``, ``iterate/*`` only. Armed
   ⇒ the host merges when green and this tool only watches. Unchanged behaviour.
2. **A refusal is classified from facts, not wording** (:mod:`lib.pr_delivery`).
   Transient ⇒ keep watching, exactly as today.
3. **Structurally impossible ⇒ deliver it here** (:mod:`lib.pr_self_merge`).

Rung 3 exists because a base branch without protection cannot arm auto-merge at all
(``Protected branch rules not configured for this branch``), so *nothing* merged the
PR and every iterate on such a repo ended not-delivered after a 1800-second timeout. A
private repo on GitHub Free cannot have rulesets, so it could never be delivered to.

Kept out of ``watch_pr_delivery.py`` deliberately: that tool's ``--once`` mode exists
so a human can ask "why is this PR stuck?", and a diagnostic that can merge is not one
you run casually. The pure decisions live in :mod:`lib.pr_delivery` and
:mod:`lib.pr_readiness`, the host calls in :mod:`lib.pr_delivery_host`.

Exit codes: 0 delivered · 2 checks failed · 3 closed unmerged · 4 pending timeout ·
5 host error · 6 no merger can exist (arming impossible, self-merge not permitted) ·
7 delivery refused (identity mismatch, re-verification red, or the merge failed).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.deliver_pr_compliance_audit import run_merge_compliance_audit  # noqa: E402
from lib.deliver_pr_timing import (  # noqa: E402
    delivery_root_span,
    delivery_wait_span,
    instrument_watch,
    timed_self_merge_call,
)
from lib.pr_delivery_host import HOST_ERRORS, Host  # noqa: E402
from lib.pr_delivery import (  # noqa: E402
    ARM_SETTING_OFF,
    ARM_UNAVAILABLE,
    campaign_defers,
    EXIT_CHECKS_FAILED,
    EXIT_CLOSED,
    EXIT_DELIVERED,
    EXIT_HOST_ERROR,
    EXIT_NO_MERGER,
    EXIT_PENDING,
    EXIT_REFUSED,
    STATUS_EXITS,
    classify_arm_outcome,
    delivery_result,
    self_merge_allowed,
    terminal_state_result,
    wrong_pr,
)
from lib.pr_self_merge import self_merge  # noqa: E402
from lib.run_pointer_retirement import retire_run_pointer_best_effort  # noqa: E402
from tools import watch_pr_delivery as wpd  # noqa: E402

__all__ = [
    "EXIT_CHECKS_FAILED", "EXIT_CLOSED", "EXIT_DELIVERED", "EXIT_HOST_ERROR",
    "EXIT_NO_MERGER", "EXIT_PENDING", "EXIT_REFUSED", "deliver", "summary",
]


def deliver(
    pr_url: str,
    *,
    project_root: Path,
    run_id: str,
    head_branch: str,
    base_branch: str,
    repo: str,
    env: dict | None = None,
    timeout_seconds: float = 1800.0,
    poll_seconds: float = 30.0,
    arm: bool = True,
    host: Host | None = None,
    watch=None,
    verified_commit: str = "",
    now=None,
    record_timing: bool = False,
) -> dict:
    """Run the ladder. Returns ``{"status", "exit_code", "merged_by", "steps", …}``.

    ``record_timing`` (default OFF — every existing caller is unaffected)
    opts into best-effort delivery/ci_wait producer spans; only :func:`main`
    turns this on."""
    env = dict(os.environ if env is None else env)
    watch = watch or wpd.watch
    # NOT wrapped here: `watch` also reaches self_merge()'s own internal retry
    # loop (rung 3) unchanged below — wrapping it at this level would record a
    # ci_wait span per internal poll AND another one for the whole self_merge()
    # call, duplicating and mislabeling the rung-3 data (code review).
    # instrument_watch is applied only at the rung-2 call site inside
    # _run_ladder, where "watch" really does mean "wait for the host".

    def _body() -> dict:
        """The ladder's own decisions — a closure so record_timing needs no
        second copy of this whole parameter list to wrap it conditionally."""
        return _run_ladder(pr_url, project_root=project_root, run_id=run_id,
                           head_branch=head_branch, base_branch=base_branch, repo=repo,
                           env=env, timeout_seconds=timeout_seconds, poll_seconds=poll_seconds,
                           arm=arm, host=host, watch=watch, verified_commit=verified_commit,
                           now=now, record_timing=record_timing)

    if not record_timing:
        return _body()
    # Self-records its own root ("delivery") — no SKILL mark needed first.
    with delivery_root_span(project_root, run_id):
        with delivery_wait_span(project_root, run_id) as extra:
            result = _body()
            if extra is not None:
                extra["conclusion"] = str(result.get("status", ""))[:200]
    return result


def _run_ladder(
    pr_url: str,
    *,
    project_root: Path,
    run_id: str,
    head_branch: str,
    base_branch: str,
    repo: str,
    env: dict,
    timeout_seconds: float,
    poll_seconds: float,
    arm: bool,
    host: Host | None,
    watch,
    verified_commit: str,
    now,
    record_timing: bool,
) -> dict:
    """The ladder's own decisions — unchanged by timing instrumentation."""
    # ONE bundle, so no member can be half-faked. The six seams used to be six loose
    # parameters whose defaults were not consistent with each other: `capability` closed
    # over the MODULE-level `gh_json`, so faking `gh_json` alone still fired real
    # `gh api` calls at the operator's live GitHub (Stage 2).
    host = host or Host.default(repo=repo)
    steps: list[str] = []

    # --- step 0: is this PR even ours? -----------------------------------------
    preflight = host.call_json(["pr", "view", pr_url, "--json",
                                "state,headRefName,baseRefName,headRefOid,url"],
                               cwd=project_root)
    if preflight is None:
        steps.append("could not read the PR before arming")
        return delivery_result("host_error", EXIT_HOST_ERROR, steps, checks_observed=None,
                              reason="the PR could not be read at all — refusing to arm or "
                                     "merge a PR whose identity is unknown")
    # Identity FIRST, and unconditionally. Reading the terminal state first meant a
    # MERGED PR short-circuited to exit 0 with NO identity check at all — so any merged PR
    # in the repo could be reported as this run's delivery, which is reachable whenever
    # `gh pr view <branch>` resolves a previously merged PR for a re-used slug (Stage 3).
    problem = wrong_pr(preflight, expected_head=head_branch,
                       expected_base=base_branch, expected_repo=repo)
    if problem:
        steps.append(f"identity refused before arming: {problem}")
        return delivery_result("refused", EXIT_REFUSED, steps, checks_observed=None,
                              reason=f"refusing to touch this PR: {problem}")

    # Only now: a PR that already reached a terminal state is REPORTED, not refused. F11
    # tells the operator to re-run delivery on a timeout or a host error, so a re-run
    # after the merge landed must not turn a delivered PR into a failure.
    finished = terminal_state_result(str(preflight.get("state") or ""), steps)
    if finished is not None:
        return finished

    if (preflight.get("state") or "").upper() != "OPEN":
        steps.append("the PR is in a state delivery does not act on")
        return delivery_result("refused", EXIT_REFUSED, steps, checks_observed=None,
                              reason=f"the PR is {preflight.get('state')!r}, not OPEN")

    permission = self_merge_allowed(env)
    campaign_defer = campaign_defers(env)

    # --- step 1: arm, unless a campaign says the orchestrator merges -----------
    if campaign_defer or not arm:
        steps.append("arm skipped (campaign defer)" if campaign_defer else "arm skipped")
        outcome = {"outcome": "deferred",
                   "reason": "the orchestrator merges this PR in turn"}
    else:
        proc = host.call(["pr", "merge", pr_url, "--auto", "--squash", "--delete-branch"],
                         cwd=project_root)
        caps = ({"allow_auto_merge": None, "base_protected": None}
                if proc.returncode == 0
                else host.capability(repo, base_branch, cwd=project_root,
                                     reader=host.gh_json))
        outcome = classify_arm_outcome(
            proc.returncode, (proc.stderr or "").strip(),
            allow_auto_merge=caps.get("allow_auto_merge"),
            base_protected=caps.get("base_protected"),
        )
        steps.append(f"arm: {outcome['outcome']} — {outcome['reason']}")

    self_merging = outcome["outcome"] == ARM_UNAVAILABLE

    # A PROTECTED base whose auto-merge setting is merely switched off is NOT
    # self-merge-eligible: the protection expresses required reviews and checks, an
    # iterate usually runs with the operator's own possibly bypass-capable token, and the
    # remedy is one checkbox rather than a new authority (Stage 3).
    if outcome["outcome"] == ARM_SETTING_OFF:
        steps.append("self-merge not offered on a protected base")
        return delivery_result("no_merger", EXIT_NO_MERGER, steps, checks_observed=None,
                              reason=outcome["reason"])

    # --- the honest fast failure ----------------------------------------------
    # No merger can exist AND we may not be one. Waiting here IS the bug being fixed:
    # 1800 seconds spent watching for something that will never happen.
    if self_merging and not permission["allowed"]:
        steps.append(f"self-merge refused — {permission['reason']}")
        return delivery_result("no_merger", EXIT_NO_MERGER, steps, checks_observed=None,
                              reason=f"{outcome['reason']}; and {permission['reason']}")

    # --- step 2: the host will merge it — just watch, exactly as today ---------
    if not self_merging:
        rung2_watch = instrument_watch(watch, project_root, run_id) if record_timing else watch
        try:
            verdict = rung2_watch(pr_url, repo=repo, timeout_seconds=timeout_seconds,
                                  poll_seconds=poll_seconds)
        except HOST_ERRORS as exc:
            # `watch_pr_delivery.main` mapped a gh failure to exit 5; keep that,
            # rather than aborting with a traceback (Stage 1 review).
            steps.append("watch: host error")
            return delivery_result("host_error", EXIT_HOST_ERROR, steps,
                                  checks_observed=None,
                                  reason="the host could not be read while waiting: "
                                         f"{type(exc).__name__}: {exc}")
        steps.append(f"watch: {verdict['status']}")
        result = delivery_result(verdict["status"],
                                STATUS_EXITS.get(verdict["status"], EXIT_PENDING),
                                steps, watch=verdict, checks_observed=None)
        if verdict["status"] == "merged":
            result["merged_by"] = "host"
        return result

    # --- step 3: deliver it here ----------------------------------------------
    def _call_self_merge() -> dict:
        return self_merge(
            pr_url, project_root=project_root, run_id=run_id, head_branch=head_branch,
            base_branch=base_branch, repo=repo, steps=steps,
            timeout_seconds=timeout_seconds, poll_seconds=poll_seconds,
            watch=watch, host=host, verified_commit=verified_commit,
            **({"now": now} if now is not None else {}),
        )
    if not record_timing:
        return _call_self_merge()
    return timed_self_merge_call(project_root, run_id, _call_self_merge)


def summary(result: dict) -> str:
    """The line the operator reads: who merged it, and on what evidence."""
    status = result["status"]
    if status == "merged":
        if result.get("merged_by") == "shipwright":
            passed = result.get("checks_passed")
            passed = (result.get("checks_observed") or 0) if passed is None else passed
            evidence = (f"the host ran {passed} passing check(s)" if passed else
                        "the host confirmed NOTHING — no check passed, so the local test "
                        "suite is the only evidence")
            return f"DELIVERED — merged by Shipwright itself; {evidence}."
        return "DELIVERED — PR merged + all Required Checks green (merged by the host)."
    if status == "no_merger":
        return ("NOT DELIVERED — no merger can exist: " + result.get("reason", "") +
                ". Merge it yourself, or allow Shipwright to "
                "(SHIPWRIGHT_ITERATE_SELF_MERGE=1).")
    if status == "checks_failed":
        return ("NOT DELIVERED — a Required Check FAILED. Diagnose "
                "(gh run view --log-failed <run>), FIX, re-push, then re-run delivery.")
    if status == "closed":
        return "NOT DELIVERED — PR was CLOSED unmerged."
    if status in ("refused", "host_error"):
        return "NOT DELIVERED — " + (result.get("reason") or "delivery refused")
    return "NOT DELIVERED — still PENDING. Re-run to keep waiting; do NOT claim 'done'."


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Deliver an iterate PR (arm it, or merge it here when the host cannot)")
    p.add_argument("--pr", required=True, help="PR number or URL")
    p.add_argument("--repo", required=True, help="owner/name")
    p.add_argument("--project-root", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--head-branch", required=True,
                   help="this run's branch, e.g. iterate/<slug>")
    p.add_argument("--base-branch", required=True)
    p.add_argument("--timeout-seconds", type=float, default=1800.0)
    p.add_argument("--poll-seconds", type=float, default=30.0)
    p.add_argument("--verified-commit", default="",
                   help="the commit F11's verifier ran on; the merge refuses any head "
                        "that is not this commit or one re-verified here")
    p.add_argument("--no-arm", action="store_true",
                   help="skip the arm (already armed, or deferred to an orchestrator)")
    args = p.parse_args(argv)
    project_root = Path(args.project_root).resolve()
    result = deliver(
        args.pr, project_root=project_root, run_id=args.run_id,
        head_branch=args.head_branch, base_branch=args.base_branch, repo=args.repo,
        timeout_seconds=args.timeout_seconds, poll_seconds=args.poll_seconds,
        arm=not args.no_arm, verified_commit=args.verified_commit, record_timing=True,
    )
    if result.get("exit_code") == EXIT_DELIVERED:
        result["merge_compliance_audit"] = run_merge_compliance_audit(
            _SCRIPTS_ROOT, project_root, args.run_id, args.pr, args.repo)

    print(json.dumps(result, indent=2))
    print(summary(result), file=sys.stderr)
    exit_code = int(result["exit_code"])
    if exit_code in (EXIT_DELIVERED, EXIT_CLOSED):
        retire_run_pointer_best_effort(project_root, args.run_id)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
