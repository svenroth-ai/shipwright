"""Secrets + CI action-unit mappers.

Sibling to ``producer.py`` (which owns the security mappers). Kept
separate so each producer-side file stays under the 300-LOC budget.
Pure functions — no I/O, no state, no triage-inbox dispatch.

Public surface re-exported from ``github_triage``:

- ``secrets_action_unit``, ``ci_action_unit``, ``latest_failed_ci_runs``,
  ``pr_ci_action_unit``
"""

from __future__ import annotations

from .producer import PREFIX_CI, PREFIX_PR_CI, PREFIX_SECRETS
from .severity import (
    kind_for,
    secret_scanning_url,
    workflow_page_url,
)

# Length cap for the gh-pr-ci detail line (mirror of producer's artifact cap).
_PR_CI_DETAIL_MAX_LEN = 1024

# Workflow-run conclusions that count as a failure worth triaging.
_FAILED_CONCLUSIONS = frozenset({"failure", "startup_failure", "timed_out"})


def secrets_action_unit(
    *,
    secret_scanning: list[dict],
    owner_repo: str | None,
) -> dict | None:
    """Collapse secret-scanning into one action-unit per repo.

    Whitelist-only ``launchPayload`` — no slash command, no alert content,
    no per-alert URLs (review finding #9: hygiene boundary). Secret
    rotation is manual by design.

    Returns ``None`` when no alerts or when ``owner_repo`` is ``None``.
    """
    if owner_repo is None or not secret_scanning:
        return None
    count = len(secret_scanning)
    url = secret_scanning_url(owner_repo)
    title = f"GitHub secret-scanning: {count} active credential(s) to rotate"
    detail = (
        f"Repo {owner_repo} | {count} open secret-scanning alert(s). "
        f"Rotate via the GitHub secret-scanning tab."
    )
    payload = (
        f"# Manual credential rotation\n"
        f"\n"
        f"GitHub secret-scanning has flagged {count} active credential(s) "
        f"in {owner_repo}.\n"
        f"Rotation is manual — do NOT run a Shipwright skill.\n"
        f"\n"
        f"Checklist:\n"
        f"  1. Open the GitHub secret-scanning tab: {url}\n"
        f"  2. For each alert: identify the secret type and rotate it at "
        f"the issuer (cloud provider, OAuth app, package registry, etc.).\n"
        f"  3. Revoke the leaked credential.\n"
        f"  4. Mark the alert resolved on GitHub (revoked / used in tests / "
        f"false positive).\n"
        f"  5. Audit access logs for unauthorized use during the exposure "
        f"window.\n"
        f"\n"
        f"Source: triage item gh-secrets:{owner_repo}"
    )
    return {
        "severity": "critical",
        "kind": kind_for("critical"),
        "title": title[:160],
        "detail": detail,
        "dedup_key": f"{PREFIX_SECRETS}{owner_repo}",
        "launch_payload": payload,
    }


def _workflow_identity(run: dict):
    """Stable workflow identity — the immutable ``workflow_id`` when present,
    else the display ``name``. Used for the dedup key (no sha component in
    the action-unit model)."""
    return run.get("workflow_id") or run.get("name") or "workflow"


def ci_action_unit(run: dict, *, owner_repo: str | None) -> dict | None:
    """One action-unit per failed default-branch workflow.

    Dedup key is ``gh-ci:{workflow_identity}`` — the head_sha is dropped
    (review finding #7) so the persisted ``launchPayload`` stays meaningful
    across reruns of the same workflow. The payload links to the workflow
    PAGE URL (stable), NOT the per-run URL (would be stale by the next
    failure).

    Returns ``None`` when ``owner_repo`` is unresolvable (the workflow-page
    URL is repo-scoped — review finding #4).
    """
    if owner_repo is None:
        return None
    workflow_id = _workflow_identity(run)
    name = run.get("name") or run.get("display_title") or "workflow"
    branch = run.get("head_branch") or "?"
    conclusion = run.get("conclusion") or "failure"
    head_sha = run.get("head_sha") or ""
    page_url = workflow_page_url(owner_repo, workflow_id)
    run_url = run.get("html_url") or ""
    title = f"[ci] {name} failing on {branch}"
    detail = (
        f"Workflow '{name}' last concluded '{conclusion}' on "
        f"{branch}@{head_sha[:7]} | latest run: {run_url}"
    )
    payload = (
        f"/shipwright-iterate --type bug\n"
        f"\n"
        f"Context: GitHub Actions workflow '{name}' is failing on the "
        f"default branch ({branch}) in {owner_repo}.\n"
        f"Last conclusion: {conclusion}.\n"
        f"Live workflow history: {page_url}\n"
        f"Source: triage item gh-ci:{workflow_id}"
    )
    return {
        "severity": "high",
        "kind": kind_for("high"),
        "title": title[:160],
        "detail": detail,
        "dedup_key": f"{PREFIX_CI}{workflow_id}",
        "launch_payload": payload,
    }


def latest_failed_ci_runs(runs: list[dict]) -> list[dict]:
    """Reduce raw workflow runs (newest first) to the latest *concluded* run
    per workflow, keeping only those whose conclusion is a failure.

    In-progress runs (``conclusion is None``) are skipped so a pending run
    never hides a workflow's last real result. Branch scope is set by the
    caller — the producer calls ``fetch_workflow_runs(default_branch())``
    so this helper sees only default-branch runs by construction.
    """
    seen: set = set()
    failed: list[dict] = []
    for run in runs:
        conclusion = run.get("conclusion")
        if conclusion is None:
            continue
        workflow = _workflow_identity(run)
        if workflow in seen:
            continue
        seen.add(workflow)
        if str(conclusion).lower() in _FAILED_CONCLUSIONS:
            failed.append(run)
    return failed


def pr_ci_action_unit(pr_info: dict, *, owner_repo: str | None) -> dict | None:
    """One action-unit per OPEN PR with ≥1 failing hard-gate (B4.5 loop-closing).

    ``pr_info`` is the enriched dict from
    ``github_pr_api.open_prs_with_failed_checks`` —
    ``{number, html_url, title, head_branch, failing_checks}`` (names already
    sanitised + sorted, so the payload is deterministic).

    Dedup key ``gh-pr-ci:{number}`` carries NO head_sha / workflow id: the
    operator action is "fix PR #N", not "fix workflow X on sha Y". Like the
    other action-units the ``launch_payload`` is FROZEN at first append — it is a
    snapshot of the failing checks at first emit; auto-resolve keys off LIVE PR
    state (``resolve.resolve_pr_ci``), never the payload text. ``owner_repo`` is
    optional (the key is PR-number-based); it only backs a fallback PR URL.

    Returns ``None`` when no PR ``number`` is present (can't form a stable key).
    """
    number = pr_info.get("number")
    if number is None:
        return None
    # Sort + dedup defensively here (not just in the producer) so the frozen
    # payload is byte-stable for ANY caller of this public mapper, not only the
    # one that hands pre-sorted names (code-review LOW-1).
    failing = sorted(set(pr_info.get("failing_checks") or []))
    checks_str = ", ".join(failing)
    branch = pr_info.get("head_branch") or "?"
    title = (pr_info.get("title") or "").strip()
    url = pr_info.get("html_url") or (
        f"https://github.com/{owner_repo}/pull/{number}" if owner_repo else ""
    )
    count = len(failing)
    heading = f"[pr-ci] PR #{number} has {count} failing check(s) on {branch}"
    detail = (
        f"PR #{number} \"{title}\" on {branch} | failing checks: "
        f"{checks_str} | {url}"
    )
    if len(detail) > _PR_CI_DETAIL_MAX_LEN:
        detail = detail[: _PR_CI_DETAIL_MAX_LEN - 1] + "…"
    payload = (
        f"/shipwright-iterate --type bug\n"
        f"\n"
        f"Context: open PR #{number} ({url}) has {count} failing required "
        f"check(s) on branch '{branch}': {checks_str}.\n"
        f"This blocks auto-merge — the PR sits armed-but-waiting until fixed.\n"
        f"Source: triage item {PREFIX_PR_CI}{number}"
    )
    return {
        "severity": "high",
        "kind": kind_for("high"),
        "title": heading[:160],
        "detail": detail,
        "dedup_key": f"{PREFIX_PR_CI}{number}",
        "launch_payload": payload,
    }
