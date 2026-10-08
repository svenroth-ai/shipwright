"""U10 integration: a campaign runner whose external review could not run, end to end.

The scenario a real autonomous medium run goes through, every piece real: the
adapter's failure envelope lands in the canonical capture file, the runner closes
its rows with ``record_review_pass.py`` (CLI, subprocess), F11's
``check_review_record`` judges the record at medium (the capture rule AND the
code-review floor must compose), ``review_unavailable_note.py --file-triage``
prints the PR/F12 line and files the re-run card, and the triage store reads the
card back. Then the orchestrator's 3f-bis promotion of ``code`` keeps the gate
green while the line still names the external pass.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SHARED / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _review_cli_harness import (  # noqa: E402
    CODE_REVIEWER_REPLY, RUN_ID, RUNNER_REASON_CODES, SELF_REVIEW_REPLY, make_project, payload, run_tool,
)
from lib.review_unavailable import artifact_paths  # noqa: E402
from tools.verifiers.review_record_check import check_review_record  # noqa: E402
from triage import read_all_items  # noqa: E402

NOTE = str(_SHARED / "scripts" / "tools" / "review_unavailable_note.py")
SPEC_PASS = json.dumps({"stage": "spec", "verdict": "PASS", "spec_citations": []})
ENVELOPE = json.dumps({"review_schema": 2, "success": False, "degraded": True, "mode": "code",
                       "degraded_reason": "provider=openrouter but 0/2 reviews succeeded"})


def _ok(result: tuple[int, str]) -> None:
    assert result[0] == 0, result[1]


@pytest.mark.covers("FR-01.11")
def test_campaign_runner_with_an_unavailable_external_review_finishes_loudly(tmp_path):
    project = make_project(tmp_path)  # complexity medium; the entry is re-pointed at a campaign branch
    entry_path = project / ".shipwright" / "agent_docs" / "iterates" / f"{RUN_ID}.json"
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    entry_path.write_text(json.dumps({**entry, "branch": "iterate/campaign-c--U1"}), encoding="utf-8")
    raw = project / artifact_paths(RUN_ID, "external_code")[0]
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(ENVELOPE, encoding="utf-8")  # what `> external-code-review-raw.json` captured

    _ok(run_tool(project, "record", "--review-type", "self", "--status", "completed",
                 "--from", "self-review", "--payload-file",
                 payload(raw.parent, "self-review-payload.json", SELF_REVIEW_REPLY)))
    _ok(run_tool(project, "record", "--review-type", "external_code", "--status", "not_run",
                 "--reason-code", "unavailable"))
    for review_type, code in RUNNER_REASON_CODES.items():
        _ok(run_tool(project, "record", "--review-type", review_type, "--status", "not_run",
                     "--reason-code", code))
    _ok(run_tool(project, "record", "--review-type", "plan", "--status", "not_run",
                 "--reason-code", "missing-keys"))

    runner_view = check_review_record(project, RUN_ID)
    assert runner_view.ok is True, runner_view.detail  # F6-verify: the floor waits for 3f-bis
    assert "did NOT run (unavailable): external_code" in runner_view.detail

    note = subprocess.run([sys.executable, NOTE, "--project-root", str(project), "--run-id", RUN_ID,
                           "--file-triage"], capture_output=True, text=True, encoding="utf-8")
    assert note.returncode == 0, note.stdout + note.stderr
    line = note.stdout.strip()
    assert line.startswith("1 (external_code) - did NOT run (unavailable)")
    card_id = line.rsplit("re-run card ", 1)[1]
    [card] = [i for i in read_all_items(project) if i.get("id") == card_id]
    assert card["status"] == "triage" and RUN_ID in card["title"]

    # 3f-bis: the orchestrator runs Stage 1 + 2 and promotes the rows.
    _ok(run_tool(project, "record", "--review-type", "spec", "--status", "completed",
                 "--from", "spec-reviewer", "--payload-file",
                 payload(raw.parent, "spec_review_reply.json", SPEC_PASS), "--force"))
    _ok(run_tool(project, "record", "--review-type", "code", "--status", "completed",
                 "--from", "code-reviewer", "--payload-file",
                 payload(raw.parent, "code_review_reply.json", CODE_REVIEWER_REPLY), "--force"))
    merged_view = check_review_record(project, RUN_ID)
    assert merged_view.ok is True, merged_view.detail
    assert "did NOT run (unavailable): external_code" in merged_view.detail
