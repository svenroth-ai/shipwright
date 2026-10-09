"""A completed reviewer row recorded without its reply says so: findings_count 0 is not "clean"."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _review_cli_harness import RUN_ID, make_project, run_tool  # noqa: E402

REPLY = {"section": "s", "review": [{"severity": "low", "category": "style",
                                      "finding": "rename x", "suggestion": "y"}]}


@pytest.mark.covers("FR-01.11/AC07")
def test_a_reply_handed_over_records_its_finding_and_no_warning(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    reply = project / ".shipwright" / "planning" / "iterate" / RUN_ID / "code_review_reply.json"
    reply.parent.mkdir(parents=True, exist_ok=True)
    reply.write_text(json.dumps(REPLY), encoding="utf-8")
    rc, out = run_tool(project, "record", "--review-type", "code", "--status", "completed",
                       "--from", "code-reviewer", "--payload-file", str(reply))
    assert rc == 0, out
    assert json.loads(out)["findings_count"] == 1
    assert "warning" not in json.loads(out)


@pytest.mark.covers("FR-01.11/AC07")
def test_recorded_by_alone_warns_that_findings_were_not_read(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    rc, out = run_tool(project, "record", "--review-type", "code", "--status", "completed",
                       "--recorded-by", "code-reviewer")
    assert rc == 0, out
    result, _ = json.JSONDecoder().raw_decode(out[out.index("{"):])  #
    assert result["findings_count"] == 0
    assert "--from code-reviewer --payload-file" in result["warning"]


@pytest.mark.covers("FR-01.11/AC07")
def test_a_payload_without_from_is_warned_as_ignored(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    reply = project / ".shipwright" / "planning" / "iterate" / RUN_ID / "code_review_reply.json"
    reply.parent.mkdir(parents=True, exist_ok=True)
    reply.write_text(json.dumps(REPLY), encoding="utf-8")
    rc, out = run_tool(project, "record", "--review-type", "code", "--status", "completed",
                       "--payload-file", str(reply))
    assert rc == 0, out
    result, _ = json.JSONDecoder().raw_decode(out[out.index("{"):])  # run_tool merges stderr into out
    assert result["findings_count"] == 0 and "NOT read" in result["warning"]


@pytest.mark.covers("FR-01.11/AC07")
def test_a_native_adapter_without_a_payload_cannot_silently_record_zero(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    rc, out = run_tool(project, "record", "--review-type", "code", "--status", "completed",
                       "--from", "code-reviewer")
    assert rc != 0 and "requires --payload-file" in out
