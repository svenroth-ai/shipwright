"""Cross-surface back-compat + campaign known-bug regression roster (SS7).

Two guarantees the capstone owes the campaign, distinct from the single-session
story in ``test_single_session_capstone.py``:

  * **(C) an in-flight MULTI-session run remains resumable.** The default
    (``multi_session``) path must survive a crash and be picked back up — closing
    the positive-half hole the existing suite left open (SS3/SS5 / the existing
    multi_session suite proved a *stale* completion is rejected; nothing proved the
    recovered task is re-claimed on its bumped version, completed, and the pipeline
    advances). And it must do so WITHOUT the SS5 single-session machinery leaking
    in: no ``run_loop_state.json`` / ``run_loop_events.jsonl`` may ever appear for a
    multi_session run. (C) is driven over the real orchestrator subprocess CLI —
    the exact surface a phase Stop hook invokes.

  * **(D) the external_review gate can never silently no-op** — a thin, in-process
    roster pin for SS6 (#351). Deep coverage (the full CLI, every
    degraded/partial/no-key branch) lives in
    ``shared/tests/test_external_review_degraded.py``; this is the campaign-level
    guard that the loud-fail contract stays intact.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ORCHESTRATOR = str(
    REPO_ROOT / "plugins" / "shipwright-run" / "scripts" / "lib" / "orchestrator.py",
)


# ---------- helpers -----------------------------------------------------

def _run_cli(args: list[str], project_root: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    res = subprocess.run(
        [sys.executable, ORCHESTRATOR, *args, "--project-root", str(project_root)],
        capture_output=True, text=True, encoding="utf-8", timeout=30, env=env,
    )
    if res.returncode not in (0, 1, 2):
        raise RuntimeError(
            f"Orchestrator CLI crashed: rc={res.returncode}\n"
            f"stdout={res.stdout!r}\nstderr={res.stderr!r}",
        )
    return res


def _write_multi_config(project: Path) -> dict:
    # SS8: single_session is the default now — request the DEPRECATED multi_session
    # path explicitly (this suite proves that legacy path stays resumable).
    res = _run_cli([
        "write-config", "--scope", "full_app", "--profile", "supabase-nextjs",
        "--autonomy", "guided", "--deploy-target", "jelastic-dev",
        "--mode", "multi_session",
    ], project)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def _read_config(project: Path) -> dict:
    return json.loads((project / "shipwright_run_config.json").read_text("utf-8"))


def _task(project: Path, phase_task_id: str) -> dict:
    return next(t for t in _read_config(project)["phase_tasks"]
               if t["phaseTaskId"] == phase_task_id)


def _claim(project: Path, *, phase_task_id: str, session_uuid: str,
           expected_phase: str) -> subprocess.CompletedProcess:
    return _run_cli([
        "claim-phase-task", "--phase-task-id", phase_task_id,
        "--session-uuid", session_uuid, "--expected-phase", expected_phase,
    ], project)


def _complete(project: Path, *, phase_task_id: str, session_uuid: str,
              version: int) -> subprocess.CompletedProcess:
    result_path = project / f".result-{phase_task_id}.json"
    result_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
    return _run_cli([
        "complete-phase-task", "--phase-task-id", phase_task_id,
        "--session-uuid", session_uuid, "--version", str(version),
        "--result-json", str(result_path),
    ], project)


def _no_single_session_files(project: Path) -> bool:
    sh = project / ".shipwright"
    return not (sh / "run_loop_state.json").exists() and \
        not (sh / "run_loop_events.jsonl").exists()


def _load_finalize_review_output():
    """Import shared's finalize_review_output WITHOUT leaking sys.path into later
    tests (restores it in a finally) — the loud-fail contract's single source."""
    import importlib
    lib_dir = str(REPO_ROOT / "shared" / "scripts" / "lib")
    added = lib_dir not in sys.path
    if added:
        sys.path.insert(0, lib_dir)
    try:
        return importlib.import_module("external_review_degraded").finalize_review_output
    finally:
        if added:
            sys.path.remove(lib_dir)


# ---------- (C) in-flight multi-session run remains resumable -----------

class TestMultiSessionRemainsResumable:
    """Default-path resumability positive half + no single-session leak."""

    def test_crash_recover_reclaim_complete_advances(self, tmp_path):
        project = tmp_path / "multi-resume"
        project.mkdir()
        cfg = _write_multi_config(project)
        assert cfg["mode"] == "multi_session"
        first = cfg["phase_tasks"][0]
        assert first["phase"] == "project"

        # 1. A session claims project, then CRASHES (never completes).
        assert _claim(project, phase_task_id=first["phaseTaskId"],
                      session_uuid=first["sessionUuid"], expected_phase="project").returncode == 0
        crashed_version = _task(project, first["phaseTaskId"])["version"]

        # 2. recover-phase-task releases the wedged claim (version bumps).
        assert _run_cli(["recover-phase-task", "--phase-task-id",
                         first["phaseTaskId"]], project).returncode == 0
        recovered = _task(project, first["phaseTaskId"])
        assert recovered["status"] == "awaiting_launch"
        assert recovered["claimedBySessionUuid"] is None
        assert recovered["version"] > crashed_version

        # 3. The crashed attempt is fenced off: its now-stale completion is refused
        #    (the safety pivot that makes resume meaningful). Exhaustive negative
        #    coverage of this rejection lives in test_multi_session_pipeline.py.
        stale = _complete(project, phase_task_id=first["phaseTaskId"],
                          session_uuid=first["sessionUuid"], version=crashed_version)
        assert stale.returncode == 2, stale.stdout

        # 4. POSITIVE HALF: the recovered task is re-claimed on its BUMPED version and
        #    completed (in multi_session the sessionUuid is bound to the task, so the
        #    relaunched `claude --session-id` reuses it — the version is what fences
        #    the crashed attempt out, not session identity).
        assert _claim(project, phase_task_id=first["phaseTaskId"],
                      session_uuid=recovered["sessionUuid"], expected_phase="project").returncode == 0
        reclaimed_version = _task(project, first["phaseTaskId"])["version"]
        done = _complete(project, phase_task_id=first["phaseTaskId"],
                         session_uuid=recovered["sessionUuid"], version=reclaimed_version)
        assert done.returncode == 0, done.stdout

        # 5. The pipeline advanced: project done, design is the new frontier, run alive.
        assert _task(project, first["phaseTaskId"])["status"] == "done"
        after = _read_config(project)
        assert after["status"] == "in_progress"
        frontier = next(t for t in after["phase_tasks"] if t["status"] == "awaiting_launch")
        assert frontier["phase"] == "design"

        # 6. Back-compat: the SS5 single-session machinery never touched this run.
        assert _no_single_session_files(project)


# ---------- (D) external_review roster pin -----------------------------

class TestExternalReviewGateCannotSilentlyNoop:
    """Thin campaign-level pin of SS6's loud-fail contract (#351). The exhaustive
    coverage lives in shared/tests/test_external_review_degraded.py — this guards
    that a review gate with keys present but ZERO successful reviews fails LOUD."""

    def test_degraded_gate_is_loud(self):
        finalize_review_output = _load_finalize_review_output()

        # Keys present (provider attempted) but every leg failed -> degraded, exit 1.
        out, code = finalize_review_output("direct", {
            "gemini": {"status": "skipped", "reason": "GEMINI_API_KEY missing"},
            "openai": {"status": "error", "reason": "max_tokens unsupported"},
        })
        assert code == 1, "a degraded gate MUST exit non-zero (no silent no-op)"
        assert out["success"] is False and out["degraded"] is True
        assert out["reviews_succeeded"] == 0
        assert out.get("degraded_reason"), "degraded output must carry a machine-readable reason"

        # Contrast: one leg succeeding is NOT degraded (exit 0) — the gate isn't trigger-happy.
        healthy, hcode = finalize_review_output("direct", {
            "gemini": {"status": "success"},
            "openai": {"status": "error", "reason": "max_tokens unsupported"},
        })
        assert hcode == 0 and healthy["success"] is True and healthy["degraded"] is False


# ---------- chat-surface honest decline (parity's other half) ----------

_RUN_SKILL = REPO_ROOT / "plugins" / "shipwright-run" / "skills" / "run" / "SKILL.md"
_BANNER_GUARD = (REPO_ROOT / "plugins" / "shipwright-run" / "tests"
                 / "test_run_skill_handoff_banner.py")


class TestChatSurfaceHonestDecline:
    """Parity's honest other half: a chat surface (VS Code / desktop) can't launch
    a bound multi_session phase session, so /shipwright-run must DECLINE honestly
    there — not silently stall. Enforces the reference the capstone parity test
    leans on (the SKILL.md prose contract + its drift-guard both exist) rather than
    only documenting it. Deep prose coverage: test_run_skill_handoff_banner.py."""

    def test_run_skill_declines_on_chat_surface(self):
        assert _BANNER_GUARD.exists(), "the chat-surface banner drift-guard must exist"
        text = _RUN_SKILL.read_text(encoding="utf-8")
        assert "CLAUDE_CODE_ENTRYPOINT" in text, "the master must detect the launch surface"
        a = text.find("**(a) `surface` is chat")
        b = text.find("**(b) `surface` is terminal")
        assert a != -1 and b != -1 and a < b, "SKILL.md must carry chat/terminal branches"
        assert "can't" in text[a:b].lower() or "cannot" in text[a:b].lower(), \
            "the chat branch must honestly state the pipeline can't launch here"
