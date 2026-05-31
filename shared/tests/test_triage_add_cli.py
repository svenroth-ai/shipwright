"""Tests for shared/scripts/tools/triage_add.py — manual triage card creation.

AC-1 of iterate-2026-05-21-empirical-followups. Operators stamp FRs onto
new triage cards via this CLI; the existing aggregator + RTM consumer
then render `FAIL → [trg-XXX]` deep-links automatically (the deep-link
infrastructure was empirically verified in V-3 of the campaign).

Covers:
- Happy path: valid args → card created with frId populated
- --fr-id regex rejection (invalid shape → exit 1, JSON error)
- --fr-id optional (omitted → card with frId=None)
- --fr-id empty string treated as "missing" (rejected)
- title/severity/kind validation delegated to triage.append_triage_item
- JSON contract on both success and failure (stdout)
- Markdown-injection safety: title with pipes/brackets/newlines is
  preserved on the wire but downstream escape_cell handles rendering
- Schema shape parity vs hand-crafted reference item (only `frId` differs)
- subprocess invocation path (`uv run shared/scripts/tools/triage_add.py ...`)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Wire up shared/scripts so triage_add can be imported as a module.
_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from tools import triage_add  # noqa: E402
from triage import read_all_items  # noqa: E402


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_fr_id_regex_accepts_canonical_shape():
    """Canonical FR shape `FR-NN.NN` passes regex."""
    assert triage_add.FR_ID_RE.match("FR-01.01")
    assert triage_add.FR_ID_RE.match("FR-12.34")
    assert triage_add.FR_ID_RE.match("FR-99.99")


def test_fr_id_regex_rejects_malformed():
    """Non-canonical shapes are rejected.

    Note: digit count is NOT enforced — the spec says "format-only
    validation", so `FR-1.1` and `FR-001.01` ARE syntactically valid
    even if convention is two-digit segments. Cross-FR existence
    against spec.md is the canonical way to catch non-existent IDs,
    intentionally deferred (see iterate spec Out-of-Scope).
    """
    bad = [
        "FR-01.01.01",       # extra segment
        "FR-01_01",          # underscore separator
        "FR-01,01",          # comma separator
        "fr-01.01",          # lowercase prefix
        "ABC-01.01",         # wrong prefix
        "FR01.01",           # missing dash
        "01.01",             # missing prefix
        " FR-01.01",         # leading whitespace
        "FR-01.01 ",         # trailing whitespace
        "FR-01.",            # missing trailing digit
        "FR-.01",            # missing leading digit
        "",                  # empty string
    ]
    for value in bad:
        assert not triage_add.FR_ID_RE.match(value), f"unexpectedly matched: {value!r}"


# ---------------------------------------------------------------------------
# CLI happy path
# ---------------------------------------------------------------------------


def test_main_creates_card_with_fr_id(tmp_path: Path, capsys: pytest.CaptureFixture):
    """Happy path: --fr-id FR-01.01 → card created with frId populated."""
    project_root = tmp_path
    (project_root / ".shipwright").mkdir()

    exit_code = triage_add.main([
        "--project-root", str(project_root),
        "--title", "Manual triage card for FR-01.01",
        "--detail", "Operator-stamped via triage_add",
        "--severity", "high",
        "--kind", "bug",
        "--source", "manual",
        "--fr-id", "FR-01.01",
    ])

    assert exit_code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["success"] is True
    assert payload["id"].startswith("trg-")
    assert payload["frId"] == "FR-01.01"
    # Operator-information line about format-only validation per OpenAI #12.
    assert payload.get("note", "").startswith("--fr-id format-validated")

    # Round-trip: card lives in triage.jsonl with frId preserved.
    items = read_all_items(project_root)
    matching = [i for i in items if i["id"] == payload["id"]]
    assert len(matching) == 1
    assert matching[0]["frId"] == "FR-01.01"
    assert matching[0]["title"] == "Manual triage card for FR-01.01"
    assert matching[0]["severity"] == "high"
    assert matching[0]["kind"] == "bug"
    assert matching[0]["source"] == "manual"
    assert matching[0]["status"] == "triage"


def test_main_detail_is_optional(tmp_path: Path, capsys: pytest.CaptureFixture):
    """--detail is optional and defaults to empty string.

    Per code-review finding #1 (OpenAI): AC-1 lists `--title --severity
    --kind --source --fr-id` as the canonical surface; --detail rounds
    out the card when context is available but the CLI must accept the
    minimal AC-1 form.
    """
    project_root = tmp_path
    (project_root / ".shipwright").mkdir()

    exit_code = triage_add.main([
        "--project-root", str(project_root),
        "--title", "Minimal AC-1 surface",
        "--severity", "high",
        "--kind", "bug",
        "--source", "manual",
        "--fr-id", "FR-01.01",
        # No --detail provided.
    ])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    items = read_all_items(project_root)
    assert items[0]["detail"] == ""


def test_main_without_fr_id_creates_card_with_null_fr(tmp_path: Path, capsys: pytest.CaptureFixture):
    """--fr-id is optional; omitting it produces a card with frId=None."""
    project_root = tmp_path
    (project_root / ".shipwright").mkdir()

    exit_code = triage_add.main([
        "--project-root", str(project_root),
        "--title", "Generic card without FR stamp",
        "--detail", "no fr_id provided",
        "--severity", "low",
        "--kind", "improvement",
        "--source", "manual",
    ])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert payload["frId"] is None
    # No format-only warning when --fr-id was not provided.
    assert "note" not in payload or "fr-id" not in payload.get("note", "").lower()

    items = read_all_items(project_root)
    assert items[0]["frId"] is None


# ---------------------------------------------------------------------------
# CLI validation failures
# ---------------------------------------------------------------------------


def test_main_rejects_malformed_fr_id(tmp_path: Path, capsys: pytest.CaptureFixture):
    """--fr-id 'foo' (not matching ^FR-\\d+\\.\\d+$) → exit 1, JSON error."""
    project_root = tmp_path
    (project_root / ".shipwright").mkdir()

    exit_code = triage_add.main([
        "--project-root", str(project_root),
        "--title", "Should not be written",
        "--detail", "...",
        "--severity", "high",
        "--kind", "bug",
        "--source", "manual",
        "--fr-id", "not-an-fr",
    ])

    assert exit_code == 1
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["success"] is False
    assert payload["error"] == "invalid_fr_id"
    assert "FR-NN.NN" in payload["detail"] or "^FR-" in payload["detail"]

    # Nothing was written.
    items = read_all_items(project_root)
    assert items == []


def test_main_rejects_empty_fr_id(tmp_path: Path, capsys: pytest.CaptureFixture):
    """--fr-id '' is treated as malformed (not as missing)."""
    project_root = tmp_path
    (project_root / ".shipwright").mkdir()

    exit_code = triage_add.main([
        "--project-root", str(project_root),
        "--title", "Should not be written",
        "--detail", "...",
        "--severity", "high",
        "--kind", "bug",
        "--source", "manual",
        "--fr-id", "",
    ])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert payload["error"] == "invalid_fr_id"


def test_main_rejects_whitespace_only_fr_id(tmp_path: Path, capsys: pytest.CaptureFixture):
    """--fr-id with only whitespace → invalid (the regex anchors reject it)."""
    project_root = tmp_path
    (project_root / ".shipwright").mkdir()

    exit_code = triage_add.main([
        "--project-root", str(project_root),
        "--title", "Should not be written",
        "--detail", "...",
        "--severity", "high",
        "--kind", "bug",
        "--source", "manual",
        "--fr-id", "  ",
    ])

    assert exit_code == 1


def test_main_propagates_severity_validation_error(tmp_path: Path, capsys: pytest.CaptureFixture):
    """Invalid --severity → exit 1, error from triage.append_triage_item.

    Validates the OpenAI #5 requirement: reuse existing triage validation,
    don't reinvent it.
    """
    project_root = tmp_path
    (project_root / ".shipwright").mkdir()

    exit_code = triage_add.main([
        "--project-root", str(project_root),
        "--title", "bad severity test",
        "--detail", "...",
        "--severity", "catastrophic",  # not in SEVERITIES
        "--kind", "bug",
        "--source", "manual",
    ])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert payload["error"] == "invalid_input"
    assert "severity" in payload["detail"].lower()


def test_main_propagates_kind_validation_error(tmp_path: Path, capsys: pytest.CaptureFixture):
    """Invalid --kind → exit 1."""
    project_root = tmp_path
    (project_root / ".shipwright").mkdir()

    exit_code = triage_add.main([
        "--project-root", str(project_root),
        "--title", "bad kind test",
        "--detail", "...",
        "--severity", "high",
        "--kind", "catastrophe",  # not in KINDS
        "--source", "manual",
    ])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "invalid_input"
    assert "kind" in payload["detail"].lower()


def test_main_rejects_blank_title(tmp_path: Path, capsys: pytest.CaptureFixture):
    """Whitespace-only title → exit 1."""
    project_root = tmp_path
    (project_root / ".shipwright").mkdir()

    exit_code = triage_add.main([
        "--project-root", str(project_root),
        "--title", "   ",
        "--detail", "...",
        "--severity", "high",
        "--kind", "bug",
        "--source", "manual",
    ])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "invalid_input"


# ---------------------------------------------------------------------------
# Markdown-injection safety (OpenAI #8)
# ---------------------------------------------------------------------------


def test_main_preserves_pipes_and_brackets_in_title(tmp_path: Path, capsys: pytest.CaptureFixture):
    """Title with markdown-sensitive chars stored verbatim on wire.

    Per OpenAI #8: producers don't sanitize at write time. Downstream
    `markdown_table.escape_cell` handles pipes/newlines when rendering
    the inbox/RTM. Verify the wire shape is preserved so consumers see
    exactly what the operator typed.
    """
    project_root = tmp_path
    (project_root / ".shipwright").mkdir()

    nasty = "FR-01.01 | [link](evil) \nNewline injection"
    exit_code = triage_add.main([
        "--project-root", str(project_root),
        "--title", nasty,
        "--detail", "...",
        "--severity", "high",
        "--kind", "bug",
        "--source", "manual",
    ])

    assert exit_code == 0
    items = read_all_items(project_root)
    # Wire format preserves verbatim — escaping is the renderer's job.
    assert items[0]["title"] == nasty


# ---------------------------------------------------------------------------
# Schema-parity contract (OpenAI #10)
# ---------------------------------------------------------------------------


def test_schema_parity_only_fr_id_differs(tmp_path: Path, capsys: pytest.CaptureFixture):
    """CLI-produced item shape matches a hand-crafted reference; only `frId` differs.

    Locks the contract so a future refactor of triage_add can't quietly
    change wire keys / casing. Per code-review finding #3 (OpenAI): also
    explicitly assert the CLI stdout payload shape (`success`, `id`,
    `frId` camelCase keys) and the persisted JSONL shape, not just a
    subset of common fields.
    """
    project_root = tmp_path
    (project_root / ".shipwright").mkdir()

    # Hand-craft via the underlying API (no frId).
    from triage import append_triage_item
    ref_id = append_triage_item(
        project_root,
        source="manual", severity="high", kind="bug",
        title="ref via API", detail="...",
    )

    # Capture CLI stdout for shape assertions.
    capsys.readouterr()  # drop any prior capture
    exit_code = triage_add.main([
        "--project-root", str(project_root),
        "--title", "via CLI",
        "--detail", "...",
        "--severity", "high",
        "--kind", "bug",
        "--source", "manual",
        "--fr-id", "FR-01.01",
    ])
    stdout = capsys.readouterr().out
    assert exit_code == 0

    # ----- Stdout contract (code-review finding #3) -----
    cli_payload = json.loads(stdout)
    assert cli_payload["success"] is True
    assert isinstance(cli_payload["id"], str) and cli_payload["id"].startswith("trg-")
    # `frId` MUST be in camelCase on stdout (matches wire format).
    assert "frId" in cli_payload
    assert cli_payload["frId"] == "FR-01.01"
    # snake_case `fr_id` MUST NOT leak into the public JSON contract.
    assert "fr_id" not in cli_payload

    # ----- Persisted JSONL shape (code-review finding #3) -----
    items = read_all_items(project_root)
    by_id = {i["id"]: i for i in items}
    ref = by_id[ref_id]
    cli = by_id[cli_payload["id"]]

    # CamelCase wire keys are the contract.
    required_wire_keys = {
        "id", "source", "severity", "kind", "title", "detail",
        "evidencePath", "runId", "commit", "dedupKey", "launchPayload",
        "frId", "suiteId", "eventId", "status",
        "suggestedPriority", "suggestedDomain", "ts", "originalTs",
    }
    assert required_wire_keys.issubset(cli.keys()), (
        f"missing keys: {required_wire_keys - cli.keys()}"
    )
    # snake_case alias must not leak.
    assert "fr_id" not in cli

    # Schema parity: both items share identical key sets.
    assert set(ref.keys()) == set(cli.keys())

    # Differing keys: id, ts, originalTs, title, frId. Everything else matches.
    common = {"source", "severity", "kind", "detail", "status",
              "evidencePath", "runId", "commit", "dedupKey",
              "launchPayload", "suiteId", "eventId",
              "suggestedPriority", "suggestedDomain"}
    for key in common:
        assert ref[key] == cli[key], f"key {key!r} differs unexpectedly: {ref[key]!r} vs {cli[key]!r}"

    assert ref["frId"] is None
    assert cli["frId"] == "FR-01.01"


# ---------------------------------------------------------------------------
# Subprocess invocation (OpenAI #6 — packaging path)
# ---------------------------------------------------------------------------


def test_main_invokable_via_uv_run(tmp_path: Path):
    """Smoke-test that `uv run shared/scripts/tools/triage_add.py ...` works.

    Verifies packaging conventions match other tools/ scripts. Skipped in
    CI if `uv` is not present (mirrors existing test_silent_skip pattern).
    """
    import os
    import shutil

    if not shutil.which("uv"):
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail("uv not available in CI — install with astral-sh/setup-uv@v3")
        pytest.skip("uv not available locally")

    project_root = tmp_path
    (project_root / ".shipwright").mkdir()

    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "shared" / "scripts" / "tools" / "triage_add.py"

    result = subprocess.run(
        [
            "uv", "run", "--no-project", str(script),
            "--project-root", str(project_root),
            "--title", "smoke",
            "--detail", "...",
            "--severity", "low",
            "--kind", "improvement",
            "--source", "manual",
            "--fr-id", "FR-01.01",
        ],
        capture_output=True, text=True,
        cwd=str(repo_root),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["frId"] == "FR-01.01"
