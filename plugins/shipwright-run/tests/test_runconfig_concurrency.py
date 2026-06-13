"""WP2/F11+F12: concurrent multi-process writers never truncate or lose config.

This is the cross_component **integration coverage** for the audit. ALL THREE
writer families named in the audit hammer the same ``shipwright_run_config.json``
from separate OS processes under their respective (path-coordinated) advisory
locks:

  * orchestrator      — ``update_step``            (run_config_lock)
  * phase-task         — ``recover_phase_task``     (_PhaseTasksLock)
  * phase-history      — ``append_phase_history``   (file_lock)

After the storm:
  * the file is always valid JSON (atomic tmp+os.replace => no torn read), and
  * every write from EVERY family survived (no stale-copy clobber):
      - update_step's ``current_step`` is set,
      - recover_phase_task bumped ``version`` exactly N times, and
      - append_phase_history appended exactly N phase_history entries.

Real OS subprocesses are used (not threads / multiprocessing pickling) so the
file lock is exercised across true process boundaries — the only level at
which advisory locks actually coordinate.
"""
import json
import subprocess
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib"

CONFIG_NAME = "shipwright_run_config.json"
N_ITERS = 40

# Self-contained worker run via ``python -c`` so it imports cleanly in a fresh
# process regardless of how pytest named this test module.
#   argv: [run_lib_path, project_root, kind, iters]
_WORKER_SRC = """
import sys
from pathlib import Path
lib, root, kind, iters = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
sys.path.insert(0, lib)
root = Path(root)
if kind == "orchestrator":
    from orchestrator import update_step
    for _ in range(iters):
        update_step(root, "test", "in_progress")
elif kind == "phase_task":
    from phase_task_lifecycle import recover_phase_task
    for _ in range(iters):
        recover_phase_task(root, phase_task_id="ptk-conc01", force_status="awaiting_launch")
else:  # phase_history — the third writer family, via its real RMW + atomic write
    repo_root = Path(lib).parents[3]
    sys.path.insert(0, str(repo_root / "shared" / "scripts" / "tools"))
    from run_config_store import run_config_lock
    from append_phase_history import append_history
    for i in range(iters):
        with run_config_lock(root):
            append_history(root, "build", {"run_id": "ph-%d" % i, "date": "2026-06-13"})
"""


def _seed_config(project_root: Path) -> None:
    cfg = {
        "schemaVersion": 2,
        "scope": "full_app",
        "pipeline": ["project", "design", "plan", "build", "test", "changelog", "deploy"],
        "phase_tasks": [{
            "phaseTaskId": "ptk-conc01",
            "phase": "build",
            "status": "in_progress",
            "version": 1,
            "claimedBySessionUuid": "seed",
            "prerequisites": [],
            "executionCount": 1,
        }],
        "completed_phase_task_ids": [],
        "splits_frozen": [],
        "runConditions": {"securityEnabled": False, "splitMode": None, "aikidoClientIdPresent": False},
        "status": "in_progress",
        "completed_steps": [],
        "current_step": "project",
        "created_at": "2026-06-13T00:00:00+00:00",
        "phase_history": {},
    }
    (project_root / CONFIG_NAME).write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


def _spawn(kind: str, project_root: Path) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", _WORKER_SRC, str(_LIB), str(project_root), kind, str(N_ITERS)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )


def test_three_process_writers_no_truncation_no_lost_update(tmp_path):
    _seed_config(tmp_path)

    procs = [
        _spawn("orchestrator", tmp_path),
        _spawn("phase_task", tmp_path),
        _spawn("phase_history", tmp_path),
    ]
    for p in procs:
        out, err = p.communicate(timeout=120)
        assert p.returncode == 0, f"worker failed (rc={p.returncode}):\n{err}"

    # Never truncated => always parseable, regardless of interleaving.
    cfg = json.loads((tmp_path / CONFIG_NAME).read_text(encoding="utf-8"))

    # Each family's writes ALL survived (a stale-copy clobber — the F11 bug —
    # would drop some, failing one of these exact counts):
    assert cfg["current_step"] == "test"                       # orchestrator family
    assert cfg["phase_tasks"][0]["version"] == 1 + N_ITERS     # phase-task family
    assert len(cfg["phase_history"]["build"]) == N_ITERS       # phase-history family
