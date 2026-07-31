"""Rung 3 of the delivery ladder: merge it here, because the host cannot
(iterate-2026-07-31-f11-delivery-truth).

Reached only when arming auto-merge is **structurally impossible** — the repository's
auto-merge setting is off, or the base branch has no protection — and self-merge is
permitted. The cycle is: wait for green → refresh if behind or conflicted → re-verify →
merge pinned to the verified commit → confirm ``MERGED``.

**Stricter than ``--auto``, not looser.** ``ensure_current`` exists because the host's
server-side merge cannot run the regenerate-at-merge resolver, so a branch that fell
behind merges stale (Group-E). Arming narrows that window but cannot close it:
``--auto`` merges the moment checks pass, however far the branch has drifted by then.
Here the moment of merging is ours, so the refresh happens immediately before it.

Three invariants this cycle exists to keep, each of which costs a round trip:

* **What merges is what was verified.** F11 runs the finalization verifier *before* the
  watch, so a refresh *during* the wait produces a commit no verifier ever saw. It is
  re-verified, red **STOPS** delivery, and the merge is issued with
  ``--match-head-commit`` so the *host* enforces the pin rather than this loop. The pin
  alone was not enough: it pins whatever the PR head *is*, so a commit pushed by anyone
  else during the wait would have been pinned and merged just as cheerfully. The head is
  therefore also compared with the local HEAD this run verified (Stage 2).
* **Checks do not vanish.** The names seen on earlier polls must report again on the new
  head — a count would be satisfied by three checks reporting where the base had
  meanwhile grown two more.
* **A finished PR is reported, not refused.** Someone else — a human, the campaign
  orchestrator — can merge it in the seconds the refresh takes.

The wall-clock budget is spent ONCE across all attempts, not per attempt: three
attempts × ``timeout_seconds`` would silently make F11's ``--timeout-seconds 1800`` a
5400-second block (Stage 2).

Split out of ``tools/deliver_pr.py`` when that file crossed the 300-line limit; the
seam is real — the driver decides *which rung*, this decides *how to finish*.
"""

from __future__ import annotations

import time
from pathlib import Path

from .pr_delivery import (
    EXIT_DELIVERED,
    EXIT_HOST_ERROR,
    EXIT_PENDING,
    EXIT_REFUSED,
    STATUS_EXITS,
    delivery_result,
    terminal_state_result,
    wrong_pr,
)
from .pr_readiness import REFRESHABLE_MERGE_STATES
from .pr_delivery_host import HOST_ERRORS

#: How many times the wait→refresh→merge cycle may restart before giving up. A head
#: moving once or twice is ordinary on a busy trunk; three times means something else is
#: pushing to this branch, and looping forever would hide that.
MAX_ATTEMPTS = 3


def self_merge(
    pr_url: str,
    *,
    project_root: Path,
    run_id: str,
    head_branch: str,
    base_branch: str,
    repo: str,
    steps: list[str],
    timeout_seconds: float,
    poll_seconds: float,
    watch,
    host,
    verified_commit: str = "",
    now=time.monotonic,
) -> dict:
    """Carry the PR to MERGED, or return the reason it was not. Never raises.

    ``verified_commit`` is the commit F11's verifier actually ran on. Keying
    re-verification on "did I push inside this process" was a hole in both directions
    (Stage 3): a re-run after a RED re-verification found the branch already current,
    never re-verified, and merged the very commit the previous invocation had refused;
    and any commit pushed by anything else sharing the worktree satisfied the stand-in
    check. What must be verified is a property of the COMMIT, not of who pushed it.
    """
    seen_names: set[str] = set()
    passed_count = 0
    verified: set[str] = {verified_commit} if verified_commit else set()
    deadline = now() + timeout_seconds
    for attempt in range(MAX_ATTEMPTS):
        remaining = deadline - now()
        if remaining <= 0:
            steps.append(f"wait[{attempt}]: the delivery budget is spent")
            return delivery_result("pending", EXIT_PENDING, steps,
                                   checks_observed=len(seen_names),
                                   reason="the delivery timeout elapsed; re-run to keep waiting")
        try:
            verdict = watch(pr_url, repo=repo, timeout_seconds=remaining,
                            poll_seconds=poll_seconds, ready_is_terminal=True,
                            seen_names=sorted(seen_names))
        except HOST_ERRORS as exc:
            steps.append(f"wait[{attempt}]: host error")
            return delivery_result("host_error", EXIT_HOST_ERROR, steps,
                                   checks_observed=len(seen_names),
                                   reason=f"the host could not be read while waiting: "
                                          f"{type(exc).__name__}: {exc}")
        status = verdict["status"]
        steps.append(f"wait[{attempt}]: {status}")
        seen_names |= set(verdict.get("seen_names") or ())
        # Passes, not entries: skipped and neutral checks count for the merge DECISION but
        # are not evidence, and the summary promises how many the host actually ran.
        passed_count = max(passed_count, int(verdict.get("checks_passed") or 0))

        if status not in ("ready", "refresh_needed"):
            # Merged by somebody else, red, closed, or timed out. Each already has a
            # verdict and an exit code, and none of them is ours to override.
            result = delivery_result(status, STATUS_EXITS.get(status, EXIT_PENDING),
                                     steps, watch=verdict,
                                     checks_observed=len(seen_names))
            if status == "merged":
                result["merged_by"] = "other"
            return result

        # Refresh AFTER green, never before: refreshing earlier burns a CI run on a head
        # we are about to replace. `refresh_needed` arrives here too — the host telling
        # us the branch is behind or conflicted, which only a refresh clears.
        if now() >= deadline:
            steps.append("the budget was spent before the refresh")
            return delivery_result("pending", EXIT_PENDING, steps,
                                   checks_observed=len(seen_names),
                                   reason="the delivery timeout elapsed; re-run to keep waiting")
        refreshed = host.refresh(project_root, run_id, head_branch,
                                 timeout=max(1.0, deadline - now()))
        if not refreshed.get("ok"):
            steps.append(f"refresh failed: {refreshed.get('error', '')}")
            return delivery_result("refused", EXIT_REFUSED, steps,
                                   checks_observed=len(seen_names),
                                   reason="could not bring the branch up to date: "
                                          f"{refreshed.get('error', '')}")
        if refreshed.get("pushed"):
            new_head = host.head_sha(project_root)
            steps.append(f"refreshed and pushed {new_head[:12]}")
            if not host.verify(project_root, run_id, new_head,
                               timeout=max(1.0, deadline - now())):
                return delivery_result("refused", EXIT_REFUSED, steps,
                                       checks_observed=len(seen_names),
                                       reason="the refresh commit failed re-verification — "
                                              "refusing to merge a commit the verifier rejected")
            verified.add(new_head)
            steps.append("re-verified the refresh commit")
            continue  # back to waiting: the NEW head's checks must report

        if status == "refresh_needed":
            # The host says behind/conflicted but there was nothing to integrate, so its
            # view is stale. Poll again rather than merging against a state we cannot
            # explain; the attempt bound turns a persistent disagreement into an honest
            # pending.
            steps.append("host reports behind, but the branch is already current — re-polling")
            continue

        # --- the pinned merge -------------------------------------------------
        pinned = verdict.get("head_oid") or ""
        if not pinned:
            steps.append("no head commit observed — refusing an unpinned merge")
            return delivery_result("refused", EXIT_REFUSED, steps,
                                   checks_observed=len(seen_names),
                                   reason="the head commit could not be read, so the merge "
                                          "could not be pinned to a verified commit")
        if pinned not in verified:
            # The PR head carries no verification. Either something else pushed to this
            # branch, or a PREVIOUS invocation pushed a refresh whose re-verification came
            # back red — in which case the branch is sitting on a rejected commit and
            # merging it would deliver work the gate refused. Verify it now, or refuse.
            steps.append(f"PR head {pinned[:12]} carries no verification from this run")
            if now() >= deadline:
                return delivery_result("pending", EXIT_PENDING, steps,
                                       checks_observed=len(seen_names),
                                       reason="the delivery timeout elapsed before the PR head "
                                              "could be verified; re-run to keep waiting")
            local = host.head_sha(project_root)
            if not local or local != pinned:
                # We do not have that commit checked out, so we cannot verify it. An
                # UNREADABLE local HEAD refuses too: `if local and ...` used to skip the
                # comparison entirely and merge whatever the PR head was (Stage 3).
                return delivery_result("refused", EXIT_REFUSED, steps,
                                       checks_observed=len(seen_names),
                                       reason=f"the PR head ({pinned[:12]}) is not the commit "
                                              f"this run has checked out "
                                              f"({local[:12] or 'unreadable'}) — refusing to "
                                              "merge work no verifier here has seen")
            if not host.verify(project_root, run_id, pinned,
                               timeout=max(1.0, deadline - now())):
                return delivery_result("refused", EXIT_REFUSED, steps,
                                       checks_observed=len(seen_names),
                                       reason="the PR head failed verification — refusing to "
                                              "merge a commit the verifier rejected")
            verified.add(pinned)
            steps.append(f"verified the PR head {pinned[:12]}")
        fresh = host.call_json(["pr", "view", pr_url, "--json",
                                "state,headRefName,baseRefName,headRefOid,url,"
                                "mergeStateStatus"],
                               cwd=project_root)
        if fresh is None:
            steps.append("could not re-read the PR before merging")
            return delivery_result("host_error", EXIT_HOST_ERROR, steps,
                                   checks_observed=len(seen_names),
                                   reason="the PR could not be re-read immediately before merging")
        finished = terminal_state_result(str(fresh.get("state") or ""), steps)
        if finished is not None:
            # It landed while we were refreshing. That is delivery, not a refusal.
            finished["checks_observed"] = len(seen_names)
            return finished
        problem = wrong_pr(fresh, expected_head=head_branch,
                           expected_base=base_branch, expected_repo=repo)
        if problem:
            steps.append(f"identity refused: {problem}")
            return delivery_result("refused", EXIT_REFUSED, steps,
                                   checks_observed=len(seen_names),
                                   reason=f"refusing to merge: {problem}")
        if (fresh.get("headRefOid") or "") != pinned:
            steps.append("head moved between readiness and merge — restarting the wait")
            continue
        # Up-to-dateness at the MOMENT of merging, not merely at the last poll. On an
        # unprotected base nothing forces it, so a branch that fell behind seconds ago
        # would be squashed by a server-side 3-way merge of the regenerated churn
        # snapshots — the Group-E staleness this refresh exists to prevent (Stage 3).
        if (fresh.get("mergeStateStatus") or "").upper() in REFRESHABLE_MERGE_STATES:
            steps.append("the base moved between readiness and merge — refreshing again")
            continue

        # NO `--delete-branch`: on a non-`--auto` merge gh deletes the LOCAL branch too,
        # which means checking out the default branch inside this worktree. That fails when
        # the main clone holds that branch, and succeeds DESTRUCTIVELY when it does not,
        # leaving the iterate's own worktree off its branch mid-F11 (Stage 3). The remote
        # ref is deleted separately, after delivery is confirmed, best-effort.
        merge = host.call(["pr", "merge", pr_url, "--squash",
                           "--match-head-commit", pinned], cwd=project_root)

        # The STATE is the evidence, in BOTH directions. A non-zero exit used to return
        # immediately, so any failure after the merge API call had already succeeded — a
        # dropped connection reading the response, a branch delete erroring — reported NOT
        # DELIVERED for a change that was on the default branch, and told the operator not
        # to retry (Stage 3).
        after = host.call_json(["pr", "view", pr_url, "--json", "state"], cwd=project_root)
        landed = terminal_state_result(str((after or {}).get("state") or ""), steps)
        if landed is None or landed["status"] != "merged":
            if merge.returncode != 0:
                steps.append("merge refused by the host")
                return delivery_result("refused", EXIT_REFUSED, steps,
                                       checks_observed=len(seen_names),
                                       reason="the host refused the merge: "
                                              f"{(merge.stderr or merge.stdout or '').strip()[:300]}")
            steps.append("merge command succeeded but the PR does not read as MERGED")
            return delivery_result("refused", EXIT_REFUSED, steps,
                                   checks_observed=len(seen_names),
                                   reason="the merge command exited zero but the PR does not "
                                          "read as MERGED — not claiming delivery on an exit code")
        if merge.returncode != 0:
            steps.append("the merge landed even though the command reported a failure")
        # Best-effort, remote-only. Never fatal: the change IS delivered.
        host.call(["api", "-X", "DELETE",
                   f"repos/{repo}/git/refs/heads/{head_branch}"], cwd=project_root)
        steps.append("merged here, pinned to the verified commit")
        result = delivery_result("merged", EXIT_DELIVERED, steps,
                                 checks_observed=len(seen_names),
                                 checks_passed=passed_count)
        result["merged_by"] = "shipwright"
        return result

    steps.append(f"gave up after {MAX_ATTEMPTS} refresh/merge attempts")
    return delivery_result("pending", EXIT_PENDING, steps,
                           checks_observed=len(seen_names),
                           reason="the head kept moving; re-run the delivery to keep trying")


__all__ = ["MAX_ATTEMPTS", "self_merge"]
