"""Shared fixtures of the drops-layout writer tests (campaign events-drop-files, S4)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from tools import record_event  # noqa: E402


def _layout(monkeypatch, which: str) -> None:
    monkeypatch.setenv("SHIPWRIGHT_EVENTS_LAYOUT_TEST", "1")
    monkeypatch.setenv("SHIPWRIGHT_EVENTS_LAYOUT", which)
    monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout


@pytest.fixture(name="drops_repo")
def _drops_repo(tmp_path, monkeypatch):
    _layout(monkeypatch, "drops")
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    for k, v in (("user.email", "t@t"), ("user.name", "t"), ("commit.gpgsign", "false")):
        _git(root, "config", k, v)
    (root / ".gitignore").write_text("*.lock\n.worktrees/\n", encoding="utf-8")
    (root / "README.md").write_text("x\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _ev(eid: str, **extra) -> dict:
    return {"v": 1, "id": eid, "ts": "2026-11-06T10:00:00+00:00", "type": "task_created", "description": "d", **extra}


def _append(root: Path, event: dict, run_id: str | None = None) -> None:
    record_event.append_event(root, event, run_id)


def _drop_names(root: Path) -> list[str]:
    d = root / ".shipwright/events/drops"
    return sorted(p.name for p in d.glob("*.jsonl")) if d.is_dir() else []


