"""``iterate_stop_finalize`` repair pass refuses to run without worktree pointer.

iterate-2026-05-27-tracked-artifacts-single-producer-and-finalize-sandbox
SCOPE 2: the repair pass would previously fall back to cwd
(``resolve_project_root()``) when ``_active_worktree_root()`` returned None,
running ``finalize_iterate.run()`` against the main tree and writing the 5
compliance MDs + (now) 3 agent-doc MDs into main — bypassing PR #78's
single-producer guarantee.

Drift protection: invoke the hook with a stale session-id pointing nowhere,
cwd at a fake main tree, assert NO writes land under
``.shipwright/compliance/*.md`` or ``.shipwright/agent_docs/*.md``.
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPO_ROOT / "plugins" / "shipwright-iterate" / "scripts" / "hooks" / "iterate_stop_finalize.py"


def _seed_main_tree(project_root: Path) -> None:
    """Bare-minimum Shipwright-managed tree, sans worktree pointer."""
    (project_root / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete"}),
        encoding="utf-8",
    )
    # Initialize as git repo so the worktree-isolation lib's lookup doesn't
    # error out before reaching its containment check.
    subprocess.run(
        ["git", "init", "--quiet", "-b", "main", str(project_root)],
        check=True,
    )
    sw = project_root / ".shipwright"
    (sw / "agent_docs").mkdir(parents=True, exist_ok=True)
    (sw / "compliance").mkdir(parents=True, exist_ok=True)


def test_repair_pass_refuses_when_no_worktree_pointer(tmp_path: Path) -> None:
    _seed_main_tree(tmp_path)

    env = os.environ.copy()
    env["SHIPWRIGHT_SESSION_ID"] = str(uuid.uuid4())  # no pointer for this id
    env["SHIPWRIGHT_PROJECT_ROOT"] = str(tmp_path)

    proc = subprocess.run(
        ["uv", "run", "--no-project", "--project", str(REPO_ROOT), str(HOOK)],
        input="{}",
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )

    # Hook always exits 0 (Stop chain non-blocking).
    assert proc.returncode == 0, (
        f"hook returned non-zero: rc={proc.returncode}\nstdout={proc.stdout!r}\n"
        f"stderr={proc.stderr!r}"
    )

    # The hook may or may not log the gate message (handoff also logs);
    # the important assertion is the WRITE EFFECT:
    # NO compliance MDs should appear in the fake main tree.
    compliance_dir = tmp_path / ".shipwright" / "compliance"
    compliance_md_files = sorted(compliance_dir.glob("*.md"))
    assert compliance_md_files == [], (
        f"repair pass wrote compliance MDs in main tree: "
        f"{[str(p) for p in compliance_md_files]}\n"
        f"This is the iterate-2026-05-27 SCOPE 2 regression.\n"
        f"stderr={proc.stderr!r}"
    )

    # Tracked agent-doc MDs must also stay absent. (The handoff Stop step
    # writes runtime/ — that's allowed; the tracked path must not appear.)
    agent_docs = tmp_path / ".shipwright" / "agent_docs"
    for tracked_name in ("session_handoff.md", "build_dashboard.md", "triage_inbox.md"):
        assert not (agent_docs / tracked_name).exists(), (
            f"repair pass wrote tracked agent_docs/{tracked_name} in main tree.\n"
            f"stderr={proc.stderr!r}"
        )
