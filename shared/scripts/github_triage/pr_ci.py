"""PR-CI loop-closing source (B4.5 automerge): failed hard-gates on OPEN PRs.

Consumer-side orchestration for the ``gh-pr-ci:{pr_number}`` action-unit, split
out of ``consumer.py`` so that orchestrator stays under its LOC budget. Fetches
open PRs, emits one action-unit per (non-draft) PR carrying ≥1 failing hard-gate,
and runs the differentiated auto-resolve — all gated symmetrically on a fully
successful fetch (``open_prs_with_failed_checks`` not ``None``), so a network
blip yields no emit AND no resolve this run.

iterate-2026-06-11-automerge-gh-pr-ci-producer.
"""

from __future__ import annotations

import sys

import github_pr_api

from .mappers import pr_ci_action_unit
from .resolve import resolve_pr_ci


def import_pr_ci_findings(project_root, owner_repo, *, append_fn) -> dict:
    """Emit + auto-resolve ``gh-pr-ci`` action-units for the current open PRs.

    ``append_fn`` is the consumer's ``_maybe_append`` closure (it owns the
    idempotent triage write + the ``current_keys`` bookkeeping), so this module
    never imports the triage writer directly.

    Returns ``{"appended", "resolved", "emitted"}`` where ``emitted`` is the
    by-source emission count, or ``None`` when the PR-CI fetch failed (symmetry —
    the consumer records ``by_source["gh-pr-ci:"] = None`` and the auto-resolve
    sweep is skipped entirely).
    """
    open_prs = github_pr_api.fetch_open_prs()
    failing = github_pr_api.open_prs_with_failed_checks(open_prs)
    if failing is None:
        return {"appended": 0, "resolved": 0, "emitted": None}

    appended = 0
    for pr_info in failing:
        unit = pr_ci_action_unit(pr_info, owner_repo=owner_repo)
        if unit is not None and append_fn(unit):
            appended += 1

    try:
        resolved = resolve_pr_ci(
            project_root,
            open_pr_numbers={
                p.get("number") for p in (open_prs or []) if isinstance(p, dict)
            },
            failing_pr_numbers={p.get("number") for p in failing},
            pr_state_fetcher=github_pr_api.fetch_pr_state,
        )
    except Exception as exc:  # noqa: BLE001 — fail-soft, never block the import
        sys.stderr.write(
            f"[github-triage] pr-ci resolve sweep failed: "
            f"{type(exc).__name__}: {exc}\n"
        )
        resolved = 0

    return {"appended": appended, "resolved": resolved, "emitted": appended}
