"""Shared fixtures for the iterate Stop-guard tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPO_ROOT / "plugins" / "shipwright-iterate" / "scripts" / "hooks" / "iterate_stop_guard.py"
BLOCKER_TOOL = REPO_ROOT / "shared" / "scripts" / "tools" / "record_hard_blocker.py"
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))


RUN = "iterate-2026-10-09-demo"
CMD = ("<command-message>x</command-message><command-name>/shipwright-iterate:iterate"
       "</command-name><command-args>{args}</command-args>")


def _transcript(tmp_path: Path, args: str = "--autonomous fix it", tools: int = 1) -> Path:
    lines = [json.dumps({"type": "user", "message": {"content": CMD.format(args=args)}})]
    for _ in range(tools):
        lines.append(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {}}]}}))
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    main = tmp_path / "main"
    main.mkdir()
    git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run([*git, "init", "--quiet", "-b", "main", str(main)], check=True)
    subprocess.run([*git, "-C", str(main), "commit", "--quiet", "--allow-empty", "-m", "i"], check=True)
    worktree = main / ".worktrees" / "demo"
    subprocess.run([*git, "-C", str(main), "worktree", "add", "--quiet", str(worktree),
                    "-b", "iterate/demo"], check=True)
    ptr = main / ".shipwright" / "iterate_active"
    ptr.mkdir(parents=True)
    (ptr / "sess1.json").write_text(json.dumps({
        "run_id": RUN, "slug": "demo", "branch": "iterate/demo",
        "worktree_path": str(worktree), "main_root": str(main), "session_id": "sess1",
    }), encoding="utf-8")
    return main, worktree


def _run_hook(main: Path, transcript: Path, loop_id: str = "", cwd: Path | None = None,
              extra_env: dict | None = None) -> dict | None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("SHIPWRIGHT_")}
    env.update(extra_env or {})
    if loop_id:
        env["SHIPWRIGHT_LOOP_ID"] = loop_id
    proc = subprocess.run(
        [sys.executable, str(HOOK)], cwd=cwd or main, env=env, capture_output=True, text=True,
        input=json.dumps({"session_id": "sess1", "transcript_path": str(transcript)}),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout) if proc.stdout.strip() else None
