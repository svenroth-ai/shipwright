"""U10: the write-time refusal and the loud surface for a review that did not run.

``record_review_pass.py record`` refuses ``--reason-code unavailable`` on an
adapter-backed pass whose failure was not captured, and
``review_unavailable_note.py`` prints the one line the PR body and F12 carry —
and, for an autonomous run, files ONE re-run triage card per run.
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

from _review_cli_harness import RUN_ID, make_project, run_tool  # noqa: E402
from lib.review_unavailable import artifact_paths  # noqa: E402

NOTE = str(_SHARED / "scripts" / "tools" / "review_unavailable_note.py")
FAILED = json.dumps({"review_schema": 2, "success": False, "error": "no provider answered", "mode": "code"})
PLAN_FAILED = FAILED.replace('"code"', '"iterate"')


@pytest.fixture
def project(tmp_path):
    return make_project(tmp_path)


def _unavailable(project: Path, review_type: str = "external_code") -> tuple[int, str]:
    return run_tool(project, "record", "--review-type", review_type,
                    "--status", "not_run", "--reason-code", "unavailable")


def _capture(project: Path, review_type: str, *, raw: str | None = None, err: str | None = None) -> None:
    raw_rel, err_rel = artifact_paths(RUN_ID, review_type)
    for rel, text in ((raw_rel, raw), (err_rel, err)):
        if text is not None:
            (project / rel).parent.mkdir(parents=True, exist_ok=True)
            (project / rel).write_text(text, encoding="utf-8")


def _note(project: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, NOTE, "--project-root", str(project), "--run-id", RUN_ID, *extra],
                          capture_output=True, text=True, encoding="utf-8")


@pytest.mark.covers("FR-01.11")
def test_record_refuses_unavailable_on_an_external_pass_without_a_capture(project):
    code, out = _unavailable(project)
    assert code == 2, out
    assert "no captured adapter error" in json.loads(out)["message"]


@pytest.mark.covers("FR-01.11")
def test_record_accepts_unavailable_once_the_failure_is_captured(project):
    _capture(project, "external_code", raw="", err="error: Failed to spawn: `uv`")
    assert _unavailable(project)[0] == 0


@pytest.mark.covers("FR-01.11")
def test_record_leaves_unavailable_on_an_internal_pass_alone(project):
    assert _unavailable(project, "code")[0] == 0


@pytest.mark.covers("FR-01.11")
def test_note_says_none_when_no_row_is_unavailable(project):
    run_tool(project, "init")
    result = _note(project)
    assert (result.returncode, result.stdout.strip()) == (0, "none")


@pytest.mark.covers("FR-01.11")
def test_note_names_each_unavailable_pass_and_its_capture_path_never_its_content(project):
    leaked = "https://internal.example/provider-route-42"
    _capture(project, "plan", raw=PLAN_FAILED)
    _capture(project, "external_code", raw="", err=f"error reaching {leaked}")
    assert _unavailable(project, "plan")[0] == 0
    assert _unavailable(project)[0] == 0
    line = _note(project).stdout.strip()
    assert line.startswith("2 (plan, external_code) - did NOT run (unavailable)"), line
    assert "external-plan-review-raw.json" in line and "external-code-review-raw.stderr.txt" in line
    assert leaked not in line


@pytest.mark.covers("FR-01.11")
def test_file_triage_files_one_card_per_run_and_finds_it_again(project):
    _capture(project, "external_code", raw=FAILED)
    assert _unavailable(project)[0] == 0
    first, second = _note(project, "--file-triage"), _note(project, "--file-triage")
    assert first.returncode == 0 and second.returncode == 0, first.stdout + first.stderr
    card = first.stdout.strip().rsplit("re-run card ", 1)[1]
    assert second.stdout.strip().endswith(f"re-run card {card}")
    lines = (project / ".shipwright" / "triage.jsonl").read_text(encoding="utf-8").splitlines()
    appends = [json.loads(x) for x in lines if x.strip().startswith("{") and '"append"' in x]
    assert [a["id"] for a in appends] == [card]
    assert appends[0]["source"] == "iterate" and RUN_ID in appends[0]["title"]


@pytest.mark.covers("FR-01.11")
def test_a_card_found_again_but_no_longer_open_carries_its_status(project):
    from triage import mark_status

    _capture(project, "external_code", raw=FAILED)
    assert _unavailable(project)[0] == 0
    card = _note(project, "--file-triage").stdout.strip().rsplit("re-run card ", 1)[1]
    mark_status(project, card, new_status="dismissed", by="operator", reason="re-run elsewhere")
    again = _note(project, "--file-triage")
    assert again.returncode == 0 and again.stdout.strip().endswith(f"re-run card {card} (dismissed)"), again.stdout


@pytest.mark.covers("FR-01.11")
def test_note_warns_about_a_stderr_capture_that_backs_no_unavailable_row(project):
    """F6 stages the whole run dir, so a leftover capture would ship unless someone sees it."""
    run_tool(project, "init")
    _capture(project, "plan", raw="{}", err="warning: slow provider")
    result = _note(project)
    assert (result.returncode, result.stdout.strip()) == (0, "none")
    assert "WARN" in result.stderr and "external-plan-review-raw.stderr.txt" in result.stderr


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("after", ["deleted", "overwritten-with-success"])
def test_note_refuses_and_files_no_card_when_the_capture_no_longer_backs_the_claim(project, after):
    _capture(project, "external_code", raw=FAILED)
    assert _unavailable(project)[0] == 0
    raw = project / artifact_paths(RUN_ID, "external_code")[0]
    if after == "deleted":
        raw.unlink()
    else:
        raw.write_text(json.dumps({"success": True, "degraded": False}), encoding="utf-8")
    result = _note(project, "--file-triage")
    assert result.returncode == 1 and result.stdout.startswith("INVALID"), result.stdout
    assert "no card filed" in result.stdout
    assert not (project / ".shipwright" / "triage.jsonl").exists()


@pytest.mark.covers("FR-01.11")
def test_note_is_invalid_not_none_when_the_record_is_missing(project):
    result = _note(project)
    assert result.returncode == 1 and result.stdout.startswith("INVALID")
