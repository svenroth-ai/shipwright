"""Real writers under the drops layout (issue 978, campaign unit S4).

* KC4: 12 parallel Stop-hook writers of ONE ``phase_completed`` leave exactly one, and a re-run of the
  phase under a fresh run id does not duplicate it (the dedup reads the whole log under the own-key lock);
* a real ``ensure_current`` ABSORBS a late drop of this worktree, but not the file carrying the run's gate
  event: when F6 forgot to stage that one, the F11 committed-check FAILS after the absorb.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from test_events_drops_ensure_current import _ensure_current, _env, _world
from test_events_drops_harness import _git, _git_version

REPO = Path(__file__).resolve().parents[1]
RECORD_EVENT = REPO / "shared" / "scripts" / "tools" / "record_event.py"
sys.path.insert(0, str(REPO / "shared" / "scripts"))
sys.path.insert(0, str(REPO / "shared" / "testkit"))

from event_log_probe import event_records  # noqa: E402

pytestmark = [pytest.mark.covers("FR-01.11"), pytest.mark.skipif(
    _git_version() < (2, 40), reason="needs git >= 2.40")]


def _stop_hook(root: Path, run_id: str, session: str = "sess-kc4") -> dict:
    env = _env(run_id)
    env["SHIPWRIGHT_SESSION_ID"] = session
    r = subprocess.run(
        [sys.executable, str(RECORD_EVENT), "--project-root", str(root), "--type", "phase_completed",
         "--phase", "plan", "--detail", json.dumps({"sections": 3})],
        cwd=root, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    assert r.returncode == 0, f"record_event failed: {r.stdout[-300:]} {r.stderr[-300:]}"
    return json.loads(r.stdout)


def _phase_completed(root: Path) -> list[dict]:
    return [e for e in event_records(root) if e.get("type") == "phase_completed" and e.get("phase") == "plan"]


def test_kc4_twelve_parallel_stop_hooks_record_one_phase_completed(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _i: _stop_hook(root, "run-plan-1"), range(12)))
    assert sum(1 for r in results if r.get("skipped")) == 11 and sum(1 for r in results if not r.get("skipped")) == 1
    assert len(_phase_completed(root)) == 1
    # a re-run of `plan` with a FRESH run id must not duplicate it either (different key, same session)
    again = _stop_hook(root, "run-plan-2")
    assert again.get("skipped") is True and again.get("reason") == "duplicate_phase"
    assert len(_phase_completed(root)) == 1
    names = sorted(p.name for p in (root / "shipwright_events.d").glob("*.jsonl"))
    assert len(names) == 1 and names[0].startswith("run-plan-1--")  # one file: the skipped writers created none


def test_a_real_ensure_current_absorbs_a_late_drop_but_leaves_the_gate_event_to_f6(tmp_path):
    branch, _sibling, _origin = _world(tmp_path)
    late = dict(os.environ)
    late.update(_env("late-key"))
    subprocess.run([sys.executable, str(RECORD_EVENT), "--project-root", str(branch), "--type", "task_created",
                    "--description", "late", "--source", "harness"], cwd=branch, env=late, check=True,
                   capture_output=True, text=True, timeout=120)
    # the run's own gate event, written but never staged by F6
    gate = _env("run-a2")
    subprocess.run([sys.executable, str(RECORD_EVENT), "--project-root", str(branch), "--type", "work_completed",
                    "--source", "iterate", "--intent", "change", "--description", "d", "--adr-id", "run-a2",
                    "--change-type", "tooling", "--none-reason", "tooling only", "--spec-impact", "none",
                    "--spec-impact-justification", "tooling only", "--spec-impact-reason-code", "tooling-only"],
                   cwd=branch, env=gate, check=True, capture_output=True, text=True, timeout=120)
    result = _ensure_current(branch, "run-a2")
    assert result.returncode == 0, result.stdout[-800:] + result.stderr[-800:]
    assert "events-absorbed" in json.loads(result.stdout)["steps"]
    tracked = _git(branch, "ls-files", "shipwright_events.d").stdout.split()
    assert any("late-key--" in t for t in tracked) and not any("run-a2--" in t for t in tracked)

    from tools.verifiers.iterate_checks import check_events_has_commit
    forgot = check_events_has_commit(branch, "", run_id="run-a2")
    assert forgot.ok is False and "NOT in any commit" in forgot.detail  # F6 forgot: F11 FAILS after the absorb
    _git(branch, "add", "--", *[p for p in (branch / "shipwright_events.d").glob("run-a2--*.jsonl")])
    _git(branch, "commit", "-q", "-m", "F6 (late)")
    assert check_events_has_commit(branch, "", run_id="run-a2").ok is True
