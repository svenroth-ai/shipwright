"""Runs the real ``setup_iterate_worktree.py`` producer as a subprocess.

Extracted so ``test_check_worktree_location.py`` and
``test_campaign_worktree_guard_integration.py`` stop re-deriving the same
subprocess call (code review, iterate-2026-08-26-campaign-worktree-guard-followups).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_SETUP_SCRIPT = (
    Path(__file__).resolve().parent.parent / "scripts" / "tools" / "setup_iterate_worktree.py"
)


def run_setup_iterate_worktree(work: Path, slug: str, run_id: str) -> dict:
    env = os.environ.copy()
    env.pop("SHIPWRIGHT_ITERATE_NO_FETCH", None)
    env.setdefault("SHIPWRIGHT_SESSION_ID", "sess-test")
    result = subprocess.run(
        [sys.executable, str(_SETUP_SCRIPT), "--project-root", str(work),
         "--slug", slug, "--run-id", run_id],
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)
