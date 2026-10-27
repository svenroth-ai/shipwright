"""Q2 must count sections that ``archive_split.py`` moved out of ``sections[]``.

GitHub issue #930: once a split is archived its entries live under
``split_<prefix>_sections`` and ``sections`` holds only the current split, yet
the plan side of Q2 collects section names from every split — so every
section of a finished split was reported as "missing".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib import phase_quality as pq  # noqa: E402
from tools.verifiers import quality_checks as qc  # noqa: E402


def _write_plan(proj: Path, sections: list[str]) -> None:
    (proj / "shipwright_plan_snapshot.json").write_text(
        json.dumps({"sections": sections}), encoding="utf-8",
    )


def _write_build(proj: Path, config: dict) -> None:
    (proj / "shipwright_build_config.json").write_text(
        json.dumps(config), encoding="utf-8",
    )


def _entry(name: str, status: str = "complete") -> dict:
    return {"name": name, "status": status}


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    return tmp_path


@pytest.mark.covers("FR-01.05")
def test_q2_passes_when_a_finished_split_is_archived(proj: Path):
    _write_plan(proj, ["01-a", "02-a", "03-b"])
    _write_build(proj, {
        "current_split": "02-b",
        "completed_splits": ["01-x"],
        "split_01_sections": [_entry("01-a"), _entry("02-a")],
        "sections": [_entry("03-b")],
    })
    f = qc.check_q2_plan_subset_of_build(proj)
    assert f["status"] == pq.STATUS_PASS, f


@pytest.mark.covers("FR-01.05")
def test_q2_still_fails_on_incomplete_archived_section(proj: Path):
    _write_plan(proj, ["01-a"])
    _write_build(proj, {
        "split_01_sections": [_entry("01-a", "in_progress")],
        "sections": [],
    })
    f = qc.check_q2_plan_subset_of_build(proj)
    assert f["status"] == pq.STATUS_FAIL
    assert "in_progress" in f["evidence"]


@pytest.mark.covers("FR-01.05")
def test_q2_current_sections_win_on_name_clash(proj: Path):
    _write_plan(proj, ["01-a"])
    _write_build(proj, {
        "split_01_sections": [_entry("01-a", "in_progress")],
        "sections": [_entry("01-a", "complete")],
    })
    f = qc.check_q2_plan_subset_of_build(proj)
    assert f["status"] == pq.STATUS_PASS, f


@pytest.mark.covers("FR-01.05")
def test_q2_ignores_non_split_keys_and_malformed_archives(proj: Path):
    _write_plan(proj, ["01-a"])
    _write_build(proj, {
        "split_01_sections": "not-a-list",
        "split_notes": [_entry("01-a")],  # not a split_<prefix>_sections key
        "sections": [],
    })
    f = qc.check_q2_plan_subset_of_build(proj)
    assert f["status"] == pq.STATUS_FAIL
    assert "01-a" in f["evidence"]


@pytest.mark.covers("FR-01.05")
def test_q2_counts_archive_with_non_numeric_split_prefix(proj: Path):
    # archive_split.py keys on the text before the first "-": "auth-api" -> split_auth_sections
    _write_plan(proj, ["auth-a", "api-a"])
    _write_build(proj, {
        "split_auth_sections": [_entry("auth-a")],
        "split_api_sections": [_entry("api-a")],
        "sections": [],
    })
    f = qc.check_q2_plan_subset_of_build(proj)
    assert f["status"] == pq.STATUS_PASS, f


@pytest.mark.covers("FR-01.05")
def test_q2_counts_archives_when_sections_key_is_missing(proj: Path):
    _write_plan(proj, ["01-a"])
    _write_build(proj, {"split_01_sections": [_entry("01-a")]})
    f = qc.check_q2_plan_subset_of_build(proj)
    assert f["status"] == pq.STATUS_PASS, f


@pytest.mark.covers("FR-01.05")
def test_q2_does_not_crash_on_non_object_build_config(proj: Path):
    _write_plan(proj, ["01-a"])
    (proj / "shipwright_build_config.json").write_text("[]", encoding="utf-8")
    f = qc.check_q2_plan_subset_of_build(proj)
    assert f["status"] == pq.STATUS_FAIL
