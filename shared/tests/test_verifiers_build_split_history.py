"""``check_phase_history_build_has_sections`` across build splits sharing one run id (A5 review).

A driven run exports one ``SHIPWRIGHT_RUN_ID`` for every phase, so ``phase_history[build]``
holds one entry per split under the SAME id. The check used to take the FIRST matching
entry (split 01's) and compare it with the CURRENT split's sections, rejecting build/02 on
every attempt. It now takes the newest entry, preferring the current split's.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.verifiers.build_checks import check_phase_history_build_has_sections

pytestmark = pytest.mark.covers("FR-01.01/AC02")

RUN = "run-1a2b3c4d"


def _seed(root: Path, *, current: str | None, sections: list[str], history: list[dict]) -> None:
    cfg = {"sections": [{"name": n, "status": "complete"} for n in sections]}
    if current:
        cfg["current_split"] = current
    (root / "shipwright_build_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    (root / "shipwright_run_config.json").write_text(
        json.dumps({"phase_history": {"build": history}}), encoding="utf-8")


def _entry(split: str | None, *ids: str) -> dict:
    entry = {"run_id": RUN, "sections": [{"id": i} for i in ids]}
    if split:
        entry["split"] = split
    return entry


def test_the_second_split_is_checked_against_its_own_entry(tmp_path):
    _seed(tmp_path, current="02-ui", sections=["01-dash"],
          history=[_entry("01-core", "01-login"), _entry("02-ui", "01-dash")])
    assert check_phase_history_build_has_sections(tmp_path, RUN).ok is True


def test_the_current_splits_entry_wins_even_when_older(tmp_path):
    _seed(tmp_path, current="01-core", sections=["01-login"],
          history=[_entry("01-core", "01-login"), _entry("02-ui", "01-dash")])
    assert check_phase_history_build_has_sections(tmp_path, RUN).ok is True


def test_a_split_with_no_entry_of_its_own_falls_back_to_the_newest(tmp_path):
    _seed(tmp_path, current="02-ui", sections=["01-dash"],
          history=[_entry("01-core", "01-login")])
    result = check_phase_history_build_has_sections(tmp_path, RUN)
    assert result.ok is False and "01-dash" in result.detail


def test_without_split_fields_the_newest_entry_counts(tmp_path):
    _seed(tmp_path, current=None, sections=["01-dash"],
          history=[_entry(None, "01-login"), _entry(None, "01-dash")])
    assert check_phase_history_build_has_sections(tmp_path, RUN).ok is True
