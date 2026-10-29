"""Entry-channel guards of the grill-trace gate (grill_trace_entry_channel.py): a bypassed
interview, a missing transcript and a missing human sign-off all fail, for every channel."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.verifiers.common import Severity
from tools.verify_grill_trace_completeness import run_all_checks


def _payload(**overrides) -> dict:
    payload = {
        "requirement_key": "user-login", "requirement_text": "Users sign in.", "surface": "project",
        "evidence": ["turn 3"], "fit_criterion": "a valid pair returns a token",
        "dimensions": {d: "answered" for d in (
            "outcome", "purpose", "boundaries", "failure", "glossary", "rationale", "out_of_scope")},
        "glossary_delta": [], "confirmed_by": "user confirmed in turn 5", "terms_used": [],
    }
    payload.update(overrides)
    return payload


def _write_trace(planning_dir: Path, payload: dict) -> Path:
    directory = planning_dir / "grill-traces"
    directory.mkdir(parents=True, exist_ok=True)
    (planning_dir / "shipwright_project_interview.md").write_text("transcript", encoding="utf-8")
    path = directory / f"{payload['requirement_key']}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _planning(tmp_path: Path) -> Path:
    planning_dir = tmp_path / ".shipwright" / "planning"
    planning_dir.mkdir(parents=True)
    return planning_dir


def _spec_with_fr(planning_dir: Path) -> None:
    spec = planning_dir / "01-auth" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(
        "| ID | Area | Name | Priority | Description | Basis | Layers |\n"
        "|---|---|---|---|---|---|---|\n"
        "| FR-01.01 | Auth | User login | Must | ... | interview | unit |\n",
        encoding="utf-8",
    )


@pytest.mark.covers("FR-01.16/AC01")
def test_bypassed_interview_fails_once_requirements_exist(tmp_path):
    """No transcript, no traces, but the spec already has FR rows: the interview was bypassed."""
    planning_dir = _planning(tmp_path)
    _spec_with_fr(planning_dir)

    by_name = {r.name: r for r in run_all_checks(tmp_path, planning_dir=planning_dir)}

    assert by_name["grill_trace_coverage"].ok is False
    assert by_name["grill_trace_coverage"].severity == Severity.ERROR.value


@pytest.mark.covers("FR-01.16/AC01")
def test_bypassed_interview_fails_for_a_complete_project_without_a_spec(tmp_path):
    planning_dir = _planning(tmp_path)
    (tmp_path / "shipwright_project_config.json").write_text('{"status": "complete"}', encoding="utf-8")

    by_name = {r.name: r for r in run_all_checks(tmp_path, planning_dir=planning_dir)}

    assert by_name["grill_trace_coverage"].ok is False


@pytest.mark.covers("FR-01.16/AC01")
def test_nothing_recorded_yet_still_skips_before_any_requirement_exists(tmp_path):
    planning_dir = _planning(tmp_path)

    by_name = {r.name: r for r in run_all_checks(tmp_path, planning_dir=planning_dir)}

    assert by_name["grill_trace_coverage"].is_skipped


@pytest.mark.covers("FR-01.16/AC01")
def test_traces_without_a_transcript_fail(tmp_path):
    """Hand-written traces with no interview transcript or brief-mode pointer behind them."""
    planning_dir = tmp_path / ".shipwright" / "planning"
    _write_trace(planning_dir, _payload())
    (planning_dir / "shipwright_project_interview.md").unlink()

    by_name = {r.name: r for r in run_all_checks(tmp_path, planning_dir=planning_dir)}

    assert by_name["interview_transcript_present"].ok is False
    assert by_name["interview_transcript_present"].severity == Severity.ERROR.value


@pytest.mark.covers("FR-01.16/AC01")
def test_brief_mode_pointer_without_a_recorded_brief_dir_fails(tmp_path):
    planning_dir = tmp_path / ".shipwright" / "planning"
    _write_trace(planning_dir, _payload(confirmed_by="brief:brief/brief.md"))
    (planning_dir / "shipwright_project_interview.md").write_text(
        "Project brief mode: no interview was held.", encoding="utf-8")

    by_name = {r.name: r for r in run_all_checks(tmp_path, planning_dir=planning_dir)}

    assert by_name["human_signoff"].ok is False
    assert "brief_dir" in by_name["human_signoff"].detail


@pytest.mark.covers("FR-01.16/AC01")
def test_brief_mode_with_a_recorded_brief_dir_passes_signoff(tmp_path):
    planning_dir = tmp_path / ".shipwright" / "planning"
    _write_trace(planning_dir, _payload(confirmed_by="brief:brief/brief.md"))
    (planning_dir / "shipwright_project_interview.md").write_text(
        "Project brief mode: no interview was held.", encoding="utf-8")
    (tmp_path / "shipwright_run_config.json").write_text('{"brief_dir": "brief"}', encoding="utf-8")

    by_name = {r.name: r for r in run_all_checks(tmp_path, planning_dir=planning_dir)}

    assert by_name["human_signoff"].ok is True


@pytest.mark.covers("FR-01.16/AC01")
def test_self_attested_confirmation_fails(tmp_path):
    planning_dir = tmp_path / ".shipwright" / "planning"
    _write_trace(planning_dir, _payload(confirmed_by="Agent"))

    by_name = {r.name: r for r in run_all_checks(tmp_path, planning_dir=planning_dir)}

    assert by_name["human_signoff"].ok is False


@pytest.mark.covers("FR-01.16/AC01")
def test_legacy_five_column_table_uses_the_name_header():
    from tools.grill_trace_fr_coverage import extract_fr_names
    table = ("| ID | Name | Priority | Description |\n|---|---|---|---|\n"
             "| FR-01.01 | User login | Must | x |\n")
    assert extract_fr_names(table) == {"FR-01.01": "User login"}


@pytest.mark.covers("FR-01.16/AC01")
def test_extension_scope_inherited_fr_rows_only_warn(tmp_path):
    planning_dir = tmp_path / ".shipwright" / "planning"
    _write_trace(planning_dir, _payload())
    _spec_with_fr(planning_dir)
    spec = planning_dir / "01-auth" / "spec.md"
    spec.write_text(spec.read_text(encoding="utf-8")
                    + "| FR-01.02 | Auth | Old feature | Must | ... | adopted | unit |\n", encoding="utf-8")
    (tmp_path / "shipwright_project_config.json").write_text('{"scope": "extension"}', encoding="utf-8")

    by_name = {r.name: r for r in run_all_checks(tmp_path, planning_dir=planning_dir)}

    assert by_name["fr_trace_coverage"].ok is False
    assert by_name["fr_trace_coverage"].severity == Severity.WARNING.value


@pytest.mark.covers("FR-01.16/AC01")
def test_a_real_transcript_mentioning_brief_mode_is_not_a_pointer(tmp_path):
    planning_dir = tmp_path / ".shipwright" / "planning"
    _write_trace(planning_dir, _payload())
    (planning_dir / "shipwright_project_interview.md").write_text(
        "user: should we use project brief mode later?", encoding="utf-8")

    by_name = {r.name: r for r in run_all_checks(tmp_path, planning_dir=planning_dir)}

    assert by_name["human_signoff"].ok is True


@pytest.mark.covers("FR-01.16/AC01")
def test_extension_scope_untraced_interview_row_still_blocks(tmp_path):
    planning_dir = tmp_path / ".shipwright" / "planning"
    _write_trace(planning_dir, _payload())
    _spec_with_fr(planning_dir)
    spec = planning_dir / "01-auth" / "spec.md"
    spec.write_text(spec.read_text(encoding="utf-8")
                    + "| FR-01.02 | Auth | New thing | Must | ... | interview | unit |\n", encoding="utf-8")
    (tmp_path / "shipwright_project_config.json").write_text('{"scope": "extension"}', encoding="utf-8")

    by_name = {r.name: r for r in run_all_checks(tmp_path, planning_dir=planning_dir)}

    assert by_name["fr_trace_coverage"].severity == Severity.ERROR.value
