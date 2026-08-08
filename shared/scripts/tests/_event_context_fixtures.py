"""Git-repo + event-log fixture builders shared by the event_context_index
test modules (test_event_context_backfill.py, test_event_context_coverage_
envelope.py, test_commit_trailers.py).

A plain helper module rather than a ``conftest.py`` addition, following the
``_fr_history_fixtures.py`` precedent: these are constructors, not pytest
fixtures. Split out (iterate-2026-08-08-coverage-envelope-split) once a third
test module needed byte-identical copies of the same four helpers.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                    capture_output=True, text=True)


def init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    git(repo, "checkout", "-q", "-b", "main")


def commit(repo: Path, filename: str, content: str, message: str) -> str:
    (repo / filename).parent.mkdir(parents=True, exist_ok=True)
    (repo / filename).write_text(content, encoding="utf-8")
    git(repo, "add", filename)
    git(repo, "commit", "-q", "-m", message)
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


def write_events(root: Path, events: list[dict]) -> None:
    (root / "shipwright_events.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )
