"""Shared helpers for the event-folder-move tests (a git repo fixture, an old-location drop, a move PR branch)."""

from __future__ import annotations

import json
import subprocess

from pathlib import Path

import pytest

LINE = json.dumps({"v": 1, "id": "e1", "ts": "2026-11-06T10:00:00+00:00", "type": "task_created",
                   "description": "d", "run": "run-a"}) + chr(10)
DROP = "run-a--aaaaaaaa--bbbbbbbb.jsonl"


def git(root: "Path", *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    for k, v in (("user.email", "t@t"), ("user.name", "t"), ("commit.gpgsign", "false")):
        git(root, "config", k, v)
    (root / "README.md").write_text("x\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    return root


def old_drop(root: "Path", name: str = DROP) -> Path:
    path = root / "shipwright_events.d" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(LINE, encoding="utf-8")
    return path


@pytest.fixture
def move_pr(repo):
    """Trunk holds a drop at the OLD location; the branch has it at the new one."""
    old_drop(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "trunk")
    git(repo, "branch", "base")
    git(repo, "switch", "-q", "-c", "pr")
    return repo
