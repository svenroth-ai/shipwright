"""`record_review_pass.py record --transport/--transport-note` — round-trip +
backward-compat, mirroring `test_record_review_pass_model_tier.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _review_cli_harness import RUN_ID, make_project, run_tool  # noqa: E402

_SHARED = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SHARED / "scripts"))

from lib.review_record import record_path  # noqa: E402


def _reviews(project: Path) -> dict:
    return json.loads(record_path(project, RUN_ID).read_text(encoding="utf-8"))["reviews"]


def test_transport_codex_round_trips_into_the_entry(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    rc, out = run_tool(
        project, "record", "--review-type", "code", "--status", "completed",
        "--recorded-by", "code-reviewer", "--transport", "codex",
    )
    assert rc == 0, out
    assert _reviews(project)["code"]["transport"] == "codex"


def test_omitted_transport_leaves_no_stray_key(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    rc, out = run_tool(
        project, "record", "--review-type", "code", "--status", "completed",
        "--recorded-by", "code-reviewer",
    )
    assert rc == 0, out
    assert "transport" not in _reviews(project)["code"]


def test_transport_note_round_trips_with_transport(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    rc, out = run_tool(
        project, "record", "--review-type", "code", "--status", "completed",
        "--recorded-by", "code-reviewer", "--transport", "codex",
        "--transport-note", "mid-run timeout, fell back to inherit",
    )
    assert rc == 0, out
    assert _reviews(project)["code"]["transport_note"] == "mid-run timeout, fell back to inherit"


def test_invalid_transport_value_rejected_at_the_cli(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    rc, out = run_tool(
        project, "record", "--review-type", "code", "--status", "completed",
        "--recorded-by", "code-reviewer", "--transport", "carrier-pigeon",
    )
    assert rc != 0
    assert "transport" in out.lower() or "invalid choice" in out.lower()


def test_transport_note_without_transport_rejected(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    rc, out = run_tool(
        project, "record", "--review-type", "code", "--status", "completed",
        "--recorded-by", "code-reviewer", "--transport-note", "orphaned note",
    )
    assert rc != 0
    assert "transport" in out.lower()


def test_transport_codex_with_model_tier_rejected(tmp_path: Path) -> None:
    """Regression for doubt-reviewer MEDIUM, 2026-09-17: a codex-answered row
    carries no legal Claude tier, so the two together must be rejected rather
    than silently asserting a Claude tier the row was never answered by."""
    project = make_project(tmp_path)
    rc, out = run_tool(
        project, "record", "--review-type", "code", "--status", "completed",
        "--recorded-by", "code-reviewer", "--transport", "codex", "--model-tier", "opus",
    )
    assert rc != 0
    assert "model-tier" in out.lower()
