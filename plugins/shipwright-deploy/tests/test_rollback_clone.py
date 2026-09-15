"""Clone-strategy rollback + CLI argument validation.

Split out of ``test_rollback.py`` (which owns the git-strategy ref contract) to
keep both files under the repo's 300-line guideline.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import rollback

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "lib" / "rollback.py")


# --------------------------------------------------------------------------
# Tier-3 PR review round 7 — --project-root and --invocation are REQUIRED,
# no default: an omission is a hard argparse error, not a silent guess.
# --------------------------------------------------------------------------

def test_cli_refuses_to_run_without_project_root(tmp_path):
    completed = subprocess.run(
        [sys.executable, SCRIPT, "--env-name", "dev-demo", "--strategy", "clone",
         "--clone-name", "backup", "--invocation", "auto"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert completed.returncode != 0
    assert "--project-root" in completed.stderr


def test_cli_refuses_to_run_without_invocation(tmp_path):
    completed = subprocess.run(
        [sys.executable, SCRIPT, "--env-name", "dev-demo", "--strategy", "clone",
         "--clone-name", "backup", "--project-root", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert completed.returncode != 0
    assert "--invocation" in completed.stderr


# --------------------------------------------------------------------------
# AC10 — stopping is never reported as restoring
# --------------------------------------------------------------------------

@pytest.mark.covers("FR-01.08/AC10")
def test_clone_strategy_reports_stopping_not_restoring(client):
    client()

    result = rollback.rollback_clone("prod-demo", "prod-demo-backup")

    assert result["success"] is True
    assert result["restored"] is False
    assert result["next_steps"]
    assert "stopped" in result["message"].lower()


@pytest.mark.covers("FR-01.08/AC13")
def test_clone_stop_failure_halts_and_names_the_state(client):
    client(fail_on={"stopenv"})

    result = rollback.rollback_clone("prod-demo", "prod-demo-backup")

    assert result["success"] is False
    assert result["halt"] is True
    assert result["mutated"] is True
    assert result["last_attempted"] == "environment/control/rest/stopenv"
    assert result["operator_message"]


# --------------------------------------------------------------------------
# CLI argument validation (behaviour preserved from the original file)
# --------------------------------------------------------------------------

def _run(*args, project_root=None):
    """``--project-root`` and ``--invocation`` are both REQUIRED by the CLI
    (Tier-3 PR review round 7) — this helper supplies a project_root (a
    tmp_path, normally: the CLI's ``rollback_audit.record`` call writes
    ``.shipwright/deploy/rollback-history.jsonl`` relative to it, which
    would otherwise pollute wherever pytest itself was invoked from) and
    defaults ``--invocation`` to ``auto`` for tests that aren't specifically
    exercising that flag.
    """
    full_args = [sys.executable, SCRIPT, *args]
    if project_root is not None:
        full_args += ["--project-root", str(project_root)]
    if "--invocation" not in args:
        full_args += ["--invocation", "auto"]
    completed = subprocess.run(
        full_args,
        capture_output=True, text=True, encoding="utf-8",
    )
    return completed, json.loads(completed.stdout)


def test_git_strategy_requires_target_ref(tmp_path):
    """Git strategy without --target-ref should fail."""
    completed, output = _run("--env-name", "test-env", "--strategy", "git", project_root=tmp_path)
    assert output["success"] is False
    assert "target-ref" in output["error"]
    assert completed.returncode == rollback.EXIT_REFUSED


def test_clone_strategy_requires_clone_name(tmp_path):
    """Clone strategy without --clone-name should fail."""
    completed, output = _run("--env-name", "test-env", "--strategy", "clone", project_root=tmp_path)
    assert output["success"] is False
    assert "clone-name" in output["error"]
    assert completed.returncode == rollback.EXIT_REFUSED


def test_a_refusal_says_the_target_was_not_touched(tmp_path):
    """AC9 — a pre-flight refusal must make no claim about what is running.

    No `client` fixture: this drives the CLI as a subprocess, so an in-process
    stubbed client would be invisible to it either way. The refusal happens at
    argument validation, before any client is constructed.
    """
    completed, output = _run("--env-name", "test-env", "--strategy", "git", project_root=tmp_path)

    assert output["mutated"] is False
    assert output["halt"] is False
    assert "nothing on the hosting target was changed" in output["operator_message"].lower()
    assert completed.returncode != rollback.EXIT_HALT


# --------------------------------------------------------------------------
# main() driven IN-PROCESS (not subprocess) — diff-coverage visibility.
#
# Every other CLI test in this file runs rollback.py as a subprocess, which
# is correct for proving the real entry point works, but coverage.py cannot
# see code that ran in a DIFFERENT process — a subprocess-only test suite
# measures 0% diff-coverage for main() itself, however thoroughly it is
# actually exercised (feedback_subprocess_tests_are_invisible_to_diff_coverage).
# These two calls exercise the same code paths in-process so the CI diff-
# coverage gate can see them.
# --------------------------------------------------------------------------

def test_main_records_a_preflight_profile_refusal_in_process(tmp_path):
    """FR-01.08 criterion 7, exercised through ``main()`` directly: an
    unreadable ``--profile`` still reaches the unified
    ``result`` -> ``rollback_audit.record()`` -> ``exit_code()`` path."""
    import rollback_audit

    missing_profile = tmp_path / "does-not-exist.json"
    exit_status = rollback.main([
        "--env-name", "dev-demo", "--strategy", "git", "--target-ref", "v1",
        "--project-root", str(tmp_path), "--profile", str(missing_profile),
        "--invocation", "auto",
    ])

    assert exit_status == rollback.EXIT_REFUSED
    entry = rollback_audit.last_entry(tmp_path)
    assert entry is not None
    assert entry["success"] is False
    assert entry["invocation"] == "auto"


def test_main_writes_a_degraded_marker_when_the_audit_write_itself_fails(tmp_path, monkeypatch):
    """Tier-3 PR review round 4 (e4-checks-deploy-changelog): a
    LockTimeout/OSError from ``rollback_audit.record`` must not be reduced
    to a silent stderr warning — the real (here: refused) outcome's exit
    code is unaffected, but a durable degraded marker must exist for
    ``deploy_checks.check_manual_rollback_proves_alive`` to fail closed on.
    """
    import rollback_audit

    def _boom(*args, **kwargs):
        raise OSError("simulated audit write failure")

    monkeypatch.setattr(rollback_audit, "record", _boom)

    exit_status = rollback.main([
        "--env-name", "dev-demo", "--strategy", "clone",
        "--project-root", str(tmp_path), "--invocation", "manual",
    ])

    assert exit_status == rollback.EXIT_REFUSED  # no --clone-name given; real outcome intact
    marker = tmp_path / ".shipwright" / "deploy" / "rollback-audit-degraded.jsonl"
    entry = json.loads(marker.read_text(encoding="utf-8").splitlines()[-1])
    assert entry["invocation"] == "manual"
    assert "simulated audit write failure" in entry["reason"]


def test_main_records_the_invocation_flag_verbatim(tmp_path):
    """``--invocation manual`` reaches the audit record unchanged — this
    script has no way to infer it, so it must never be defaulted away."""
    import rollback_audit

    exit_status = rollback.main([
        "--env-name", "dev-demo", "--strategy", "clone",
        "--project-root", str(tmp_path), "--invocation", "manual",
    ])

    assert exit_status == rollback.EXIT_REFUSED  # no --clone-name given
    entry = rollback_audit.last_entry(tmp_path)
    assert entry is not None
    assert entry["invocation"] == "manual"
