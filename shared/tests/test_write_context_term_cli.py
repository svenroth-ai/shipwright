"""CLI tests for shared/scripts/tools/write_context_term.py's LEGACY
``--term``/``--definition``/``--avoid`` flag path.

**Not the interview-wired invocation** (P4.1 final review — the flag path
these tests exercise is deprecated in favor of ``--payload-file``, since a
value assembled from interview text into a shell-quoted ``--term
'<value>'`` argument breaks out of the quoting the moment it contains a
single quote). These tests cover the flag path for callers that already
hold trusted, non-shell-composed values (this file itself, other scripts) —
never for free text from an interview. The invocation
``plugins/shipwright-project/skills/project/references/interview-protocol.md``
actually tells the agent to use is ``--payload-file``, covered by
``test_write_context_term_payload.py`` (AC2/AC3/AC4 evidence lives there
now). As opposed to ``test_write_context_term.py``, which calls
``upsert_term`` directly.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "shared" / "scripts" / "tools" / "write_context_term.py"


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, encoding="utf-8",
    )


def test_wired_cli_sharpens_a_term_into_context_md(tmp_path):
    proc = _run(
        "--project-root", str(tmp_path),
        "--term", "Order",
        "--definition", "a customer's confirmed purchase of one or more items.",
        "--avoid", '"cart" for a confirmed order — a cart is unconfirmed.',
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "created"

    ctx = tmp_path / "CONTEXT.md"
    content = read(ctx)
    # Matches shared/context-format.md §2's documented shape.
    assert content.startswith("# CONTEXT.md —")
    assert "## Language" in content
    assert "## Relationships" in content
    assert "## Flagged ambiguities" in content
    assert "**Order** — a customer's confirmed purchase of one or more items." in content
    assert '_Avoid_ "cart" for a confirmed order — a cart is unconfirmed.' in content


def test_wired_cli_second_sharpened_term_does_not_corrupt_first(tmp_path):
    first = _run(
        "--project-root", str(tmp_path),
        "--term", "Order",
        "--definition", "a customer's confirmed purchase of one or more items.",
    )
    assert first.returncode == 0, first.stderr

    second = _run(
        "--project-root", str(tmp_path),
        "--term", "Cancellation",
        "--definition", "voiding an Order before it ships.",
    )
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["status"] == "appended"

    content = read(tmp_path / "CONTEXT.md")
    assert content.count("**Order**") == 1
    assert content.count("**Cancellation**") == 1
    assert "a customer's confirmed purchase of one or more items." in content
    assert "voiding an Order before it ships." in content


# ---------------------------------------------------------------------------
# CLI — validation exits loudly rather than silently doing the wrong thing
# ---------------------------------------------------------------------------

def test_cli_rejects_missing_project_root(tmp_path):
    missing = tmp_path / "does-not-exist"
    proc = _run(
        "--project-root", str(missing),
        "--term", "Order",
        "--definition", "x",
    )
    assert proc.returncode == 1
    assert "does not exist" in proc.stderr
    assert not missing.exists()


def test_cli_rejects_blank_term(tmp_path):
    proc = _run(
        "--project-root", str(tmp_path),
        "--term", "   ",
        "--definition", "x",
    )
    assert proc.returncode == 1
    assert "blank" in proc.stderr
    assert not (tmp_path / "CONTEXT.md").exists()


def test_cli_rejects_context_path_with_missing_parent(tmp_path):
    bogus = tmp_path / "does-not-exist" / "CONTEXT.md"
    proc = _run(
        "--project-root", str(tmp_path),
        "--context-path", str(bogus),
        "--term", "Order",
        "--definition", "x",
    )
    assert proc.returncode == 1
    assert "does not exist" in proc.stderr
    assert not bogus.parent.exists()
