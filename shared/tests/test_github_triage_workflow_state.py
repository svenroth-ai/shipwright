"""The CI reducer files cards only for workflows the repo still has.

Covers iterate-2026-08-01-ci-card-deleted-workflow AC1 and AC3-AC6, AC9 — the
reducer `latest_failed_ci_runs`. The client it calls is tested in
`test_github_workflow_api.py`; the end-to-end import path in
`test_github_triage_workflow_state_import.py`.

The bug: a workflow whose file no longer exists on the default branch keeps its
run history, so `latest_failed_ci_runs` — which consulted `conclusion` alone —
minted a high-severity `gh-ci:{workflow_id}` card nobody could ever fix
(trg-9b1a1286, workflow 322548704). The run fixtures below are the REAL
payloads behind that incident, verbatim from
`gh api repos/svenroth-ai/shipwright/actions/runs/30404435116`.

The dangerous direction here is OVER-filtering: dropping a live workflow's run
hides real CI breakage. Every "unknown" path below therefore asserts KEPT.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from github_triage.mappers import latest_failed_ci_runs  # noqa: E402

DELETED_WORKFLOW_ID = 322548704   # .github/workflows/probe-token-bypass.yml
LIVE_WORKFLOW_ID = 259825683      # .github/workflows/codeql.yml

DELETED_RUN = {
    "id": 30404435116,
    "workflow_id": DELETED_WORKFLOW_ID,
    "name": "Probe refresh-token bypass",
    "head_branch": "main",
    "head_sha": "2a5b7d35e4c0134c7f46db23129584a3cf8a3f95",
    "status": "completed",
    "conclusion": "failure",
    "html_url": "https://github.com/svenroth-ai/shipwright/actions/runs/30404435116",
}

LIVE_RUN = {
    "id": 30692857884,
    "workflow_id": LIVE_WORKFLOW_ID,
    "name": "CodeQL",
    "head_branch": "main",
    "head_sha": "62c92866770e7dc33e27f9c5ebd5948665f6f780",
    "status": "completed",
    "conclusion": "failure",
    "html_url": "https://github.com/svenroth-ai/shipwright/actions/runs/30692857884",
}


def _deleted_only(workflow_id):
    """State fetcher: the incident's workflow is deleted, everything else lives."""
    return "deleted" if workflow_id == DELETED_WORKFLOW_ID else "active"


def _ids(runs):
    return [r["workflow_id"] for r in runs]


# ---------------------------------------------------------------------------
# AC1 / AC3 — the reducer drops deleted workflows, and only those
# ---------------------------------------------------------------------------

def test_drops_run_for_deleted_workflow():
    """AC1 — the reported incident: a deleted workflow mints no card, while
    the live workflow in the same batch is untouched."""
    kept = latest_failed_ci_runs(
        [DELETED_RUN, LIVE_RUN], workflow_state_fetcher=_deleted_only
    )
    assert _ids(kept) == [LIVE_WORKFLOW_ID]


def test_keeps_run_for_active_workflow():
    """AC3 — an active workflow's failure is real work and still cards."""
    kept = latest_failed_ci_runs(
        [LIVE_RUN], workflow_state_fetcher=lambda wid: "active"
    )
    assert _ids(kept) == [LIVE_WORKFLOW_ID]


@pytest.mark.parametrize(
    "state", ["disabled_manually", "disabled_inactivity", "disabled_fork"]
)
def test_keeps_run_for_disabled_workflow(state):
    """AC3 — a disabled workflow's FILE still exists; an operator can re-enable
    and fix it. Only `deleted` is unfixable, so filtering these would suppress
    actionable failures."""
    kept = latest_failed_ci_runs(
        [LIVE_RUN], workflow_state_fetcher=lambda wid: state
    )
    assert _ids(kept) == [LIVE_WORKFLOW_ID]


# ---------------------------------------------------------------------------
# AC4 / AC5 / AC6 — every unknown fails OPEN, and does so per workflow
# ---------------------------------------------------------------------------

def test_no_fetcher_keeps_every_failed_run():
    """AC4 + AC6 — the public single-argument contract is unchanged: with no
    fetcher there is no filtering at all."""
    expected = [DELETED_WORKFLOW_ID, LIVE_WORKFLOW_ID]
    assert _ids(latest_failed_ci_runs([DELETED_RUN, LIVE_RUN])) == expected
    assert _ids(
        latest_failed_ci_runs([DELETED_RUN, LIVE_RUN], workflow_state_fetcher=None)
    ) == expected


def test_run_without_workflow_id_is_kept():
    """AC4 — no id means no question can be asked: keep the run, and do not
    call the fetcher at all."""
    calls = []

    def fetcher(workflow_id):
        calls.append(workflow_id)
        return "deleted"

    run = {k: v for k, v in LIVE_RUN.items() if k != "workflow_id"}
    kept = latest_failed_ci_runs([run], workflow_state_fetcher=fetcher)
    assert len(kept) == 1
    assert calls == []


@pytest.mark.parametrize("state", ["DELETED", "Deleted", "dElEtEd"])
def test_gone_state_match_is_case_insensitive(state):
    """Lower-cased before matching, mirroring the sibling `_FAILED_CONCLUSIONS`
    idiom. Pinned because it widens `deleted` beyond an exact literal — in the
    SAFE direction, but deliberately rather than incidentally."""
    kept = latest_failed_ci_runs(
        [DELETED_RUN], workflow_state_fetcher=lambda wid: state
    )
    assert kept == []


@pytest.mark.parametrize("bad_id", [True, False, "322548704", 3.5, None])
def test_reducer_keeps_run_whose_workflow_id_is_not_an_integer(bad_id):
    """AC4 — the REDUCER's own id guard (distinct from the client's). A
    non-integer id cannot be looked up, so the run is kept and the fetcher is
    never called. `True`/`False` matter because bool is an int subclass."""
    calls = []

    def fetcher(workflow_id):
        calls.append(workflow_id)
        return "deleted"

    kept = latest_failed_ci_runs(
        [dict(DELETED_RUN, workflow_id=bad_id)], workflow_state_fetcher=fetcher
    )
    assert len(kept) == 1
    assert calls == []


def test_state_lookups_are_capped_and_the_tail_is_kept():
    """The lookup count is bounded, and going over the cap KEEPS the extra runs.

    Each lookup is a `gh` subprocess ahead of the other four feeds, so an
    unbounded run could exhaust the hook budget and kill the import before any
    finding is written — worst exactly when main is broadly broken. The cap must
    degrade to pre-fix behaviour (keep), never to suppression."""
    runs = [dict(DELETED_RUN, id=i, workflow_id=1000 + i) for i in range(30)]
    calls = []

    def fetcher(workflow_id):
        calls.append(workflow_id)
        return "deleted"

    kept = latest_failed_ci_runs(runs, workflow_state_fetcher=fetcher)
    assert len(calls) == 20
    assert _ids(kept) == [1000 + i for i in range(20, 30)]


def test_unlookupable_runs_do_not_spend_the_lookup_budget():
    """The budget counts LOOKUPS, not runs (external code review, openai low).

    A batch of runs we cannot ask about must not exhaust the cap and leave a
    genuinely deleted workflow unexamined behind them — that would re-open the
    original bug for the very case the cap was never meant to touch.
    """
    # Distinct `name`s so each is its own workflow: with no `workflow_id`,
    # `_workflow_identity` falls back to the name, and identical names would
    # collapse into a single entry before the cap is ever reached.
    runs = [
        dict(DELETED_RUN, id=i, workflow_id=None, name=f"nameless-{i}")
        for i in range(25)
    ]
    runs.append(dict(DELETED_RUN, id=99, workflow_id=DELETED_WORKFLOW_ID))
    kept = latest_failed_ci_runs(runs, workflow_state_fetcher=_deleted_only)
    assert DELETED_WORKFLOW_ID not in _ids(kept), (
        "25 unlookupable runs consumed the budget and hid a deleted workflow"
    )
    assert len(kept) == 25


def test_unknown_state_keeps_run():
    """AC4 — the fetcher could not establish a state (fetch failed / 404 /
    malformed). Keep the run: a fetch fault must never suppress CI failures."""
    kept = latest_failed_ci_runs(
        [DELETED_RUN], workflow_state_fetcher=lambda wid: None
    )
    assert _ids(kept) == [DELETED_WORKFLOW_ID]


def test_raising_fetcher_keeps_run():
    """AC4 — a fetcher that raises must not abort the import, and must not
    drop the run either."""
    def boom(workflow_id):
        raise RuntimeError("network is down")

    kept = latest_failed_ci_runs([DELETED_RUN], workflow_state_fetcher=boom)
    assert _ids(kept) == [DELETED_WORKFLOW_ID]


def test_one_failed_lookup_does_not_disable_other_filtering():
    """AC5 — fail-open is per workflow, never global: one broken lookup must
    not stop a genuinely deleted sibling from being filtered out."""
    other_deleted = dict(DELETED_RUN, id=1, workflow_id=999000111)

    def fetcher(workflow_id):
        if workflow_id == LIVE_WORKFLOW_ID:
            raise RuntimeError("transient")
        return "deleted"

    kept = latest_failed_ci_runs(
        [DELETED_RUN, LIVE_RUN, other_deleted], workflow_state_fetcher=fetcher
    )
    assert _ids(kept) == [LIVE_WORKFLOW_ID]


def test_state_is_fetched_only_for_latest_failed_workflows():
    """AC9 — reduce FIRST, then look up. A lookup per raw run would issue up to
    100 API calls per import; a lookup for a green workflow issues one for
    nothing."""
    runs = [
        dict(LIVE_RUN, id=9002, conclusion="success"),          # green -> no lookup
        dict(DELETED_RUN, id=9001),                             # failed -> lookup
        dict(DELETED_RUN, id=9000, head_sha="older"),           # superseded -> none
        {"id": 8999, "workflow_id": 777, "conclusion": None},   # running -> none
    ]
    calls = []

    def fetcher(workflow_id):
        calls.append(workflow_id)
        return "active"

    latest_failed_ci_runs(runs, workflow_state_fetcher=fetcher)
    assert calls == [DELETED_WORKFLOW_ID], (
        "state must be fetched once, only for the workflow whose LATEST run failed"
    )
