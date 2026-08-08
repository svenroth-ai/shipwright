"""`record_review_pass.py record --model-tier` — round-trip + backward-compat.

Backward-compat matters here specifically: every existing caller of `record`
omits `--model-tier`, and the resulting entry must be indistinguishable from
today's (no stray `"model_tier": null` key) so old readers using `.get()`
see plain absence, not a new field they don't know about.
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


def test_model_tier_round_trips_into_the_entry(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    rc, out = run_tool(
        project, "record", "--review-type", "code", "--status", "completed",
        "--recorded-by", "code-reviewer", "--model-tier", "opus",
    )
    assert rc == 0, out
    assert _reviews(project)["code"]["model_tier"] == "opus"


def test_omitted_model_tier_leaves_no_stray_key(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    rc, out = run_tool(
        project, "record", "--review-type", "code", "--status", "completed",
        "--recorded-by", "code-reviewer",
    )
    assert rc == 0, out
    assert "model_tier" not in _reviews(project)["code"]


def test_inherit_is_a_recordable_literal(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    rc, out = run_tool(
        project, "record", "--review-type", "code", "--status", "completed",
        "--recorded-by", "code-reviewer", "--model-tier", "inherit",
    )
    assert rc == 0, out
    assert _reviews(project)["code"]["model_tier"] == "inherit"


def test_invalid_model_tier_rejected_at_the_cli(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    rc, out = run_tool(
        project, "record", "--review-type", "code", "--status", "completed",
        "--recorded-by", "code-reviewer", "--model-tier", "gpt5",
    )
    assert rc != 0
    assert "model-tier" in out.lower() or "invalid choice" in out.lower()
