"""Through the real orchestrator CLI: a guided run past its gate-retry cap waits for a person.

The master used to be the only thing that stopped re-dispatching after the ``ask_human``
terminal. Now ``single-session-next`` itself answers ``ask_human`` (exit 0, nothing
claimed) until a person overrides with the last descriptor (iterate
gate-hardening-leftovers, item 2c).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ORCHESTRATOR = str(REPO_ROOT / "plugins" / "shipwright-run" / "scripts" / "lib" / "orchestrator.py")

pytestmark = [pytest.mark.integration, pytest.mark.covers("FR-01.01/AC02")]


def _cli(project: Path, *args: str) -> tuple[int, dict]:
    env = {k: v for k, v in os.environ.items() if k != "AIKIDO_CLIENT_ID"}
    proc = subprocess.run(
        [sys.executable, ORCHESTRATOR, *args, "--project-root", str(project)],
        capture_output=True, text=True, encoding="utf-8", timeout=60, env=env,
    )
    assert proc.returncode in (0, 1, 2), proc.stderr
    return proc.returncode, json.loads(proc.stdout)


def _apply(project: Path, d: dict, *extra: str) -> tuple[int, dict]:
    (project / "notes.md").write_text("# notes\n", encoding="utf-8")
    result = project / f".result-v{d['version']}.json"
    result.write_text(json.dumps({"ok": True, "phase": d["phase"], "summary": "done",
                                  "artifacts": ["notes.md"]}), encoding="utf-8")
    return _cli(project, "single-session-apply", "--phase-task-id", d["phaseTaskId"],
                "--session-uuid", d["sessionUuid"], "--version", str(d["version"]),
                "--result-json", str(result), *extra)


def test_the_cap_holds_at_next_and_a_person_can_still_override(tmp_path):
    project = tmp_path / "driven"
    project.mkdir()
    code, _ = _cli(project, "write-config", "--scope", "full_app", "--profile",
                   "supabase-nextjs", "--autonomy", "guided", "--mode", "single_session")
    assert code == 0

    rounds, terminal = 0, None
    while terminal is None:  # the project phase writes no spec: its real gate rejects
        rounds += 1
        assert rounds <= 3, "the cap (1 + MAX_GATE_RETRIES) did not trip"
        code, nxt = _cli(project, "single-session-next")
        assert code == 0 and nxt["action"] == "dispatch", nxt
        last = nxt["dispatch"]
        code, rejected = _apply(project, last)
        assert code == 1 and rejected["reason"] == "phase_gate_failed", rejected
        terminal = rejected["terminal"]
    assert terminal == "ask_human" and rounds == 3

    config_before = (project / "shipwright_run_config.json").read_bytes()
    code, waiting = _cli(project, "single-session-next")
    assert code == 0 and waiting["action"] == "ask_human", waiting
    assert waiting["version"] == last["version"] and waiting["issues"]
    assert (project / "shipwright_run_config.json").read_bytes() == config_before

    code, done = _apply(project, last, "--override-reason", "accepted for the test")
    assert code == 0 and done["ok"] is True, done
    code, nxt = _cli(project, "single-session-next")
    assert code == 0 and nxt["action"] == "dispatch" and nxt["dispatch"]["phase"] == "design"


# --- a non-final build archived by the real archive_split CLI passes its gate -------------

sys.path.insert(0, str(REPO_ROOT / "shared" / "testkit"))
import minimal_valid_project as mvp  # noqa: E402

ARCHIVE_SPLIT = str(REPO_ROOT / "shared" / "scripts" / "tools" / "archive_split.py")


def _honest(project: Path, *, archive_next: str | None = None) -> dict:
    code, nxt = _cli(project, "single-session-next")
    assert code == 0 and nxt["action"] == "dispatch", nxt
    d = nxt["dispatch"]
    artifacts = mvp.write_phase(project, d["phase"], d.get("splitId"))
    if archive_next:  # what the build skill does at the end of a non-final split
        proc = subprocess.run([sys.executable, ARCHIVE_SPLIT, "--project-root", str(project),
                               "--next-split", archive_next],
                              capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = {"ok": True, "phase": d["phase"], "summary": "done", "artifacts": artifacts}
    if d.get("splitId"):
        payload["splitId"] = d["splitId"]
    result = project / f".result-{d['phaseTaskId']}.json"
    result.write_text(json.dumps(payload), encoding="utf-8")
    code, applied = _cli(project, "single-session-apply", "--phase-task-id", d["phaseTaskId"],
                         "--session-uuid", d["sessionUuid"], "--version", str(d["version"]),
                         "--result-json", str(result))
    assert code == 0 and applied["gate"]["result"] == "pass", applied
    return d


def test_an_archived_non_final_build_passes_and_the_run_completes(tmp_path):
    project = tmp_path / "split"
    project.mkdir()
    code, _ = _cli(project, "write-config", "--scope", "full_app", "--profile",
                   "supabase-nextjs", "--autonomy", "guided", "--mode", "single_session")
    assert code == 0
    for _ in ("project", "design", "plan"):
        _honest(project)
    build = _honest(project, archive_next=mvp.DEFAULT_SPLITS[1])
    assert (build["phase"], build["splitId"]) == ("build", mvp.DEFAULT_SPLITS[0])
    config = json.loads((project / "shipwright_build_config.json").read_text(encoding="utf-8"))
    assert config["sections"] == [] and config["split_01_sections"]  # it really was archived
    for _ in ("plan", "build", "test", "changelog", "deploy"):
        _honest(project)
    code, out = _cli(project, "single-session-next")
    assert out["action"] == "complete", out
