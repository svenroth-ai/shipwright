"""Campaign A3: design / plan validators share freeze_splits' split authority and judge
the TASK's split; a no-UI run skips only the screen check, never the canon checks."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_LIB = _REPO_ROOT / "plugins" / "shipwright-run" / "scripts" / "lib"
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

_spec = importlib.util.spec_from_file_location("phase_validators_split_entry", _LIB / "phase_validators.py")
_pv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pv)

# importable by bare name once phase_validators has put its lib dir on sys.path
import phase_validators_split as split  # noqa: E402

validate_phase = _pv.validate_phase

pytestmark = pytest.mark.covers("FR-01.01/AC02")


@pytest.fixture
def canon_calls(monkeypatch):
    calls: list[tuple[str, str | None]] = []

    def recorder(phase, _root, _issues, *, run_id=None):
        calls.append((phase, run_id))

    monkeypatch.setattr(split, "_run_canon_checks", recorder)
    return calls


def _json(root: Path, name: str, data) -> None:
    (root / name).write_text(json.dumps(data), encoding="utf-8")


def _html(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "01-home.html").write_text("<html></html>", encoding="utf-8")


def _msgs(issues) -> str:
    return " | ".join(i["message"] for i in issues)


def test_registry_routes_design_and_plan_to_the_split_module():
    assert _pv._VALIDATORS["design"] is split._validate_design
    assert _pv._VALIDATORS["plan"] is split._validate_plan


def test_design_passes_on_project_global_screens(tmp_path, canon_calls):
    _json(tmp_path, "shipwright_project_config.json", {"splits": [{"name": "01-a"}]})
    _html(tmp_path / ".shipwright" / "designs" / "screens")
    valid, issues = validate_phase("design", tmp_path, run_id="r1")
    assert valid and issues == []
    assert canon_calls == [("design", "r1")]


def test_design_without_screens_or_splits_is_not_a_vacuous_pass(tmp_path, canon_calls):
    valid, issues = validate_phase("design", tmp_path)
    assert not valid and "No mockups found in .shipwright/designs/screens/" in _msgs(issues)
    assert canon_calls == []


def test_design_config_splits_win_over_project_config(tmp_path, canon_calls):
    _json(tmp_path, "shipwright_design_config.json", {"splits": ["01-a"]})
    _json(tmp_path, "shipwright_project_config.json", {"splits": [{"name": "01-a"}, {"name": "02-b"}]})
    _html(tmp_path / ".shipwright" / "planning" / "01-a" / "mockups")
    valid, issues = validate_phase("design", tmp_path)
    assert valid and issues == []


def test_design_per_split_mockups_missing_for_one_split(tmp_path, canon_calls):
    _json(tmp_path, "shipwright_project_config.json", {"splits": [{"name": "01-a"}, {"name": "02-b"}]})
    _html(tmp_path / ".shipwright" / "planning" / "01-a" / "mockups")
    valid, issues = validate_phase("design", tmp_path)
    assert not valid and "per split for: 02-b" in _msgs(issues)


def test_design_with_split_id_checks_only_that_split(tmp_path, canon_calls):
    _json(tmp_path, "shipwright_project_config.json", {"splits": [{"name": "01-a"}, {"name": "02-b"}]})
    _html(tmp_path / ".shipwright" / "planning" / "02-b" / "mockups")
    assert validate_phase("design", tmp_path, split_id="02-b")[0] is True
    assert validate_phase("design", tmp_path, split_id="01-a")[0] is False


def test_design_split_id_outside_the_resolved_splits_asks(tmp_path, canon_calls):
    _json(tmp_path, "shipwright_project_config.json", {"splits": [{"name": "01-a"}]})
    _html(tmp_path / ".shipwright" / "planning" / "09-typo" / "mockups")
    valid, issues = validate_phase("design", tmp_path, split_id="09-typo")
    assert not valid and "per split for: 09-typo" in _msgs(issues)
    (tmp_path / "shipwright_project_config.json").unlink()  # no splits resolve at all
    assert validate_phase("design", tmp_path, split_id="09-typo")[0] is False


def test_non_object_design_config_falls_back_to_project_splits(tmp_path, canon_calls):
    _json(tmp_path, "shipwright_design_config.json", ["01-a"])
    _json(tmp_path, "shipwright_project_config.json", {"splits": [{"name": "02-b"}]})
    _html(tmp_path / ".shipwright" / "planning" / "02-b" / "mockups")
    assert validate_phase("design", tmp_path)[0] is True


def test_non_ui_scope_skips_only_the_screen_check(tmp_path, canon_calls):
    _json(tmp_path, "shipwright_run_config.json", {"scope": "library"})
    valid, issues = validate_phase("design", tmp_path, run_id="r5")
    assert valid and [i["severity"] for i in issues] == ["inform"]
    assert "not applicable" in _msgs(issues) and canon_calls == [("design", "r5")]


def test_non_ui_scope_still_reports_a_broken_canon_check(tmp_path, monkeypatch):
    def broken(_phase, _root, issues, *, run_id=None):
        issues.append({"severity": "ask", "message": "[canon] C1: no phase_completed event"})

    monkeypatch.setattr(split, "_run_canon_checks", broken)
    _json(tmp_path, "shipwright_run_config.json", {"scope": "library"})
    valid, issues = validate_phase("design", tmp_path)
    assert not valid and "[canon] C1" in _msgs(issues)


def test_recover_to_skipped_then_complete_does_not_launder_design(tmp_path, canon_calls):
    """`recover-phase-task --force-status skipped` is no exemption for a later completion."""
    import phase_task_lifecycle as lifecycle

    _json(tmp_path, "shipwright_run_config.json", {"phase_tasks": [
        {"phaseTaskId": "pt-design", "phase": "design", "splitId": None,
         "status": "in_progress", "version": 1}]})
    assert lifecycle.recover_phase_task(tmp_path, phase_task_id="pt-design",
                                        force_status="skipped", reason="no UI")["ok"]
    valid, issues = validate_phase("design", tmp_path)
    assert not valid and "No mockups found" in _msgs(issues) and canon_calls == []


def test_a_self_recorded_design_skip_does_not_pass_its_own_gate(tmp_path, canon_calls):
    """The design phase writes its own config; a skip recorded there is not trusted."""
    _json(tmp_path, "shipwright_design_config.json", {"skipped": True, "reason": "CLI only"})
    _json(tmp_path, "shipwright_run_config.json", {"phase_tasks": [{"phase": "design", "status": "in_progress"}]})
    valid, issues = validate_phase("design", tmp_path)
    assert not valid and "Was design skipped intentionally?" in _msgs(issues)


def test_unreadable_or_odd_run_config_does_not_crash_the_probe(tmp_path, canon_calls):
    (tmp_path / "shipwright_run_config.json").write_text("{bad", encoding="utf-8")
    assert split._design_not_applicable(tmp_path) is None
    _json(tmp_path, "shipwright_run_config.json", ["not", "an", "object"])
    assert split._design_not_applicable(tmp_path) is None


def test_no_ui_scopes_mirror_the_design_verifier():
    from tools.verifiers import design_checks
    assert split._NO_UI_SCOPES == design_checks._NO_UI_SCOPES


def _plan_project(root: Path, current_split: str, files_in: str) -> None:
    _json(root, "shipwright_build_config.json",
          {"current_split": current_split, "sections": [{"name": "section-01"}]})
    sections = root / ".shipwright" / "planning" / files_in / "sections"
    sections.mkdir(parents=True)
    (sections / "section-01.md").write_text("# s", encoding="utf-8")


def test_plan_uses_the_tasks_split(tmp_path, canon_calls):
    _plan_project(tmp_path, current_split="", files_in="02-b")
    valid, issues = validate_phase("plan", tmp_path, split_id="02-b", run_id="r2")
    assert valid and issues == [] and canon_calls == [("plan", "r2")]


def test_plan_reports_build_config_for_another_split(tmp_path, canon_calls):
    _plan_project(tmp_path, current_split="01-a", files_in="01-a")
    valid, issues = validate_phase("plan", tmp_path, split_id="02-b")
    assert not valid and "this plan task is for split '02-b'" in _msgs(issues)


def test_plan_finds_an_archived_split_after_current_split_moved_on(tmp_path, canon_calls):
    _plan_project(tmp_path, current_split="02-b", files_in="01-a")
    config = json.loads((tmp_path / "shipwright_build_config.json").read_text(encoding="utf-8"))
    config["split_01_sections"] = [{"name": "section-01"}]
    config["completed_splits"] = ["01-a"]  # archive_split records the exact name
    _json(tmp_path, "shipwright_build_config.json", config)
    assert validate_phase("plan", tmp_path, split_id="01-a") == (True, [])


def test_plan_ignores_a_bucket_archive_split_did_not_record_for_that_name(tmp_path, canon_calls):
    """A shared or leftover prefix bucket is not this split's work (doubt review)."""
    _plan_project(tmp_path, current_split="02-b", files_in="01-a")
    config = json.loads((tmp_path / "shipwright_build_config.json").read_text(encoding="utf-8"))
    config.update(split_01_sections=[{"name": "section-01"}], completed_splits=["01-other"])
    _json(tmp_path, "shipwright_build_config.json", config)
    assert validate_phase("plan", tmp_path, split_id="01-a")[0] is False


def test_plan_split_less_layout_is_checked_when_no_split_is_known(tmp_path, canon_calls):
    _plan_project(tmp_path, current_split="", files_in="")
    assert validate_phase("plan", tmp_path) == (True, [])


def test_plan_without_split_id_falls_back_to_current_split(tmp_path, canon_calls):
    _plan_project(tmp_path, current_split="01-a", files_in="01-a")
    assert validate_phase("plan", tmp_path) == (True, [])


def test_plan_split_id_outside_the_resolved_splits_asks(tmp_path, canon_calls):
    _json(tmp_path, "shipwright_project_config.json", {"splits": [{"name": "01-a"}]})
    _plan_project(tmp_path, current_split="", files_in="../escape")
    valid, issues = validate_phase("plan", tmp_path, split_id="../escape")
    assert not valid and "is not one of this run's splits (01-a)" in _msgs(issues)
    assert canon_calls == []


def test_split_resolver_tolerates_a_bom_and_undecodable_bytes(tmp_path):
    from phase_task_planning import _resolve_splits_with_fallback

    (tmp_path / "shipwright_design_config.json").write_bytes(bytes([0xFF, 0xFE, 0x00]) + b"garbage")
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"splits": [{"name": "01-a"}]}), encoding="utf-8-sig")
    assert _resolve_splits_with_fallback(tmp_path) == (["01-a"], "project", None)


def test_plan_missing_sections_and_files(tmp_path, canon_calls):
    _json(tmp_path, "shipwright_build_config.json", {"sections": []})
    assert "No sections found" in _msgs(validate_phase("plan", tmp_path)[1])
    _json(tmp_path, "shipwright_build_config.json", {"current_split": "01-a", "sections": [{"name": "s9"}]})
    valid, issues = validate_phase("plan", tmp_path, split_id="01-a")
    assert not valid and "Missing section files for: s9" in _msgs(issues)


def test_build_forwards_the_run_id_and_no_split_for_a_current_split(tmp_path, monkeypatch):
    calls: list = []
    monkeypatch.setattr(_pv, "_run_canon_checks",
                        lambda phase, _r, _i, *, run_id=None, split_id=None:
                        calls.append((phase, run_id, split_id)))
    _json(tmp_path, "shipwright_build_config.json",
          {"sections": [{"name": "s1", "status": "complete", "tests_total": 3}]})
    assert validate_phase("build", tmp_path, split_id="01-a", run_id="r4") == (True, [])
    assert calls == [("build", "r4", None)]  # not archived: the current split, no skew risk
