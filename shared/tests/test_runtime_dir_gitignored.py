"""Drift protection: ``.shipwright/agent_docs/runtime/`` stays gitignored.

iterate-2026-05-27-tracked-artifacts-single-producer-and-finalize-sandbox
makes runtime/ the live-state target for Stop-hook writers. A future
gitignore-allowlist refactor must not re-include it; if anyone tracks a
runtime file (intentionally or by accident), every Stop hook will dirty
the working tree again — the exact regression this iterate closes.

Empirical probe: feed a candidate runtime file path to
``git check-ignore`` and assert non-zero exit (ignored).
"""

from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_runtime_dir_is_gitignored() -> None:
    probe = REPO_ROOT / ".shipwright" / "agent_docs" / "runtime" / "session_handoff.md"
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "check-ignore", "-v", str(probe)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    # exit 0 = ignored (rule matched); exit 1 = not ignored; exit >1 = error
    assert proc.returncode == 0, (
        f"expected runtime/session_handoff.md to be gitignored, "
        f"got rc={proc.returncode}, stderr={proc.stderr!r}"
    )
    assert "/.shipwright/agent_docs/runtime/" in proc.stdout, (
        f"unexpected matching gitignore rule: {proc.stdout!r}"
    )


def test_runtime_dir_never_committed() -> None:
    """Empirical anti-regression: no runtime/* path has ever been tracked.

    External review finding OpenAI #9 — gitignore alone is insufficient
    once a file lands in the index. Verified empirically pre-build.
    """
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", ".shipwright/agent_docs/runtime/"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "", (
        f"unexpected tracked files under runtime/: {proc.stdout!r}\n"
        "Run `git rm --cached .shipwright/agent_docs/runtime/*` to untrack."
    )
