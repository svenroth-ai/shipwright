"""The workflow-lifecycle client: `github_workflow_api.fetch_workflow_state`.

Covers iterate-2026-08-01-ci-card-deleted-workflow AC2 and AC11. The reducer
that consumes this client is tested in
`test_github_triage_workflow_state.py`; the end-to-end import path in
`test_github_triage_workflow_state_import.py`.

`None` from this client means "state could not be established", never
"deleted" — every caller must read it as keep-the-finding, so the bad-payload
cases below are the ones that keep the fix from becoming a suppressor.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import github_api  # noqa: E402
import github_workflow_api  # noqa: E402

WORKFLOW_ID = 322548704  # the deleted workflow behind trg-9b1a1286

# Bound at import, BEFORE conftest's autouse `_isolate_live_gh_clients` can
# replace the module attribute. That stub keeps unrelated consumer suites from
# spawning a live `gh api` lookup; this suite is the one that tests the real
# client, so it holds its own reference. Hermeticity here comes from patching
# `github_api._gh_api` — the transport — rather than faking the subject.
_real_fetch_workflow_state = github_workflow_api.fetch_workflow_state


def test_fetch_workflow_state_reads_the_per_id_endpoint(monkeypatch):
    """AC2 — the state is READ from `actions/workflows/{id}`, never inferred
    from a listing.

    The `paginate` assertion pins a failure mode no other test can see:
    `actions/workflows` is object-shaped, and `gh api --paginate` on an object
    endpoint emits CONCATENATED JSON objects, so `_gh_api`'s `json.loads`
    raises and returns None. A paginated fetch here would silently disable the
    whole filter while every mocked test stayed green.
    """
    seen = {}

    def fake_gh_api(path, **kwargs):
        seen["path"] = path
        seen["kwargs"] = kwargs
        return {"id": WORKFLOW_ID, "state": "deleted"}

    monkeypatch.setattr(github_api, "_gh_api", fake_gh_api)
    assert _real_fetch_workflow_state(WORKFLOW_ID) == "deleted"
    assert seen["path"] == (
        f"repos/{{owner}}/{{repo}}/actions/workflows/{WORKFLOW_ID}"
    )
    assert not seen["kwargs"].get("paginate"), (
        "must not paginate an object-shaped endpoint"
    )


@pytest.mark.parametrize(
    "payload",
    [
        None,           # _gh_api failure (network, non-zero exit, 404)
        [],             # wrong shape
        "deleted",      # not a mapping
        {},             # no state key
        {"state": ""},  # empty state
        {"state": 7},   # non-string state
    ],
)
def test_fetch_workflow_state_returns_none_on_bad_payload(monkeypatch, payload):
    """AC11 — anything that is not a mapping carrying a non-empty string
    `state` yields None, which the reducer reads as 'keep the run'."""
    monkeypatch.setattr(github_api, "_gh_api", lambda path, **kw: payload)
    assert _real_fetch_workflow_state(WORKFLOW_ID) is None


@pytest.mark.parametrize("bad_id", ["12; rm -rf /", None, 3.5, "abc", True])
def test_fetch_workflow_state_rejects_non_integer_id(monkeypatch, bad_id):
    """AC11 — a non-integer id never reaches endpoint construction.

    `_gh_api` is already non-shell (argv list, no shell=True), so this is input
    hygiene rather than an injection fix. `True` is included because bool is an
    int subclass and must not be accepted as a workflow id.
    """
    called = []
    monkeypatch.setattr(
        github_api, "_gh_api", lambda path, **kw: called.append(path)
    )
    assert _real_fetch_workflow_state(bad_id) is None
    assert called == []


def test_unresolvable_state_is_reported_to_stderr(monkeypatch, capsys):
    """A premise-drift guard (Stage-3 doubt 1). `None` is read as "keep", which
    is correct but indistinguishable from "the workflow is alive" — so if GitHub
    ever stopped answering 200/`deleted`, the filter would become a permanent
    no-op with no signal anywhere. The id always comes from a run in this same
    repo, so failing to resolve it is anomalous, never routine.
    """
    monkeypatch.setattr(github_api, "_gh_api", lambda path, **kw: None)
    assert _real_fetch_workflow_state(WORKFLOW_ID) is None
    assert str(WORKFLOW_ID) in capsys.readouterr().err


def test_transport_exception_is_contained(monkeypatch, capsys):
    """The documented contract is "None whenever the state cannot be
    established" — including a transport that RAISES. Contained in the helper
    rather than only at the call site, because a direct caller does not inherit
    the reducer's own guard (external code review, openai medium).
    """
    def boom(path, **kwargs):
        raise RuntimeError("socket exploded")

    monkeypatch.setattr(github_api, "_gh_api", boom)
    assert _real_fetch_workflow_state(WORKFLOW_ID) is None
    err = capsys.readouterr().err
    assert "RuntimeError" in err and str(WORKFLOW_ID) in err


def test_resolved_state_is_silent(monkeypatch, capsys):
    """The diagnostic above must not fire on the normal path, or it becomes
    noise every operator learns to ignore."""
    monkeypatch.setattr(
        github_api, "_gh_api", lambda path, **kw: {"state": "active"}
    )
    assert _real_fetch_workflow_state(WORKFLOW_ID) == "active"
    assert capsys.readouterr().err == ""
