"""Helpers of the fold / quarantine / integrity tests (campaign events-drop-files, S6): small real git repos."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from lib.events_log import ARCHIVE_DIR, DROPS_DIR

OLD = "2026-01-05T10:00:00+00:00"
NEW = "2026-11-06T10:00:00+00:00"


def git(root: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert not check or r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout


def make_repo(tmp_path: Path, name: str = "repo") -> Path:
    root = tmp_path / name
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    for k, v in (("user.email", "t@t"), ("user.name", "t"), ("commit.gpgsign", "false"), ("core.autocrlf", "false")):
        git(root, "config", k, v)
    (root / ".gitignore").write_text("*.lock\n.worktrees/\n", encoding="utf-8")
    (root / "README.md").write_text("x\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    return root


def commit(root: Path, message: str = "c") -> str:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD").strip()


def ev(eid: str, ts: str = OLD, **extra) -> dict:
    return {"v": 1, "id": eid, "ts": ts, "type": "task_created", "description": "d " + eid, **extra}


def put(root: Path, folder: str, name: str, *records: dict | str) -> Path:
    path = root / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [r if isinstance(r, str) else json.dumps(r, separators=(",", ":")) for r in records]
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8", newline="\n")
    return path


def drop(root: Path, key: str, *records: dict | str, nonce: str = "00000001") -> Path:
    """A drop file named like the writer names it; records get the file's key as ``run`` unless they carry one."""
    stamped = [({"run": key, **r} if isinstance(r, dict) else r) for r in records]
    return put(root, DROPS_DIR, f"{key}--aaaaaaaa--{nonce}.jsonl", *stamped)


def archive_names(root: Path) -> list[str]:
    folder = root / ARCHIVE_DIR
    return sorted(p.name for p in folder.glob("*.jsonl")) if folder.is_dir() else []
