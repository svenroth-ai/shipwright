"""Tests for the coded release entry point (FR-01.08 criterion 1) and the
PROD ASK-FIRST guard.

Criterion 1 — a release is refused on failing tests until a person confirms.
Before ``release.py`` this was pure SKILL.md agent prose with no coded
artifact a test could drive; these tests are that artifact. Criterion 5
(auto-rollback on smoke-test failure) lives in ``test_release_rollback.py``.
"""

import json

import release


def _write_test_results(project_root, *, unit_status="passed", e2e_status="passed"):
    (project_root / "shipwright_test_results.json").write_text(
        json.dumps({"unit": {"status": unit_status}, "e2e": {"status": e2e_status}}),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------
# AC02 — refuse a release on failing tests until a person confirms
# --------------------------------------------------------------------------

def test_refuses_before_contacting_the_host_when_no_test_results(client, tmp_path):
    recording = client()

    result = release.release(
        "dev-demo", "https://example.invalid/app.git", "main",
        target="dev", project_root=tmp_path,
    )

    assert result["refused"] is True
    assert result["test_gate"] == "no-results"
    assert recording.calls == []


def test_refuses_before_contacting_the_host_when_tests_failing(client, tmp_path):
    recording = client()
    _write_test_results(tmp_path, unit_status="failed")

    result = release.release(
        "dev-demo", "https://example.invalid/app.git", "main",
        target="dev", project_root=tmp_path,
    )

    assert result["refused"] is True
    assert result["test_gate"] == "failing-unconfirmed"
    assert "confirm" in result["reason"]
    assert recording.calls == []


def test_proceeds_once_a_person_confirms_despite_failing_tests(client, tmp_path):
    recording = client()
    _write_test_results(tmp_path, unit_status="failed")

    result = release.release(
        "dev-demo", "https://example.invalid/app.git", "main",
        target="dev", project_root=tmp_path, confirm_failing_tests=True,
    )

    assert result["refused"] is False
    assert result["released"] is True
    assert result["test_gate"] == "failing-confirmed"
    assert "deploy_from_git" in recording.endpoints


def test_proceeds_normally_when_tests_pass(client, tmp_path):
    recording = client()
    _write_test_results(tmp_path)

    result = release.release(
        "dev-demo", "https://example.invalid/app.git", "main",
        target="dev", project_root=tmp_path,
    )

    assert result["released"] is True
    assert result["test_gate"] == "passed"
    assert "deploy_from_git" in recording.endpoints


def test_a_confirmed_release_proceeds_even_with_no_test_results_at_all(client, tmp_path):
    """The confirmed branch of the no-results state (evaluate_test_gate's
    ``if confirmed: return "no-results", None``) — distinct from the
    unconfirmed refusal, which every other no-results test already covers.
    """
    recording = client()

    result = release.release(
        "dev-demo", "https://example.invalid/app.git", "main",
        target="dev", project_root=tmp_path, confirm_failing_tests=True,
    )

    assert result["refused"] is False
    assert result["released"] is True
    assert result["test_gate"] == "no-results"
    assert "deploy_from_git" in recording.endpoints


def test_refuses_on_a_corrupt_results_file_without_confirmation(client, tmp_path):
    recording = client()
    (tmp_path / "shipwright_test_results.json").write_text("{not json", encoding="utf-8")

    result = release.release(
        "dev-demo", "https://example.invalid/app.git", "main",
        target="dev", project_root=tmp_path,
    )

    assert result["refused"] is True
    assert result["test_gate"] == "failing-unconfirmed"
    assert recording.calls == []


def test_a_corrupt_results_file_proceeds_once_confirmed(client, tmp_path):
    recording = client()
    (tmp_path / "shipwright_test_results.json").write_text("{not json", encoding="utf-8")

    result = release.release(
        "dev-demo", "https://example.invalid/app.git", "main",
        target="dev", project_root=tmp_path, confirm_failing_tests=True,
    )

    assert result["released"] is True
    assert result["test_gate"] == "failing-confirmed"
    assert "deploy_from_git" in recording.endpoints


def test_refuses_when_the_results_file_root_is_not_an_object(client, tmp_path):
    recording = client()
    (tmp_path / "shipwright_test_results.json").write_text("[1, 2, 3]", encoding="utf-8")

    result = release.release(
        "dev-demo", "https://example.invalid/app.git", "main",
        target="dev", project_root=tmp_path,
    )

    assert result["refused"] is True
    assert result["test_gate"] == "failing-unconfirmed"
    assert recording.calls == []


def test_proceeds_when_results_are_nested_under_iterate_latest(client, tmp_path):
    """/shipwright-iterate's F5 step nests unit/e2e under ``iterate_latest``
    instead of writing them at the top level — the gate must recognise both
    shapes or it silently never fires in an iterate-run repo.
    """
    recording = client()
    (tmp_path / "shipwright_test_results.json").write_text(
        json.dumps({"iterate_latest": {"unit": {"status": "passed"}, "e2e": {"status": "passed"}}}),
        encoding="utf-8",
    )

    result = release.release(
        "dev-demo", "https://example.invalid/app.git", "main",
        target="dev", project_root=tmp_path,
    )

    assert result["released"] is True
    assert result["test_gate"] == "passed"
    assert "deploy_from_git" in recording.endpoints


def test_a_deploy_failure_is_reported_not_raised(client, tmp_path):
    """A host failure mid-deploy is a distinct outcome from both a gate
    refusal and a smoke failure — ``failure_stage`` says which happened.
    """
    client(fail_on={"update"})  # RecordingClient.deploy_from_git calls vcs_update
    _write_test_results(tmp_path)

    result = release.release(
        "dev-demo", "https://example.invalid/app.git", "main",
        target="dev", project_root=tmp_path,
    )

    assert result["released"] is False
    assert result["refused"] is False
    assert result["failure_stage"] == "deploy"
    assert "deploy failed" in result["reason"]


# --------------------------------------------------------------------------
# PROD stays ASK-FIRST regardless of invocation path (doubt review finding #3)
# --------------------------------------------------------------------------

def test_an_unrecognised_target_is_refused_before_contacting_the_host(client, tmp_path):
    recording = client()
    _write_test_results(tmp_path)

    result = release.release(
        "dev-demo", "https://example.invalid/app.git", "main",
        target="staging", project_root=tmp_path,
    )

    assert result["refused"] is True
    assert "target" in result["reason"]
    assert recording.calls == []


def test_a_prod_release_is_refused_without_explicit_confirmation(client, tmp_path):
    recording = client()
    _write_test_results(tmp_path)

    result = release.release(
        "prod-demo", "https://example.invalid/app.git", "main",
        target="prod", project_root=tmp_path,
    )

    assert result["refused"] is True
    assert "confirm_prod" in result["reason"]
    assert recording.calls == []


def test_a_prod_release_proceeds_once_confirmed(client, tmp_path):
    recording = client()
    _write_test_results(tmp_path)

    result = release.release(
        "prod-demo", "https://example.invalid/app.git", "main",
        target="prod", project_root=tmp_path, confirm_prod=True,
    )

    assert result["refused"] is False
    assert result["released"] is True
    assert "deploy_from_git" in recording.endpoints
