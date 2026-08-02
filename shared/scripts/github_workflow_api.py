"""Workflow-lifecycle reads from the GitHub Actions API.

Sibling client to ``github_api`` (whose ``_gh_api`` transport this reuses),
split out for the same reason ``github_pr_api`` was: ``github_api.py`` sits
above its size budget and must not keep growing.

Scope: what the code host says about a *workflow definition*, as opposed to
``github_api.fetch_workflow_runs`` which reports what its *runs* did. The two
are different endpoints, and conflating them is the bug this module exists to
fix — see ``fetch_workflow_state``.

**Call volume — bounded, not overlooked.** The caller asks only for workflows
whose *latest* default-branch run failed: zero on a healthy repo. The reducer
caps those serial lookups at 20; beyond the cap a run is kept, so the limit
degrades safely to the pre-fix behaviour instead of suppressing a finding.
Each attempted call also carries ``github_api._TIMEOUT_SECONDS``.

Public surface:

- ``fetch_workflow_state(workflow_id) -> str | None``
"""

from __future__ import annotations

import sys

import github_api


def fetch_workflow_state(workflow_id: int) -> str | None:
    """Lifecycle state of ONE workflow, or ``None`` when it cannot be established.

    GitHub reports ``active``, ``deleted``, ``disabled_manually``,
    ``disabled_inactivity`` or ``disabled_fork``. A ``deleted`` workflow's file
    is gone from the default branch: its runs survive in history, but nobody
    can fix, re-run, or green it again.

    ``None`` means **unknown**, never "deleted" — `gh` missing, API error, HTTP
    404, or a payload without a usable ``state``. Callers MUST read it as "keep
    the finding" (iterate-2026-08-01-ci-card-deleted-workflow): over-filtering
    silently hides real CI breakage, which is far worse than showing one stale
    card. 404 in particular is NOT treated as deletion — GitHub returns 404 for
    resources a token may not read, so a permission gap would otherwise blank
    the entire CI feed, and a genuinely deleted workflow answers 200 with
    ``{"state": "deleted"}`` anyway (verified against workflow 322548704).

    Read per id rather than filtered out of the ``actions/workflows`` list: that
    list omits deleted workflows, so absence would have to stand in for
    deletion — and it is not established that every ``disabled_*`` workflow
    appears in it, so a disabled (still fixable) workflow could be misread as
    deleted and its real failure dropped. This endpoint states the answer
    instead of implying it.

    Deliberately NOT paginated: it returns a single object, and ``gh --paginate``
    on an object-shaped endpoint emits *concatenated* JSON objects that
    ``_gh_api``'s ``json.loads`` cannot parse — which would make every lookup
    return ``None`` and silently disable the filter.
    """
    # bool is an int subclass; `True` is not a workflow id. Reject anything
    # non-integral before it reaches endpoint construction.
    if isinstance(workflow_id, bool) or not isinstance(workflow_id, int):
        return None
    # Contained here, not just at the call site: this is a public helper whose
    # documented contract is "None whenever the state cannot be established",
    # and a direct caller does not inherit the reducer's own guard.
    try:
        data = github_api._gh_api(
            f"repos/{{owner}}/{{repo}}/actions/workflows/{workflow_id}"
        )
    except Exception as exc:  # noqa: BLE001 — the contract is None, never a raise
        data, detail = None, f"{type(exc).__name__}: {exc}"
    else:
        detail = "no response" if data is None else "unexpected payload shape"
    state = data.get("state") if isinstance(data, dict) else None
    if isinstance(state, str) and state:
        return state
    # Say so. The caller cannot: it reads None as "keep", which is correct but
    # indistinguishable from "the workflow is alive". Without a line here, a
    # drift in the premise this module rests on — that a deleted workflow
    # answers 200 with a state — would turn the whole filter into a permanent
    # no-op with no signal anywhere. The id came from a run in this same repo,
    # so failing to resolve it is always anomalous, never routine. `detail`
    # separates a transport fault from an actually-drifted payload shape, so
    # the line diagnoses rather than merely warns.
    sys.stderr.write(
        f"[github-workflow-api] no state for workflow {workflow_id} "
        f"({detail}); treating as alive (finding kept)\n"
    )
    return None
