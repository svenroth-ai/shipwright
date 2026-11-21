"""Reminder CLI across real processes and a real git worktree (E1a)."""

from __future__ import annotations

import json

import pytest
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).resolve().parent.parent / "scripts" / "tools" / "reminder_cli.py"


def _git(cwd, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd, check=True, capture_output=True,
    )


def _cli(cwd, *args):
    return subprocess.run([sys.executable, str(CLI), *args], cwd=cwd,
                          capture_output=True, text=True)


@pytest.mark.covers("FR-01.22/AC05")
def test_two_processes_adding_both_survive_with_distinct_ids(tmp_path):
    procs = [
        subprocess.Popen(
            [sys.executable, str(CLI), "--project-root", str(tmp_path), "add", f"T{i}",
             "--due", "2026-11-28", "--why", "w", "--json"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for i in range(4)
    ]
    outs = [p.communicate() for p in procs]
    assert all(p.returncode == 0 for p in procs), outs
    ids = {json.loads(o)["id"] for o, _ in outs}
    assert len(ids) == 4
    listed = json.loads(_cli(tmp_path, "--project-root", str(tmp_path), "list", "--json").stdout)
    assert {r["id"] for r in listed["reminders"]} == ids


@pytest.mark.covers("FR-01.22/AC02")
def test_reminder_written_from_a_worktree_lands_in_the_main_store(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q", "-b", "main")
    (main / "f.txt").write_text("x")
    _git(main, "add", "f.txt")
    _git(main, "commit", "-q", "-m", "init")
    wt = tmp_path / "wt"
    _git(main, "worktree", "add", "-q", str(wt), "-b", "side")

    res = _cli(wt, "--project-root", str(wt), "add", "From worktree",
               "--due", "2026-11-28", "--why", "w", "--json")
    assert res.returncode == 0, res.stderr
    rid = json.loads(res.stdout)["id"]
    assert rid in (main / ".shipwright" / "reminders.jsonl").read_text(encoding="utf-8")
    assert not (wt / ".shipwright" / "reminders.jsonl").exists()
    # and it is visible from the main checkout too
    shown = _cli(main, "show", rid, "--project-root", str(main), "--json")
    assert shown.returncode == 0 and json.loads(shown.stdout)["title"] == "From worktree"


@pytest.mark.covers("FR-01.22/AC01")
def test_non_ascii_text_round_trips_through_the_cli_on_any_console(tmp_path):
    title = "Prüfen — 日本語"
    env = {**__import__("os").environ, "PYTHONIOENCODING": "cp1252"}
    res = subprocess.run(
        [sys.executable, str(CLI), "--project-root", str(tmp_path), "add", title,
         "--due", "2026-11-28", "--why", "w"],
        capture_output=True, env=env,
    )
    assert res.returncode == 0, res.stderr
    shown = subprocess.run(
        [sys.executable, str(CLI), "--project-root", str(tmp_path), "list", "--json"],
        capture_output=True, env=env,
    )
    assert json.loads(shown.stdout.decode("utf-8"))["reminders"][0]["title"] == title
