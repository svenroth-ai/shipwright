"""The build verifiers judge an archived split's own sections when asked for that split.

For a non-final split the build skill runs ``archive_split`` before the result is gated, so
``sections`` is ``[]`` and the per-section checks used to pass vacuously ("no complete
sections to check") for the very split they were asked about (A5 doubt review).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.archive_split import archive_split
from tools.verifiers import build_split
from tools.verifiers.build_checks import (
    check_all_sections_complete,
    check_per_section_work_completed_events,
    run_build_checks,
)

pytestmark = pytest.mark.covers("FR-01.01/AC02")

DONE = {"name": "01-login", "status": "complete", "tests_total": 2}


def _archived(root: Path, sections: list) -> None:
    (root / "shipwright_project_config.json").write_text(
        json.dumps({"splits": [{"name": "01-core"}, {"name": "02-ui"}]}), encoding="utf-8")
    (root / "shipwright_build_config.json").write_text(
        json.dumps({"current_split": "01-core", "sections": sections}), encoding="utf-8")
    assert archive_split(root, "02-ui")["success"] is True


def _by_name(results, prefix: str):
    return next(r for r in results if r.name.startswith(prefix))


def test_the_archived_splits_missing_event_is_reported(tmp_path):
    _archived(tmp_path, [DONE])
    result = check_per_section_work_completed_events(tmp_path, "01-core")
    assert result.ok is False and "01-login" in result.detail


def test_without_a_split_the_checks_read_the_current_list_as_before(tmp_path):
    _archived(tmp_path, [DONE])
    result = check_per_section_work_completed_events(tmp_path)
    assert result.ok is True and "no complete sections" in result.detail


def test_the_archived_splits_recorded_event_satisfies_c1(tmp_path):
    _archived(tmp_path, [DONE])
    (tmp_path / "shipwright_events.jsonl").write_text(json.dumps(
        {"type": "work_completed", "source": "build", "section": "01-login"}) + "\n",
        encoding="utf-8")
    assert check_per_section_work_completed_events(tmp_path, "01-core").ok is True


def test_an_archived_incomplete_section_fails_the_completeness_check(tmp_path):
    _archived(tmp_path, [{**DONE, "status": "in_progress"}])
    assert check_all_sections_complete(tmp_path, "01-core").ok is False


def test_run_build_checks_forwards_the_split(tmp_path):
    _archived(tmp_path, [DONE])
    with_split = _by_name(run_build_checks(tmp_path, run_id="r", split_id="01-core"), "C1")
    without = _by_name(run_build_checks(tmp_path, run_id="r"), "C1")
    assert with_split.ok is False and without.ok is True


@pytest.mark.parametrize("config,split_id,expected", [
    ("bad", "01-a", {}),
    ({"sections": [DONE]}, None, {"sections": [DONE]}),
    ({"current_split": "", "sections": [DONE]}, "01-a", {"current_split": "", "sections": [DONE]}),
    ({"current_split": "02-b", "split_01_sections": [DONE], "completed_splits": ["01-a"]}, "01-a",
     {"current_split": "01-a", "split_01_sections": [DONE], "completed_splits": ["01-a"],
      "sections": [DONE]}),
    ({"current_split": "02-b", "split_01_sections": [DONE], "completed_splits": ["01-x"]}, "01-a",
     {"current_split": "01-a", "split_01_sections": [DONE], "completed_splits": ["01-x"],
      "sections": []}),
    ({"current_split": "02-b"}, "01-a", {"current_split": "01-a", "sections": []}),
])
def test_build_config_for_split(config, split_id, expected):
    assert build_split.build_config_for_split(config, split_id) == expected


def test_sections_for_split_rejects_non_objects_and_non_lists():
    assert build_split.sections_for_split(None, "01-a") == []
    assert build_split.sections_for_split({"sections": "x"}, None) == []
    assert build_split.archived_sections_key("03-api-gw") == "split_03_sections"


def test_the_archived_split_is_judged_on_its_own_history_entry(tmp_path):
    """The current split's history lists the section; the archived split's own entry does
    not. Judged for the archived split, the check must report it (external plan review)."""
    from tools.verifiers.build_checks import check_phase_history_build_has_sections

    _archived(tmp_path, [DONE])
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({"phase_history": {"build": [
        {"run_id": "r", "split": "01-core", "sections": [{"id": "01-other"}]},
        {"run_id": "r", "split": "02-ui", "sections": [{"id": "01-login"}]},
    ]}}), encoding="utf-8")
    result = check_phase_history_build_has_sections(tmp_path, "r", "01-core")
    assert result.ok is False and "01-login" in result.detail
