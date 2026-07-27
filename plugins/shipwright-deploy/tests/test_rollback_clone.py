"""Clone-strategy rollback + CLI argument validation.

Split out of ``test_rollback.py`` (which owns the git-strategy ref contract) to
keep both files under the repo's 300-line guideline.
"""

import json
import subprocess
import sys
from pathlib import Path

import rollback

SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "lib" / "rollback.py")


# --------------------------------------------------------------------------
# AC10 — stopping is never reported as restoring
# --------------------------------------------------------------------------

def test_clone_strategy_reports_stopping_not_restoring(client):
    client()

    result = rollback.rollback_clone("prod-demo", "prod-demo-backup")

    assert result["success"] is True
    assert result["restored"] is False
    assert result["next_steps"]
    assert "stopped" in result["message"].lower()


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

def _run(*args):
    completed = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, encoding="utf-8",
    )
    return completed, json.loads(completed.stdout)


def test_git_strategy_requires_target_ref():
    """Git strategy without --target-ref should fail."""
    completed, output = _run("--env-name", "test-env", "--strategy", "git")
    assert output["success"] is False
    assert "target-ref" in output["error"]
    assert completed.returncode == rollback.EXIT_REFUSED


def test_clone_strategy_requires_clone_name():
    """Clone strategy without --clone-name should fail."""
    completed, output = _run("--env-name", "test-env", "--strategy", "clone")
    assert output["success"] is False
    assert "clone-name" in output["error"]
    assert completed.returncode == rollback.EXIT_REFUSED


def test_a_refusal_says_the_target_was_not_touched(client):
    """AC9 — a pre-flight refusal must make no claim about what is running."""
    completed, output = _run("--env-name", "test-env", "--strategy", "git")

    assert output["mutated"] is False
    assert output["halt"] is False
    assert "nothing on the hosting target was changed" in output["operator_message"].lower()
    assert completed.returncode != rollback.EXIT_HALT
    del client
