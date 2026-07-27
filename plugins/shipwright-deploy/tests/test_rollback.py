"""Tests for the git rollback strategy — does it use the ref it was given?

The old version of this file asserted only that ``--target-ref`` is *required*.
It never asserted that it is *used*, which is exactly how the critical defect
(rollback re-deploys branch HEAD while reporting the requested version) survived
review. Every test here therefore inspects the outbound hosting calls, not just
the returned payload. Clone-strategy and CLI-argument tests live in
``test_rollback_clone.py``.
"""

import urllib.error

import pytest

import rollback


# --------------------------------------------------------------------------
# AC1 / AC2 — the requested version reaches the hosting interface
# --------------------------------------------------------------------------

def test_target_ref_is_sent_to_the_host_before_the_update(client):
    """AC1 — the ref must be pinned, and pinned BEFORE the update is issued.

    Regression pin for the critical defect: the old implementation issued only
    ``update``, so the ref appeared in no request at all.
    """
    recording = client()

    result = rollback.rollback_git("dev-demo", "v1.2.3")

    assert recording.endpoints == ["getprojects", "editproject", "update", "getprojects"]
    assert recording.params_for("editproject")[0]["branch"] == "v1.2.3"
    assert recording.endpoints.index("editproject") < recording.endpoints.index("update")
    assert result["success"] is True


def test_pin_failure_never_issues_the_update_and_never_reports_success(client):
    """AC2 — a failed pin must not fall through to the plain redeploy."""
    recording = client(fail_on={"editproject"})

    result = rollback.rollback_git("dev-demo", "v1.2.3")

    assert "update" not in recording.endpoints
    assert result["success"] is False
    assert "Rolled back" not in result["message"]
    assert result["halt"] is True


def test_report_never_claims_a_rollback_that_did_not_complete(client):
    """AC2 — the ref may be named as *requested*, never as *done*."""
    client(fail_on={"update"})

    result = rollback.rollback_git("dev-demo", "v9.9.9")

    assert result["success"] is False
    assert result["target_ref"] == "v9.9.9"
    assert "Rolled back dev-demo to v9.9.9" not in result["message"]


# --------------------------------------------------------------------------
# AC11 — pinning must not destroy the rest of the project config
# --------------------------------------------------------------------------

def test_pin_sends_the_full_project_object_with_only_the_branch_replaced(client, vcs_project):
    """AC11 — a sparse write could wipe the repo URL / credentials."""
    recording = client()

    rollback.rollback_git("dev-demo", "v1.2.3")

    pinned = recording.params_for("editproject")[0]
    for key, value in vcs_project.items():
        if key == "branch":
            continue
        assert pinned[key] == value, f"{key} was dropped from the editproject payload"
    assert pinned["branch"] == "v1.2.3"


def test_unreadable_project_config_refuses_instead_of_writing(client):
    """AC11 — if the current config cannot be read, do not risk a sparse write."""
    recording = client(fail_on={"getprojects"})

    result = rollback.rollback_git("dev-demo", "v1.2.3")

    assert "editproject" not in recording.endpoints
    assert "update" not in recording.endpoints
    assert result["success"] is False
    assert result["mutated"] is False


# --------------------------------------------------------------------------
# AC3 / AC13 — the verdict never over-claims
# --------------------------------------------------------------------------

def test_readback_confirming_the_ref_reports_confirmed(client):
    client()

    result = rollback.rollback_git("dev-demo", "v1.2.3")

    assert result["ref_verified"] == "confirmed"
    assert result["verification_error"] is None


def test_readback_returning_a_different_ref_is_a_failure(client):
    """AC3 — a mismatch is not a soft warning."""
    recording = client()

    def _stubborn(env_name, project, ref):  # host accepts the write, keeps `main`
        recording.calls.append(("editproject", {"envName": env_name, **project, "branch": ref}))
        return {"result": 0}

    recording.set_vcs_ref = _stubborn

    result = rollback.rollback_git("dev-demo", "v1.2.3")

    assert result["ref_verified"] == "mismatch"
    assert result["success"] is False
    assert result["halt"] is True


def test_unavailable_readback_downgrades_the_claim_and_says_why(client):
    """AC3 — 'unconfirmed' keeps success but must never read as 'confirmed'."""
    recording = client()
    original = recording.get_vcs_project
    state = {"reads": 0}

    def _read_once_then_fail(env_name, context="ROOT"):
        state["reads"] += 1
        if state["reads"] > 1:
            raise rollback.HostingError("getprojects unavailable")
        return original(env_name, context)

    recording.get_vcs_project = _read_once_then_fail

    result = rollback.rollback_git("dev-demo", "v1.2.3")

    assert result["success"] is True
    assert result["ref_verified"] == "unconfirmed"
    assert "getprojects unavailable" in result["verification_error"]
    assert "not confirm" in result["message"]


def test_a_raw_transport_failure_also_downgrades_rather_than_escaping(client, vcs_project):
    """A client that does not wrap URLError must still produce a report."""
    recording = client()
    state = {"reads": 0}

    def _urlerror(env_name, context="ROOT"):
        state["reads"] += 1
        if state["reads"] > 1:
            raise urllib.error.URLError("connection reset")
        return dict(vcs_project)

    recording.get_vcs_project = _urlerror

    result = rollback.rollback_git("dev-demo", "v1.2.3")

    assert result["success"] is True
    assert result["ref_verified"] == "unconfirmed"
    assert "connection reset" in result["verification_error"]


def test_readback_parse_bug_is_not_swallowed_as_unavailable(client, vcs_project):
    """AC3 — only transport/API failures downgrade; a programming error surfaces."""
    recording = client()
    state = {"reads": 0}

    def _boom(env_name, context="ROOT"):
        state["reads"] += 1
        if state["reads"] > 1:
            raise TypeError("parse bug")
        return dict(vcs_project)

    recording.get_vcs_project = _boom

    with pytest.raises(TypeError):
        rollback.rollback_git("dev-demo", "v1.2.3")


def test_refs_heads_prefix_compares_canonically(client):
    """AC13 — `refs/heads/main` and `main` are the same ref."""
    recording = client()

    def _prefixed(env_name, project, ref):
        recording.calls.append(("editproject", {"envName": env_name, **project, "branch": ref}))
        recording._project = {**project, "branch": f"refs/heads/{ref}"}
        return {"result": 0}

    recording.set_vcs_ref = _prefixed

    result = rollback.rollback_git("dev-demo", "release-1")

    assert result["ref_verified"] == "confirmed"
    assert result["success"] is True


# --------------------------------------------------------------------------
# AC12 — a half-done rollback names what it changed
# --------------------------------------------------------------------------

def test_update_failure_reports_the_changed_configuration_and_the_previous_ref(client):
    client(fail_on={"update"})

    result = rollback.rollback_git("dev-demo", "v1.2.3")

    assert result["success"] is False
    assert result["halt"] is True
    assert result["mutated"] is True
    assert result["previous_ref"] == "main"
    assert result["last_attempted"] == "environment/vcs/rest/update"
    assert result["what_it_found"]
    assert "v1.2.3" in result["operator_message"]
    assert "not verif" in result["operator_message"].lower()


# --------------------------------------------------------------------------
# AC13 — ref-form validation happens before anything is touched
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["HEAD; rm -rf /", "-oProxyCommand=x", "a..b", "with space", ""])
def test_invalid_ref_forms_are_rejected_before_any_host_call(client, bad):
    recording = client()

    result = rollback.rollback_git("dev-demo", bad)

    assert recording.calls == []
    assert result["success"] is False
    assert result["mutated"] is False
    assert result["halt"] is False
