#!/usr/bin/env python3
"""PR-scoped GitHub (`gh`) client for the triage importer's loop-closing source.

Sibling to ``github_api`` — split out (rather than grown into it) because
``github_api.py`` is already at its grandfathered LOC ceiling; adding here keeps
each gh-client file cohesive and avoids ratcheting the bloat baseline. Reuses
``github_api._gh_api`` so every fetch shares the SAME bounded-timeout,
None-on-failure contract the auto-resolve pass depends on (a failed fetch is
``None``; a successful empty fetch is ``[]``).

These functions back the ``gh-pr-ci:{pr_number}`` action-unit
(iterate-2026-06-11-automerge-gh-pr-ci-producer, B4.5 loop-closing): failed
hard-gates on an OPEN PR must surface in triage, else an armed auto-merge sits
silently waiting.

Call-volume note: the import is throttled (default 6h) — the per-open-PR
check-runs fan-out (one `gh api` call per open PR) runs at most a few times a day
and stays well under GitHub's rate limit for any triage-managed repo. No cap is
applied: capping the PR set would reintroduce the incomplete-set false-resolve
risk the symmetry + truncation guards exist to prevent.
"""

from __future__ import annotations

from urllib.parse import quote

import github_api

# Check-run conclusions that mark a PR as carrying a failing hard-gate. Superset
# of the default-branch CI set (mappers._FAILED_CONCLUSIONS) — on a PR, GitHub's
# required-check gating also blocks auto-merge on ``cancelled`` /
# ``action_required``, so those are non-passing terminal states an operator must
# act on. In-progress / queued / success / neutral / skipped never count.
_FAILED_CONCLUSIONS = frozenset(
    {"failure", "timed_out", "startup_failure", "cancelled", "action_required"}
)

# Per-check-name display cap in the (frozen) launch payload — check names are
# user-defined strings, so they are sanitised + bounded before rendering.
_MAX_NAME_LEN = 80


def _sanitize_name(name: object) -> str:
    """Render a check-run name safe + bounded for the launch payload.

    Non-printable characters (newlines, tabs, control codes) collapse to spaces
    so a maliciously- or accidentally-named check can't break the payload's
    structure or smuggle control sequences into operator output. Empty / non-str
    names fall back to ``"unnamed"``.
    """
    if not isinstance(name, str):
        return "unnamed"
    cleaned = "".join(ch if ch.isprintable() else " " for ch in name)
    cleaned = " ".join(cleaned.split())[:_MAX_NAME_LEN].strip()
    return cleaned or "unnamed"


def _failing_check_names(check_runs: list[dict] | None) -> list[str]:
    """Sorted, de-duplicated, sanitised names of the COMPLETED failing checks.

    Pure. Only ``status == "completed"`` runs with a failing ``conclusion``
    count — a pending / queued check is not a failure. Sorting + dedup make the
    derived payload deterministic regardless of API ordering.
    """
    names: set[str] = set()
    for run in check_runs or []:
        if not isinstance(run, dict) or run.get("status") != "completed":
            continue
        conclusion = run.get("conclusion")
        if isinstance(conclusion, str) and conclusion.lower() in _FAILED_CONCLUSIONS:
            names.add(_sanitize_name(run.get("name")))
    return sorted(names)


def fetch_open_prs() -> list[dict] | None:
    """Open PRs for the current repo (``None`` on failure, ``[]`` when none).

    Paginated (arrays merge cleanly under ``gh --paginate``) so the open set is
    COMPLETE — the differentiated auto-resolve relies on a complete open set to
    distinguish "PR still open" from "PR gone".
    """
    data = github_api._gh_api(
        "repos/{owner}/{repo}/pulls?state=open&per_page=100", paginate=True
    )
    return data if isinstance(data, list) else None


def fetch_pr_check_runs(head_sha: str) -> list[dict] | None:
    """Check runs for ``head_sha`` (``None`` on failure / truncation).

    ``filter=latest`` so a superseded failed run that was re-run green never
    counts. The response is the object form ``{total_count, check_runs}`` (like
    ``fetch_workflow_runs``); when ``total_count`` exceeds the page we got, the
    view is partial — return ``None`` so the symmetry rule skips this run rather
    than misread an unseen failing check on page 2 as "all green".
    """
    sha = quote(str(head_sha), safe="")
    data = github_api._gh_api(
        f"repos/{{owner}}/{{repo}}/commits/{sha}/check-runs"
        f"?per_page=100&filter=latest"
    )
    if not isinstance(data, dict):
        return None
    runs = data.get("check_runs")
    if not isinstance(runs, list):
        return None
    total = data.get("total_count")
    if isinstance(total, int) and len(runs) < total:
        return None
    return runs


def fetch_pr_state(pr_number: int) -> dict | None:
    """``{"state", "merged"}`` for one PR, or ``None`` on failure.

    Resolve-only: distinguishes ``prMerged`` from ``prClosed`` for a PR that has
    left the open set. ``None`` (unfetchable) keeps the item open one more cycle
    rather than guessing — see ``github_triage.resolve.resolve_pr_ci``.
    """
    data = github_api._gh_api(f"repos/{{owner}}/{{repo}}/pulls/{int(pr_number)}")
    if not isinstance(data, dict):
        return None
    return {"state": data.get("state"), "merged": bool(data.get("merged"))}


def open_prs_with_failed_checks(prs: list[dict] | None) -> list[dict] | None:
    """Reduce open PRs to the (non-draft) ones carrying ≥1 failing hard-gate.

    Each kept PR is enriched with ``{number, html_url, title, head_branch,
    failing_checks}``. Draft PRs are excluded — a draft can't be auto-merge-armed,
    so its red CI is expected WIP, not a silently-stuck armed PR.

    Symmetry (the MED-#1 lesson): returns ``None`` if ``prs is None`` OR ANY
    per-PR check-runs fetch returns ``None`` — a network blip must never let the
    consumer mass-resolve. ``[]`` is a valid "no failing PRs".
    """
    if prs is None:
        return None
    out: list[dict] = []
    for pr in prs:
        if not isinstance(pr, dict) or pr.get("draft"):
            continue
        head = pr.get("head") or {}
        head_sha = head.get("sha")
        if not head_sha:
            continue
        runs = fetch_pr_check_runs(head_sha)
        if runs is None:
            return None
        names = _failing_check_names(runs)
        if names:
            out.append({
                "number": pr.get("number"),
                "html_url": pr.get("html_url"),
                "title": pr.get("title"),
                "head_branch": head.get("ref"),
                "failing_checks": names,
            })
    return out
