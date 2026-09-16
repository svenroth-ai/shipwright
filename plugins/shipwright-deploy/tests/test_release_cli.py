"""In-process tests for release.py's argv parsing and exit-code mapping
(``_build_parser`` / ``main``).

Deliberately in-process (``release.main([...])``, not a subprocess) — a
subprocess call is invisible to coverage instrumentation, and the E2E tests
in ``test_release_e2e_cli.py`` already prove the module works as a real
subprocess across a process boundary. These tests exist to exercise the
argv-to-``release()``-call wiring itself.
"""

import json

import release


def _write_test_results(project_root, *, unit_status="passed"):
    (project_root / "shipwright_test_results.json").write_text(
        json.dumps({"unit": {"status": unit_status}, "e2e": {"status": "passed"}}),
        encoding="utf-8",
    )


def test_main_returns_exit_refused_on_a_gate_refusal(client, tmp_path, capsys):
    client()

    code = release.main([
        "--env-name", "dev-demo", "--repo-url", "https://example.invalid/app.git",
        "--branch", "main", "--target", "dev", "--project-root", str(tmp_path),
    ])

    assert code == release.EXIT_REFUSED
    printed = json.loads(capsys.readouterr().out)
    assert printed["refused"] is True


def test_main_returns_exit_released_on_success(client, tmp_path, capsys):
    recording = client()
    _write_test_results(tmp_path)

    code = release.main([
        "--env-name", "dev-demo", "--repo-url", "https://example.invalid/app.git",
        "--branch", "main", "--target", "dev", "--project-root", str(tmp_path),
    ])

    assert code == release.EXIT_RELEASED
    printed = json.loads(capsys.readouterr().out)
    assert printed["released"] is True
    assert "deploy_from_git" in recording.endpoints


def test_main_returns_exit_not_released_on_a_deploy_failure(client, tmp_path, capsys):
    client(fail_on={"update"})
    _write_test_results(tmp_path)

    code = release.main([
        "--env-name", "dev-demo", "--repo-url", "https://example.invalid/app.git",
        "--branch", "main", "--target", "dev", "--project-root", str(tmp_path),
    ])

    assert code == release.EXIT_NOT_RELEASED
    printed = json.loads(capsys.readouterr().out)
    assert printed["failure_stage"] == "deploy"


def test_main_reports_a_profile_load_error_before_any_release_attempt(client, tmp_path, capsys):
    recording = client()
    _write_test_results(tmp_path)
    missing_profile = tmp_path / "does-not-exist.json"

    code = release.main([
        "--env-name", "dev-demo", "--repo-url", "https://example.invalid/app.git",
        "--branch", "main", "--target", "dev", "--project-root", str(tmp_path),
        "--profile", str(missing_profile),
    ])

    assert code == release.EXIT_REFUSED
    printed = json.loads(capsys.readouterr().out)
    assert printed["refused"] is True
    assert recording.calls == []


def test_main_wires_confirm_prod_through_to_a_prod_release(client, tmp_path, capsys):
    recording = client()
    _write_test_results(tmp_path)

    code = release.main([
        "--env-name", "prod-demo", "--repo-url", "https://example.invalid/app.git",
        "--branch", "main", "--target", "prod", "--confirm-prod",
        "--project-root", str(tmp_path),
    ])

    assert code == release.EXIT_RELEASED
    assert "deploy_from_git" in recording.endpoints
