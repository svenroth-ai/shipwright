"""Tests for validate-deploy.py."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "checks" / "validate-deploy.py")


def run_validate(env: dict = None, project_root: Path = None) -> dict:
    """Run validate-deploy.py with optional env overrides.

    ``project_root`` MUST be passed by every caller that cares about
    ``success`` — omitting it defaults the script to ``Path.cwd()``, and
    since the test-gate check added for FR-01.08 #1 reads
    ``<project_root>/shipwright_test_results.json``, a bare invocation would
    pick up whatever ambient file sits at pytest's own cwd (this repo's own
    root file, when run from there) instead of a clean, isolated state.
    """
    import os
    test_env = os.environ.copy()
    if env:
        test_env.update(env)

    args = [sys.executable, SCRIPT]
    if project_root is not None:
        args += ["--project-root", str(project_root)]

    result = subprocess.run(
        args,
        capture_output=True, text=True, encoding="utf-8",
        env=test_env,
    )
    return json.loads(result.stdout)


def test_validate_with_token(monkeypatch, tmp_path):
    # A green shipwright_test_results.json — this test is about the token
    # check, not the test gate, and the test gate now refuses on a missing
    # results file (FR-01.08 #1, Tier-3 PR review round 3).
    (tmp_path / "shipwright_test_results.json").write_text(
        json.dumps({"unit": {"status": "passed"}, "e2e": {"status": "passed"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("JELASTIC_TOKEN", "test-token")
    output = run_validate({"JELASTIC_TOKEN": "test-token"}, project_root=tmp_path)
    assert output["success"] is True
    assert output["jelastic_token"] is True


def test_validate_without_token(monkeypatch, tmp_path):
    monkeypatch.delenv("JELASTIC_TOKEN", raising=False)
    import os
    env = os.environ.copy()
    env.pop("JELASTIC_TOKEN", None)

    result = subprocess.run(
        [sys.executable, SCRIPT, "--project-root", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8",
        env=env,
    )
    output = json.loads(result.stdout)
    assert output["success"] is False
    assert output["jelastic_token"] is False
    # A missing JELASTIC_TOKEN is a hard error (deployment will fail), not a
    # warning — validate-deploy.py appends it to `errors`, and `success` is
    # `len(errors) == 0`. The earlier `output["warnings"]` check contradicted
    # the `success is False` assertion above.
    assert any("JELASTIC_TOKEN" in e for e in output["errors"])


def test_validate_result_structure(monkeypatch, tmp_path):
    monkeypatch.setenv("JELASTIC_TOKEN", "test")
    output = run_validate({"JELASTIC_TOKEN": "test"}, project_root=tmp_path)
    assert "success" in output
    assert "jelastic_token" in output
    assert "supabase_token" in output
    assert "git_remote" in output
    assert "warnings" in output


def _run_with_project_root(project_root: Path, extra_args: list[str] | None = None) -> dict:
    import os
    env = os.environ.copy()
    env["JELASTIC_TOKEN"] = "test-token"
    result = subprocess.run(
        [sys.executable, SCRIPT, "--project-root", str(project_root), *(extra_args or [])],
        capture_output=True, text=True, encoding="utf-8",
        env=env,
    )
    return json.loads(result.stdout)


def test_test_gate_no_results_file_refuses_without_confirmation(tmp_path):
    """Spec FR-01.08 #1: a missing results file needs the same confirmation
    as a known failure — SKILL.md's prior (pre-mechanisation) Step B4 already
    required confirmation for "tests failed OR file does not exist", and
    mechanising criterion 1 must not silently loosen that (Tier-3 PR review,
    e4-checks-deploy-changelog round 3)."""
    output = _run_with_project_root(tmp_path)
    assert output["test_gate"] == "no-results"
    assert output["success"] is False
    assert any("--confirm-failing-tests" in e for e in output["errors"])


def test_test_gate_no_results_file_proceeds_once_a_person_confirms(tmp_path):
    output = _run_with_project_root(tmp_path, ["--confirm-failing-tests"])
    assert output["test_gate"] == "no-results"
    assert output["success"] is True
    assert any("confirmed by a person" in w for w in output["warnings"])


def test_test_gate_refuses_on_failing_tests_without_confirmation(tmp_path):
    (tmp_path / "shipwright_test_results.json").write_text(
        json.dumps({"unit": {"status": "failed"}, "e2e": {"status": "skipped"}}),
        encoding="utf-8",
    )
    output = _run_with_project_root(tmp_path)
    assert output["test_gate"] == "failing-unconfirmed"
    assert output["success"] is False
    assert any("--confirm-failing-tests" in e for e in output["errors"])


def test_test_gate_proceeds_once_a_person_confirms(tmp_path):
    (tmp_path / "shipwright_test_results.json").write_text(
        json.dumps({"unit": {"status": "failed"}, "e2e": {"status": "skipped"}}),
        encoding="utf-8",
    )
    output = _run_with_project_root(tmp_path, ["--confirm-failing-tests"])
    assert output["test_gate"] == "failing-confirmed"
    assert output["success"] is True
    assert any("confirmed by a person" in w for w in output["warnings"])


def test_test_gate_passes_on_green_results(tmp_path):
    (tmp_path / "shipwright_test_results.json").write_text(
        json.dumps({"unit": {"status": "passed"}, "e2e": {"status": "passed"}}),
        encoding="utf-8",
    )
    output = _run_with_project_root(tmp_path)
    assert output["test_gate"] == "passed"
    assert output["success"] is True
    assert output["errors"] == []


def test_test_gate_refuses_on_a_present_but_malformed_results_file(tmp_path):
    """External review (round 1): a results file that EXISTS but fails to
    parse must not be silently treated the same as an absent one — that
    would have been a silent-pass gap inconsistent with the sibling
    ``deploy_checks.check_test_gate_passed`` verifier, which already blocks
    on malformed JSON.
    """
    (tmp_path / "shipwright_test_results.json").write_text("{not valid json", encoding="utf-8")
    output = _run_with_project_root(tmp_path)
    assert output["test_gate"] == "failing-unconfirmed"
    assert output["success"] is False
    assert any("could not be read" in e for e in output["errors"])


def test_test_gate_malformed_results_proceeds_once_confirmed(tmp_path):
    (tmp_path / "shipwright_test_results.json").write_text("{not valid json", encoding="utf-8")
    output = _run_with_project_root(tmp_path, ["--confirm-failing-tests"])
    assert output["test_gate"] == "failing-confirmed"
    assert output["success"] is True


def test_test_gate_does_not_crash_on_a_non_object_json_root(tmp_path):
    """External code review (e4-checks-deploy-changelog): valid JSON that
    isn't an object (a bare list here) used to crash ``.get()`` with
    ``AttributeError`` before this script ever printed a result.
    """
    (tmp_path / "shipwright_test_results.json").write_text("[1, 2, 3]", encoding="utf-8")
    output = _run_with_project_root(tmp_path)
    assert output["test_gate"] == "failing-unconfirmed"
    assert output["success"] is False
    assert any("could not be read" in e for e in output["errors"])


def test_test_gate_reads_the_iterate_latest_nested_shape(tmp_path):
    """Self-review round-trip probe against THIS repo's real
    shipwright_test_results.json (e4-checks-deploy-changelog): the
    /shipwright-iterate F5 step nests unit/e2e under an ``iterate_latest``
    wrapper, a different shape than the full-pipeline /shipwright-test
    phase's top-level keys. Reading only the top level made this gate a
    permanent no-op in every iterate-run repo (unit always read ``None``
    there) — an integration test against the real file caught it.
    """
    (tmp_path / "shipwright_test_results.json").write_text(
        json.dumps({"iterate_latest": {
            "unit": {"status": "passed"}, "e2e": {"status": "not_run"},
        }}),
        encoding="utf-8",
    )
    output = _run_with_project_root(tmp_path)
    assert output["test_gate"] == "passed"
    assert output["success"] is True


def test_test_gate_e2e_not_run_does_not_block_a_passing_unit_layer(tmp_path):
    """E2E is non-blocking, matching the pipeline's own ``_validate_test``
    convention (constitution: E2E can be flaky — an "inform" warning, never
    an "ask" gate). ``not_run`` is the routine case for a backend-only
    change with no startable web surface and must never refuse the deploy.
    """
    (tmp_path / "shipwright_test_results.json").write_text(
        json.dumps({"unit": {"status": "passed"}, "e2e": {"status": "not_run"}}),
        encoding="utf-8",
    )
    output = _run_with_project_root(tmp_path)
    assert output["test_gate"] == "passed"
    assert output["success"] is True


def test_test_gate_e2e_partial_still_blocks(tmp_path):
    """A REPORTED e2e failure (``partial``) still gates — only the routine
    not_run/skipped/absent cases were made non-blocking, not a genuine
    signal that some e2e specs actually failed.
    """
    (tmp_path / "shipwright_test_results.json").write_text(
        json.dumps({"unit": {"status": "passed"}, "e2e": {"status": "partial"}}),
        encoding="utf-8",
    )
    output = _run_with_project_root(tmp_path)
    assert output["test_gate"] == "failing-unconfirmed"
    assert output["success"] is False


def test_test_gate_e2e_failed_status_blocks(tmp_path):
    """Tier-3 PR review round 5: the earlier ``!= "partial"`` blocklist let
    an explicit ``e2e.status == "failed"`` through as non-blocking too — an
    allowlist of the routine statuses is what actually implements "only a
    reported failure blocks"."""
    (tmp_path / "shipwright_test_results.json").write_text(
        json.dumps({"unit": {"status": "passed"}, "e2e": {"status": "failed"}}),
        encoding="utf-8",
    )
    output = _run_with_project_root(tmp_path)
    assert output["test_gate"] == "failing-unconfirmed"
    assert output["success"] is False


def test_test_gate_e2e_unrecognised_status_blocks(tmp_path):
    (tmp_path / "shipwright_test_results.json").write_text(
        json.dumps({"unit": {"status": "passed"}, "e2e": {"status": "error"}}),
        encoding="utf-8",
    )
    output = _run_with_project_root(tmp_path)
    assert output["test_gate"] == "failing-unconfirmed"
    assert output["success"] is False


def test_test_gate_e2e_skipped_status_does_not_block(tmp_path):
    (tmp_path / "shipwright_test_results.json").write_text(
        json.dumps({"unit": {"status": "passed"}, "e2e": {"status": "skipped"}}),
        encoding="utf-8",
    )
    output = _run_with_project_root(tmp_path)
    assert output["test_gate"] == "passed"
    assert output["success"] is True
