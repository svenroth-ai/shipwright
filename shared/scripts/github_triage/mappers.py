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

# Length cap for a detail line built from text the project does not control —
# a workflow name, a branch, the title whoever opened a PR wrote. Mirrors
# producer's `_ARTIFACT_DETAIL_MAX_LEN`. This is a CROWDING guard, not an
# escaping one: terminal control characters are stripped separately, at
# display, on both operator surfaces. Without it one entry can grow without
# limit and push the rest out of a view that shows a capped number of items.
_DETAIL_MAX_LEN = 1024


def _cap_detail(detail: str) -> str:
    """Truncate only what exceeds the cap; a detail of exactly the cap length
    is passed through untouched. The ellipsis marks where the cut happened."""
    if len(detail) <= _DETAIL_MAX_LEN:
        return detail
    return detail[: _DETAIL_MAX_LEN - 1] + "…"

# Workflow-run conclusions that count as a failure worth triaging.
_FAILED_CONCLUSIONS = frozenset({"failure", "startup_failure", "timed_out"})

# Workflow lifecycle states that make a failed run unactionable. A DELETED
# workflow's file is gone from the default branch — its runs remain in history,
# but nobody can fix it, re-run it, or make it green, so a card for it is an
# unfixable P1 (trg-9b1a1286, workflow 322548704).
#
# `disabled_manually` / `disabled_inactivity` / `disabled_fork` are deliberately
# ABSENT: a disabled workflow's file still exists, so an operator can re-enable
# it and fix the failure. Filtering those would suppress real work.
_GONE_WORKFLOW_STATES = frozenset({"deleted"})

# Ceiling on state lookups per import. Each is a serial `gh` subprocess running
# BEFORE the other four feeds, so an unbounded run risks exhausting the hook
# budget and killing the import before ANY finding of ANY class is written —
# exactly when main is broadly red. Past the cap a run is simply KEPT, so this
# degrades to the pre-fix behaviour for the tail: fail-open here too.
_MAX_STATE_LOOKUPS = 20


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
    detail = _cap_detail(
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


def _lookup_id(run: dict) -> int | None:
    """The run's workflow id, or ``None`` when no lookup can be made for it.
    ``bool`` is rejected explicitly: it is an ``int`` subclass, never an id."""
    workflow_id = run.get("workflow_id")
    if isinstance(workflow_id, bool) or not isinstance(workflow_id, int):
        return None
    return workflow_id


def _workflow_is_gone(workflow_id: int, fetcher) -> bool:
    """True only when the code host positively states the workflow is gone.

    Fail-OPEN everywhere else — a fetcher that returns nothing, a fetcher that
    raises. Over-filtering silently hides real CI breakage, so "unknown" must
    always mean "keep". The guard sits per workflow, which is what keeps one
    broken lookup from disabling filtering for the others.

    The raising branch is silent by design: this module is I/O-free, and the
    production fetcher (``github_workflow_api.fetch_workflow_state``) already
    writes its own stderr line whenever it cannot establish a state. Only an
    injected test fake reaches the ``except`` at all.
    """
    try:
        state = fetcher(workflow_id)
    except Exception:  # noqa: BLE001 — a lookup fault must never abort an import
        return False
    return isinstance(state, str) and state.lower() in _GONE_WORKFLOW_STATES


def latest_failed_ci_runs(
    runs: list[dict],
    *,
    workflow_state_fetcher=None,
) -> list[dict]:
    """Reduce raw workflow runs (newest first) to the latest *concluded* run
    per workflow, keeping only those whose conclusion is a failure AND whose
    workflow the repository still has.

    In-progress runs (``conclusion is None``) are skipped so a pending run
    never hides a workflow's last real result. Branch scope is set by the
    caller — the producer calls ``fetch_workflow_runs(default_branch())``
    so this helper sees only default-branch runs by construction.

    ``workflow_state_fetcher`` is an optional ``(workflow_id) -> str | None``
    callable — in production ``github_workflow_api.fetch_workflow_state``. When
    it is ``None`` no state filtering happens at all, which keeps the original
    single-argument contract of this re-exported public helper intact. The
    fetcher is injected rather than imported so this module keeps its "pure
    functions, no I/O" property; the same shape backs
    ``resolve.resolve_pr_ci(..., pr_state_fetcher=...)``.

    The state lookup runs AFTER the reduction, so it costs at most one call per
    workflow whose *latest* run failed — never one per raw run (up to 100 per
    import), and never one for a workflow that is green — and at most
    ``_MAX_STATE_LOOKUPS`` in total.
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
    if workflow_state_fetcher is None:
        return failed
    kept: list[dict] = []
    lookups = 0
    for run in failed:
        workflow_id = _lookup_id(run)
        # The budget counts LOOKUPS, not runs: a run we cannot ask about spends
        # nothing, so a batch of malformed ids can never exhaust the cap and
        # leave a genuinely deleted workflow unexamined behind them.
        if workflow_id is None or lookups >= _MAX_STATE_LOOKUPS:
            kept.append(run)
            continue
        lookups += 1
        if not _workflow_is_gone(workflow_id, workflow_state_fetcher):
            kept.append(run)
    return kept


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
    detail = _cap_detail(
        f"PR #{number} \"{title}\" on {branch} | failing checks: "
        f"{checks_str} | {url}"
    )
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
