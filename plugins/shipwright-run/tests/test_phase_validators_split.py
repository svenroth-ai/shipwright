"""Campaign A3: design / plan validators share freeze_splits' split authority and judge
the TASK's split; both skip keys count; the canon bridge never swallows a degraded run."""

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
import phase_validators_canon as canon  # noqa: E402
import phase_validators_late as late  # noqa: E402
import phase_validators_split as split  # noqa: E402

validate_phase = _pv.validate_phase

pytestmark = pytest.mark.covers("FR-01.01/AC01")


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


def test_non_ui_scope_passes_design_with_a_note(tmp_path, canon_calls):
    _json(tmp_path, "shipwright_run_config.json", {"scope": "library"})
    valid, issues = validate_phase("design", tmp_path)
    assert valid and [i["severity"] for i in issues] == ["inform"]
    assert "not applicable" in _msgs(issues) and canon_calls == []


def test_design_task_skipped_by_the_orchestrator_passes(tmp_path, canon_calls):
    _json(tmp_path, "shipwright_run_config.json",
          {"phase_tasks": [{"phase": "project", "status": "done"},
                           {"phase": "design", "status": "skipped"}]})
    valid, issues = validate_phase("design", tmp_path)
    assert valid and "marked skipped" in _msgs(issues) and canon_calls == []


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
    _json(tmp_path, "shipwright_build_config.json", config)
    assert validate_phase("plan", tmp_path, split_id="01-a") == (True, [])


def test_plan_split_less_layout_is_checked_when_no_split_is_known(tmp_path, canon_calls):
    _plan_project(tmp_path, current_split="", files_in="")
    assert validate_phase("plan", tmp_path) == (True, [])


def test_plan_without_split_id_falls_back_to_current_split(tmp_path, canon_calls):
    _plan_project(tmp_path, current_split="01-a", files_in="01-a")
    assert validate_phase("plan", tmp_path) == (True, [])


def test_plan_missing_sections_and_files(tmp_path, canon_calls):
    _json(tmp_path, "shipwright_build_config.json", {"sections": []})
    assert "No sections found" in _msgs(validate_phase("plan", tmp_path)[1])
    _json(tmp_path, "shipwright_build_config.json", {"current_split": "01-a", "sections": [{"name": "s9"}]})
    valid, issues = validate_phase("plan", tmp_path, split_id="01-a")
    assert not valid and "Missing section files for: s9" in _msgs(issues)


def test_build_forwards_the_run_id_to_the_canon_bridge(tmp_path, monkeypatch):
    calls: list = []
    monkeypatch.setattr(_pv, "_run_canon_checks",
                        lambda phase, _r, _i, *, run_id=None: calls.append((phase, run_id)))
    _json(tmp_path, "shipwright_build_config.json",
          {"sections": [{"name": "s1", "status": "complete", "tests_total": 3}]})
    assert validate_phase("build", tmp_path, split_id="01-a", run_id="r4") == (True, [])
    assert calls == [("build", "r4")]


@pytest.mark.parametrize("key", ["reason", "skip_reason"])
def test_test_layers_accept_either_skip_key(tmp_path, monkeypatch, key):
    monkeypatch.setattr(late, "_run_canon_checks", lambda *_a, **_k: None)
    _json(tmp_path, "shipwright_test_results.json", {
        "unit": {"total": 1, "passed": 1},
        "integration": {"skipped": True, key: "no db"},
        "smoke": {"status": "skip", key: "no server"},
        "e2e": {"skipped": True, key: "no browser"},
    })
    assert validate_phase("test", tmp_path) == (True, [])


def _hide_verifiers(monkeypatch):
    """Make ``tools.verifiers`` unlocatable, including submodules an earlier test cached."""
    for name in [m for m in sys.modules if m == "tools.verifiers" or m.startswith("tools.verifiers.")]:
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setitem(sys.modules, "tools.verifiers", None)


def test_skip_reason_accepts_only_non_blank_strings():
    assert late._skip_reason({"reason": {"x": 1}, "skip_reason": " no db "}) == "no db"
    assert late._skip_reason({"reason": ["a"]}) == ""


def test_absent_canon_package_is_a_visible_degraded_note(tmp_path, monkeypatch):
    _hide_verifiers(monkeypatch)
    issues: list[dict] = []
    canon._run_canon_checks("plan", tmp_path, issues, run_id="r3")
    assert len(issues) == 1
    assert issues[0]["severity"] == "inform" and issues[0]["kind"] == "canon_degraded"
    assert issues[0]["message"].startswith(f"{canon.DEGRADED_PREFIX} plan: canon verifiers are not importable")


def test_broken_canon_module_import_is_ask_level(tmp_path, monkeypatch):
    """The package is locatable, so a submodule that fails to import is broken, not absent."""
    monkeypatch.setitem(sys.modules, "tools.verifiers.plan_checks", None)
    issues: list[dict] = []
    canon._run_canon_checks("plan", tmp_path, issues, run_id="r3")
    assert [(i["severity"], i["kind"]) for i in issues] == [("ask", "canon_degraded")]
    assert "a canon verifier failed to import" in issues[0]["message"]


def test_explicit_empty_run_id_is_ask_level(tmp_path):
    issues: list[dict] = []
    canon._run_canon_checks("plan", tmp_path, issues, run_id="  ")
    assert [(i["severity"], i["kind"]) for i in issues] == [("ask", "canon_degraded")]
    assert "empty run id" in issues[0]["message"]


def test_degraded_note_reaches_the_gate_consumer(tmp_path, monkeypatch):
    """run_phase_gate (the v1 path's consumer, A4's v2 seam) keeps the note as inform."""
    _hide_verifiers(monkeypatch)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    from orchestrator_pkg.validation_record import run_phase_gate

    ask, inform, checked = run_phase_gate(tmp_path, "changelog")
    assert checked and ask == []
    assert [i.get("kind") for i in inform] == ["canon_degraded"]


def _stub_plan_checks(monkeypatch, seen: list):
    from tools.verifiers import plan_checks

    def stub(_root, *, run_id):
        seen.append(run_id)
        return []

    monkeypatch.setattr(plan_checks, "run_plan_checks", stub)


def test_explicit_run_id_beats_the_environment(tmp_path, monkeypatch):
    seen: list = []
    _stub_plan_checks(monkeypatch, seen)
    monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "from-env")
    issues: list[dict] = []
    canon._run_canon_checks("plan", tmp_path, issues, run_id="explicit")
    assert seen == ["explicit"] and issues == []


def test_missing_run_id_is_a_visible_degraded_note(tmp_path, monkeypatch):
    seen: list = []
    _stub_plan_checks(monkeypatch, seen)
    monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)
    issues: list[dict] = []
    canon._run_canon_checks("plan", tmp_path, issues)
    assert seen == [""]
    assert [i["kind"] for i in issues] == ["canon_degraded"]
    assert "phase_history[plan] was not checked" in issues[0]["message"]


def test_an_unlocatable_verifier_package_reads_as_absent(monkeypatch):
    def boom(_name):
        raise ValueError("tools.verifiers.__spec__ is None")

    monkeypatch.setattr(canon.importlib.util, "find_spec", boom)
    assert canon._verifiers_present() is False
