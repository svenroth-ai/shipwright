"""Acceptance test for iterate-2026-08-09-compaction-state-audit.

The bug report's scenario is "kill a run mid-phase and prove it resumes from
artifacts alone, with no conversational memory." A literal same-session kill
of the Claude Code process cannot be scripted from inside the very session
doing the fix — there is no test harness that can suspend and restart the
agent loop itself. This is the closest deterministic substitute: fresh
**subprocesses**, each cold-reading only files a fixture setup step wrote to
disk beforehand, exercising the two real mechanisms a resumed run depends on:

1. **AC-3a (primary, canonical):** `record_review_pass.py show` — the exact
   command SKILL.md's B1 instructs an agent to run on resume — must report
   the interrupted-cascade signal from `reviews.json` alone. This is what B1
   actually reads; nothing here depends on any handoff file being fresh.
2. **AC-3b (secondary, best-effort):** the real `generate_handoff_on_stop.py`
   Stop-hook subprocess (the one Claude Code invokes at session end) must
   render the same signal into `session_handoff.md`, for a human or a
   differently-triggered resume path skimming that file.

Neither process is seeded with anything beyond what a fixture would leave on
disk after a mid-phase kill: no environment carries the run's history, no
in-memory state is shared between the fixture-setup step and the two
assertion subprocesses.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STOP_HOOK = REPO_ROOT / "shared" / "scripts" / "hooks" / "generate_handoff_on_stop.py"
RECORD_REVIEW_PASS = REPO_ROOT / "shared" / "scripts" / "tools" / "record_review_pass.py"

RUN_ID = "iterate-2026-08-09-killmidphase"
SLUG = "killmidphase"


def _init_git_repo_on_iterate_branch(project_root: Path) -> None:
    """Mimic what `setup_iterate_worktree.py` leaves behind: a repo whose
    current branch is `iterate/<slug>` — the signal `render_iterate_progress`
    keys off to even look for iterate state."""
    run = lambda *args: subprocess.run(  # noqa: E731
        ["git", *args], cwd=project_root, check=True,
        capture_output=True, text=True,
    )
    run("init", "-q")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "Test")
    (project_root / "README.md").write_text("placeholder\n", encoding="utf-8")
    run("add", "-A")
    run("commit", "-q", "-m", "initial")
    run("checkout", "-q", "-b", f"iterate/{SLUG}")


def _seed_mid_phase_fixture(project_root: Path) -> None:
    """Lay down exactly what a run killed right after Stage-1 review (spec
    passed) but before Stage 2 (code) would have on disk — nothing more.
    No process below this point is told any of this directly; each rediscovers
    it from these files alone."""
    (project_root / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (project_root / "shipwright_run_config.json").write_text(
        json.dumps({"scope": "full_app", "iterate_history": [
            {"run_id": RUN_ID, "complexity": "medium"},
        ]}),
        encoding="utf-8",
    )

    iterate_dir = project_root / ".shipwright" / "planning" / "iterate"
    iterate_dir.mkdir(parents=True, exist_ok=True)
    (iterate_dir / f"2026-08-09-{SLUG}.md").write_text(
        "\n".join([
            f"# Iterate Spec: {SLUG}",
            "",
            f"- **Run ID:** {RUN_ID}",
            "- **Type:** feature",
            "- **Complexity:** medium",
            "- **Status:** in-progress",
        ]),
        encoding="utf-8",
    )

    from lib.review_record_schema import REVIEW_TYPES  # noqa: E402

    record_dir = iterate_dir / RUN_ID
    record_dir.mkdir(parents=True, exist_ok=True)
    terminal = {"self", "plan", "plan_internal", "spec"}
    reviews = {
        t: {
            "review_type": t,
            "status": "completed" if t in terminal else "pending",
            "findings_count": 0,
            "findings": [],
            "provider": None,
            "completed_at": None,
            "disposition": None,
            "recorded_by": None,
            "parse_status": None,
            "raw_excerpt": None,
        }
        for t in REVIEW_TYPES
    }
    (record_dir / "reviews.json").write_text(
        json.dumps({"schema_version": 1, "run_id": RUN_ID, "reviews": reviews}),
        encoding="utf-8",
    )


def test_ac3a_record_review_pass_show_reports_interrupted_cascade(tmp_path):
    """AC-3a — the canonical resume signal (B1's own instruction) must come
    back correct from a cold subprocess reading only reviews.json."""
    project_root = tmp_path
    _init_git_repo_on_iterate_branch(project_root)
    _seed_mid_phase_fixture(project_root)

    result = subprocess.run(
        [sys.executable, str(RECORD_REVIEW_PASS), "show",
         "--project-root", str(project_root), "--run-id", RUN_ID],
        capture_output=True, text=True, check=True,
    )
    record = json.loads(result.stdout)
    reviews = record["reviews"]

    assert reviews["self"]["status"] == "completed"
    assert reviews["spec"]["status"] == "completed"
    assert reviews["code"]["status"] == "pending"
    assert reviews["doubt"]["status"] == "pending"


def test_ac3b_stop_hook_handoff_surfaces_interrupted_cascade(tmp_path):
    """AC-3b — the same signal, rendered into the handoff a human or a
    differently-triggered resume reads, produced by the real Stop-hook
    subprocess (not by calling render_iterate_progress() in-process)."""
    project_root = tmp_path
    _init_git_repo_on_iterate_branch(project_root)
    _seed_mid_phase_fixture(project_root)

    env = os.environ.copy()
    env["SHIPWRIGHT_SESSION_ID"] = "acceptance-test-session"
    result = subprocess.run(
        [sys.executable, str(STOP_HOOK)],
        input="{}", capture_output=True, text=True, cwd=project_root, env=env,
    )
    assert result.returncode == 0, result.stderr

    handoff = project_root / ".shipwright" / "agent_docs" / "runtime" / "session_handoff.md"
    assert handoff.exists(), f"no runtime handoff written; stderr={result.stderr!r}"
    content = handoff.read_text(encoding="utf-8")

    assert "Current Iterate Progress" in content
    assert RUN_ID in content
    assert "Review Cascade" in content and "interrupted" in content
    assert "code" in content and "doubt" in content
    assert "Mandatory replay on Resume" in content
    assert "Review cascade interrupted" in content


def test_ac3a_and_ac3b_agree_on_which_types_are_pending(tmp_path):
    """Both paths must name the SAME pending set from the SAME fixture —
    the renderer is a convenience view over the same reviews.json B1 reads
    directly, not an independent (and possibly divergent) source of truth."""
    project_root = tmp_path
    _init_git_repo_on_iterate_branch(project_root)
    _seed_mid_phase_fixture(project_root)

    show_result = subprocess.run(
        [sys.executable, str(RECORD_REVIEW_PASS), "show",
         "--project-root", str(project_root), "--run-id", RUN_ID],
        capture_output=True, text=True, check=True,
    )
    record = json.loads(show_result.stdout)
    pending_from_record = {
        t for t, entry in record["reviews"].items() if entry["status"] == "pending"
    }

    env = os.environ.copy()
    env["SHIPWRIGHT_SESSION_ID"] = "acceptance-test-session"
    subprocess.run(
        [sys.executable, str(STOP_HOOK)],
        input="{}", capture_output=True, text=True, cwd=project_root, env=env,
        check=True,
    )
    handoff = project_root / ".shipwright" / "agent_docs" / "runtime" / "session_handoff.md"
    content = handoff.read_text(encoding="utf-8")

    for pending_type in pending_from_record:
        assert pending_type in content, (
            f"reviews.json names {pending_type!r} pending but the rendered "
            "handoff's Review Cascade line omits it"
        )
