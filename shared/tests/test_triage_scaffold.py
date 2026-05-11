"""AC-6 scaffolder tests — idempotent triage-inbox bootstrap.

Covers:
- JSONL header creation on fresh project
- JSONL header preservation on re-run (idempotency)
- triage_inbox.md skeleton write
- .gitignore append (file absent / present-without-line / present-with-line)
- Combined idempotency across all 3 writers (re-run produces same content)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from tools.scaffold_triage_inbox import (  # noqa: E402
    GITIGNORE_LINES,
    scaffold_triage_inbox,
)

SCAFFOLDER = _WORKTREE / "shared" / "scripts" / "tools" / "scaffold_triage_inbox.py"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


# --- JSONL header creation ----------------------------------------------

def test_creates_jsonl_with_header(project: Path) -> None:
    result = scaffold_triage_inbox(project)
    triage = project / ".shipwright" / "triage.jsonl"
    assert triage.exists()
    first_line = triage.read_text(encoding="utf-8").splitlines()[0]
    header = json.loads(first_line)
    assert header == {"v": 1, "schema": "triage", "created": header["created"]}
    assert "Z" in header["created"]  # ISO-8601 Z suffix
    assert result["results"]["jsonl"]["action"] == "created"


def test_preserves_existing_jsonl_on_rerun(project: Path) -> None:
    """Idempotency: second invocation doesn't rewrite the header."""
    scaffold_triage_inbox(project)
    triage = project / ".shipwright" / "triage.jsonl"
    first_content = triage.read_text(encoding="utf-8")

    result = scaffold_triage_inbox(project)
    second_content = triage.read_text(encoding="utf-8")
    assert first_content == second_content
    assert result["results"]["jsonl"]["action"] == "preserved"


# --- Markdown skeleton --------------------------------------------------

def test_creates_markdown_skeleton(project: Path) -> None:
    result = scaffold_triage_inbox(project)
    md = project / ".shipwright" / "agent_docs" / "triage_inbox.md"
    assert md.exists()
    content = md.read_text(encoding="utf-8")
    assert "# Triage Inbox" in content
    assert "No triage items pending" in content
    assert result["results"]["markdown"]["action"] == "created"


def test_preserves_existing_markdown_on_rerun(project: Path) -> None:
    """Operator may have annotated the empty file; don't clobber."""
    md = project / ".shipwright" / "agent_docs" / "triage_inbox.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text("# Triage Inbox\n\nOperator notes here.\n", encoding="utf-8")

    result = scaffold_triage_inbox(project)
    assert md.read_text(encoding="utf-8") == "# Triage Inbox\n\nOperator notes here.\n"
    assert result["results"]["markdown"]["action"] == "preserved"


# --- .gitignore handling ------------------------------------------------

def test_creates_gitignore_when_absent(project: Path) -> None:
    """No .gitignore at all → scaffolder creates one with both lines."""
    gi = project / ".gitignore"
    assert not gi.exists()
    result = scaffold_triage_inbox(project)
    assert gi.exists()
    content = gi.read_text(encoding="utf-8")
    for line in GITIGNORE_LINES:
        assert line in content
    assert result["results"]["gitignore"]["action"] == "created"
    assert set(result["results"]["gitignore"]["added"]) == set(GITIGNORE_LINES)


def test_appends_to_existing_gitignore(project: Path) -> None:
    """Existing .gitignore without the lines → append both."""
    gi = project / ".gitignore"
    gi.write_text("node_modules/\n.env\n", encoding="utf-8")
    result = scaffold_triage_inbox(project)
    content = gi.read_text(encoding="utf-8")
    assert "node_modules/" in content  # preserved
    assert ".env" in content
    for line in GITIGNORE_LINES:
        assert line in content
    assert result["results"]["gitignore"]["action"] == "appended"


def test_skips_already_present_lines(project: Path) -> None:
    """Both lines already in .gitignore → no-op."""
    gi = project / ".gitignore"
    existing = "node_modules/\n" + "\n".join(GITIGNORE_LINES) + "\n"
    gi.write_text(existing, encoding="utf-8")

    result = scaffold_triage_inbox(project)
    assert gi.read_text(encoding="utf-8") == existing
    assert result["results"]["gitignore"]["action"] == "already-present"
    assert result["results"]["gitignore"]["added"] == []


def test_partial_gitignore_appends_only_missing(project: Path) -> None:
    """Only .jsonl present, .lock missing → append .lock only."""
    gi = project / ".gitignore"
    gi.write_text(GITIGNORE_LINES[0] + "\n", encoding="utf-8")
    result = scaffold_triage_inbox(project)
    content = gi.read_text(encoding="utf-8")
    assert GITIGNORE_LINES[0] in content
    assert GITIGNORE_LINES[1] in content
    assert GITIGNORE_LINES[1] in result["results"]["gitignore"]["added"]
    assert GITIGNORE_LINES[0] not in result["results"]["gitignore"]["added"]


# --- Full idempotency ---------------------------------------------------

def test_full_idempotency(project: Path) -> None:
    """Two consecutive invocations produce the same final state."""
    scaffold_triage_inbox(project)
    state1_triage = (project / ".shipwright" / "triage.jsonl").read_text(encoding="utf-8")
    state1_md = (project / ".shipwright" / "agent_docs" / "triage_inbox.md").read_text(encoding="utf-8")
    state1_gi = (project / ".gitignore").read_text(encoding="utf-8")

    scaffold_triage_inbox(project)
    state2_triage = (project / ".shipwright" / "triage.jsonl").read_text(encoding="utf-8")
    state2_md = (project / ".shipwright" / "agent_docs" / "triage_inbox.md").read_text(encoding="utf-8")
    state2_gi = (project / ".gitignore").read_text(encoding="utf-8")

    assert state1_triage == state2_triage
    assert state1_md == state2_md
    assert state1_gi == state2_gi


# --- CLI smoke ----------------------------------------------------------

def test_cli_runs_and_produces_files(project: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCAFFOLDER), "--project-root", str(project)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, (
        f"scaffolder CLI exit {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert (project / ".shipwright" / "triage.jsonl").exists()
    assert (project / ".shipwright" / "agent_docs" / "triage_inbox.md").exists()
    assert (project / ".gitignore").exists()


def test_cli_json_output(project: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCAFFOLDER), "--project-root", str(project), "--json"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["wrote"] is True
    assert "jsonl" in data["results"]
    assert "markdown" in data["results"]
    assert "gitignore" in data["results"]
