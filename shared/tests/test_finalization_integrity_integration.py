"""Cross-component integration: the iterate finalization producers (F3
decision-drop + F5c iterate-entry) compose with the F11 verifier consumer.

Proves the fix for iterate-2026-07-20-runner-finalization-integrity end to end
using the REAL producer tools (``write_decision_drop``, ``append_iterate_entry``)
and the REAL verifier functions — not stubs — against a real git repo:

  * happy path  — F3 drop + F5c entry + a commit that does NOT touch
    decision_log.md  => the F11 ADR / history / no-direct checks all pass.
  * forbidden   — the same run whose commit ALSO wrote decision_log.md directly
    => ``check_iterate_no_direct_decision_log`` fails closed.
  * lost ADR    — F5c entry present but the drop is an empty ``{}`` placeholder
    (a silently-lost ADR) => ``check_adr_in_iterate_history`` fails closed.

This is the ``category: "integration"`` behavior the ``cross_component`` gate
requires: it exercises the composition of three components (F3 producer, F5c
producer, F11 consumer) in one real scenario, not each in isolation.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from lib.iterate_entry import sanitize_run_id_for_filename
from tools.append_iterate_entry import append_iterate_entry
from tools.verifiers.iterate_checks import (
    check_adr_in_iterate_history,
    check_iterate_history_has_run_id,
    check_iterate_no_direct_decision_log,
)
from tools.write_decision_drop import write_decision_drop

_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@t.invalid",
    "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@t.invalid",
}


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], env=_GIT_ENV,
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def _init_project(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (root / "shipwright_run_config.json").write_text(
        json.dumps({"scope": "library", "_iterate_migration_state": "complete"}),
        encoding="utf-8",
    )
    _git(root, "init")
    (root / "seed.txt").write_text("seed\n")
    _git(root, "add", "seed.txt")
    _git(root, "commit", "-m", "baseline")


def _entry(run_id: str) -> dict:
    return {
        "run_id": run_id, "date": "2026-07-20T10:00:00Z", "type": "change",
        "complexity": "medium", "branch": f"iterate/{run_id}",
        "spec": None, "tests_passed": True, "adr": run_id,
    }


def _run_f3_f5c(root: Path, run_id: str) -> None:
    """Run the REAL F3 (decision-drop) + F5c (iterate-entry) producers."""
    write_decision_drop(
        root, run_id=run_id, section="Iterate — change: x", title="x",
        context="c", decision="Chose the decision-drop path.", consequences="k",
    )
    append_iterate_entry(root, _entry(run_id))


def test_happy_path_f3_f5c_compose_green(tmp_path):
    root = tmp_path / "proj"
    _init_project(root)
    run_id = "iterate-2026-07-20-compose"
    _run_f3_f5c(root, run_id)
    # A normal iterate commit — a code change, no decision_log.md write.
    (root / "feature.py").write_text("x = 1\n")
    _git(root, "add", "feature.py")
    _git(root, "commit", "-m", "feat: x")
    head = _git(root, "rev-parse", "HEAD")

    assert check_iterate_history_has_run_id(root, run_id).ok is True
    assert check_adr_in_iterate_history(root, run_id).ok is True
    assert check_iterate_no_direct_decision_log(root, run_id, head).ok is True


def test_forbidden_direct_decision_log_write_fails(tmp_path):
    root = tmp_path / "proj"
    _init_project(root)
    run_id = "iterate-2026-07-20-direct"
    _run_f3_f5c(root, run_id)
    log = root / ".shipwright" / "agent_docs" / "decision_log.md"
    log.write_text("# Decision Log\n\n### ADR-070: written directly\n")
    (root / "feature.py").write_text("x = 1\n")
    _git(root, "add", "feature.py", str(log))
    _git(root, "commit", "-m", "feat: x + direct ADR (forbidden)")
    head = _git(root, "rev-parse", "HEAD")

    # F3/F5c still recorded, but the direct decision_log.md write is caught.
    assert check_iterate_history_has_run_id(root, run_id).ok is True
    res = check_iterate_no_direct_decision_log(root, run_id, head)
    assert res.ok is False
    assert "decision_log.md" in res.detail


def test_lost_adr_empty_drop_fails(tmp_path):
    root = tmp_path / "proj"
    _init_project(root)
    run_id = "iterate-2026-07-20-lostadr"
    # F5c ran, but the ADR content was lost — an empty placeholder drop.
    append_iterate_entry(root, _entry(run_id))
    drops = root / ".shipwright" / "agent_docs" / "decision-drops"
    drops.mkdir(parents=True, exist_ok=True)
    (drops / f"{sanitize_run_id_for_filename(run_id)}_001.json").write_text("{}")
    (root / ".shipwright" / "agent_docs" / "decision_log.md").write_text("# Decision Log\n")

    assert check_iterate_history_has_run_id(root, run_id).ok is True
    assert check_adr_in_iterate_history(root, run_id).ok is False
