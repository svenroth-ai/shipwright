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


# --- tracking flip: triage.jsonl is the tracked SSoT (campaign C1) ------

def test_jsonl_is_no_longer_a_managed_ignore_line(project: Path) -> None:
    """triage.jsonl is tracked now — only the .lock + GC .bak are scaffolder ignores."""
    assert ".shipwright/triage.jsonl" not in GITIGNORE_LINES  # the tracked SSoT
    assert ".shipwright/triage.jsonl.lock" in GITIGNORE_LINES
    assert ".shipwright/triage.jsonl.bak" in GITIGNORE_LINES


def test_self_heals_stale_bare_jsonl_ignore(project: Path) -> None:
    """A pre-tracking bare ``.shipwright/triage.jsonl`` ignore (appended after
    the managed block) is stripped so it can't override the negation.
    """
    gi = project / ".gitignore"
    gi.write_text(
        "node_modules/\n"
        "# === BEGIN Shipwright canonical .shipwright artifact-ignore (managed) ===\n"
        "/.shipwright/*\n"
        "!/.shipwright/triage.jsonl\n"
        "# === END Shipwright canonical .shipwright artifact-ignore (managed) ===\n"
        "\n# Triage Inbox (shipwright)\n"
        ".shipwright/triage.jsonl\n"
        ".shipwright/triage.jsonl.lock\n",
        encoding="utf-8",
    )
    result = scaffold_triage_inbox(project)
    lines = [L.strip() for L in gi.read_text(encoding="utf-8").splitlines()]
    # Stale bare line gone; negation + lock survive.
    assert ".shipwright/triage.jsonl" not in lines
    assert "!/.shipwright/triage.jsonl" in lines
    assert ".shipwright/triage.jsonl.lock" in lines
    assert ".shipwright/triage.jsonl" in result["results"]["gitignore"]["healed"]


def test_self_heal_strips_slash_prefixed_variant(project: Path) -> None:
    gi = project / ".gitignore"
    gi.write_text("/.shipwright/triage.jsonl\n.shipwright/triage.jsonl.lock\n",
                  encoding="utf-8")
    scaffold_triage_inbox(project)
    lines = [L.strip() for L in gi.read_text(encoding="utf-8").splitlines()]
    assert "/.shipwright/triage.jsonl" not in lines
    assert ".shipwright/triage.jsonl.lock" in lines


def test_self_heal_never_strips_the_negation(project: Path) -> None:
    """The ``!`` negation must survive a (re-)scaffold untouched."""
    gi = project / ".gitignore"
    gi.write_text("!/.shipwright/triage.jsonl\n.shipwright/triage.jsonl.lock\n",
                  encoding="utf-8")
    result = scaffold_triage_inbox(project)
    lines = [L.strip() for L in gi.read_text(encoding="utf-8").splitlines()]
    assert "!/.shipwright/triage.jsonl" in lines
    assert result["results"]["gitignore"]["healed"] == []  # negation isn't "stale"


def test_canonical_negation_tracks_jsonl_but_ignores_lock_and_bak(project: Path) -> None:
    """End-to-end on the REAL SSoT template (via gitignore_canon): the managed
    block tracks triage.jsonl while .lock + .bak stay ignored. Pins the
    load-bearing gitignore behavior so a future template edit can't regress it.
    """
    from lib.gitignore_canon import merge_canonical_block

    merge_canonical_block(project)  # writes the canonical block from the SSoT template
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    (project / ".shipwright").mkdir(exist_ok=True)
    for name in ("triage.jsonl", "triage.jsonl.lock", "triage.jsonl.bak"):
        (project / ".shipwright" / name).write_text("", encoding="utf-8")

    def _ignored(rel: str) -> bool:
        return subprocess.run(
            ["git", "check-ignore", "-q", rel], cwd=project
        ).returncode == 0

    assert not _ignored(".shipwright/triage.jsonl"), "triage.jsonl must be TRACKED"
    assert _ignored(".shipwright/triage.jsonl.lock"), ".lock must stay ignored"
    assert _ignored(".shipwright/triage.jsonl.bak"), ".bak must stay ignored"


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
