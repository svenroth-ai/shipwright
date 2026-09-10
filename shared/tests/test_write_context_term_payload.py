"""``--payload-file`` tests for write_context_term.py (P4.1 final review,
GitHub required-check finding): the sanctioned way to pass free text from an
interview, so that a value containing a single quote (ordinary English —
"the customer's cart") never has to be substituted into a shell-quoted CLI
argument at all. The payload file is written directly to disk here (Path
.write_text), mirroring how the agent uses the Write tool rather than a
shell command — the point of this feature is that no shell ever sees the
free text.
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


def _write_payload(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_payload_file_sharpens_a_term_containing_a_single_quote(tmp_path):
    """The regression this feature exists for: a term/definition/avoid with
    an embedded single quote would break a hand-assembled `--term '<value>'`
    shell string. Via --payload-file it round-trips exactly."""
    payload_path = tmp_path / "payload.json"
    _write_payload(payload_path, {
        "term": "Customer's Cart",
        "definition": "it's the pre-checkout collection of a customer's chosen items.",
        "avoid": "\"basket\" — that's the warehouse term, not the customer-facing one.",
    })
    proc = _run(
        "--project-root", str(tmp_path),
        "--payload-file", str(payload_path),
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["status"] == "created"
    assert result["term"] == "Customer's Cart"

    content = read(tmp_path / "CONTEXT.md")
    assert "**Customer's Cart** — it's the pre-checkout collection of a " \
        "customer's chosen items." in content
    assert '_Avoid_ "basket" — that\'s the warehouse term, not the ' \
        "customer-facing one." in content


def test_payload_file_project_name_and_summary_with_apostrophes(tmp_path):
    payload_path = tmp_path / "payload.json"
    _write_payload(payload_path, {
        "term": "Order",
        "definition": "a confirmed purchase.",
        "project_name": "Bob's Bakery",
        "summary": "it's a small bakery's ordering system.",
    })
    proc = _run("--project-root", str(tmp_path), "--payload-file", str(payload_path))
    assert proc.returncode == 0, proc.stderr
    content = read(tmp_path / "CONTEXT.md")
    assert "# CONTEXT.md — Bob's Bakery domain glossary" in content
    assert "it's a small bakery's ordering system." in content


def test_payload_file_clear_avoid_round_trips(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    _write_payload(tmp_path / "p1.json", {
        "term": "Order", "definition": "v1", "avoid": "cart.",
    })
    first = _run("--project-root", str(tmp_path), "--payload-file", str(tmp_path / "p1.json"))
    assert first.returncode == 0, first.stderr

    _write_payload(tmp_path / "p2.json", {
        "term": "Order", "definition": "v2", "clear_avoid": True,
    })
    second = _run("--project-root", str(tmp_path), "--payload-file", str(tmp_path / "p2.json"))
    assert second.returncode == 0, second.stderr
    content = read(ctx)
    assert "**Order** — v2" in content
    assert "_Avoid_" not in content


def test_payload_file_missing_required_fields_is_rejected(tmp_path):
    payload_path = tmp_path / "payload.json"
    _write_payload(payload_path, {"term": "Order"})  # no definition
    proc = _run("--project-root", str(tmp_path), "--payload-file", str(payload_path))
    assert proc.returncode == 1
    assert "'term' and 'definition'" in proc.stderr
    assert not (tmp_path / "CONTEXT.md").exists()


def test_payload_file_invalid_json_is_rejected(tmp_path):
    payload_path = tmp_path / "payload.json"
    payload_path.write_text("{not valid json", encoding="utf-8")
    proc = _run("--project-root", str(tmp_path), "--payload-file", str(payload_path))
    assert proc.returncode == 1
    assert "not valid JSON" in proc.stderr


def test_payload_file_non_object_json_is_rejected(tmp_path):
    payload_path = tmp_path / "payload.json"
    payload_path.write_text('["Order", "a confirmed purchase."]', encoding="utf-8")
    proc = _run("--project-root", str(tmp_path), "--payload-file", str(payload_path))
    assert proc.returncode == 1
    assert "JSON object" in proc.stderr


def test_payload_file_non_string_field_is_rejected(tmp_path):
    payload_path = tmp_path / "payload.json"
    _write_payload(payload_path, {"term": "Order", "definition": 12345})
    proc = _run("--project-root", str(tmp_path), "--payload-file", str(payload_path))
    assert proc.returncode == 1
    assert "must be strings" in proc.stderr


def test_payload_file_missing_path_is_rejected(tmp_path):
    proc = _run(
        "--project-root", str(tmp_path),
        "--payload-file", str(tmp_path / "does-not-exist.json"),
    )
    assert proc.returncode == 1
    assert "cannot read --payload-file" in proc.stderr


def test_payload_file_combined_with_term_flag_is_rejected(tmp_path):
    payload_path = tmp_path / "payload.json"
    _write_payload(payload_path, {"term": "Order", "definition": "a confirmed purchase."})
    proc = _run(
        "--project-root", str(tmp_path),
        "--payload-file", str(payload_path),
        "--term", "Cancellation",
    )
    assert proc.returncode == 1
    assert "cannot be combined" in proc.stderr
    assert not (tmp_path / "CONTEXT.md").exists()
