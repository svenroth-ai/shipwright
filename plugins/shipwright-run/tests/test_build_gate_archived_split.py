"""The build gate judges the TASK's split, also once the build skill archived it.

For a non-final split the build skill runs ``archive_split`` before its result is
applied: the split's sections move to ``split_<prefix>_sections`` and ``sections`` becomes
``[]``. Before this fix the enforced gate then asked "No sections found for current split"
and refused every correct non-final build (iterate gate-hardening-leftovers).
"""
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

_spec = importlib.util.spec_from_file_location("phase_validators_archived_entry",
                                               _LIB / "phase_validators.py")
_pv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pv)

import phase_validators_canon as canon  # noqa: E402
import phase_validators_split as split  # noqa: E402
from orchestrator_pkg import phase_gate  # noqa: E402
from tools.archive_split import archive_split  # noqa: E402
from tools.verifiers import build_split  # noqa: E402

validate_phase = _pv.validate_phase

pytestmark = pytest.mark.covers("FR-01.01/AC02")

DONE = {"name": "s1", "status": "complete", "tests_total": 3}


@pytest.fixture
def canon_calls(monkeypatch):
    calls: list = []
    monkeypatch.setattr(_pv, "_run_canon_checks",
                        lambda phase, _r, _i, *, run_id=None, split_id=None:
                        calls.append((phase, run_id, split_id)))
    return calls


def _archived(root: Path, sections: list) -> None:
    (root / "shipwright_project_config.json").write_text(
        json.dumps({"splits": [{"name": "01-a"}, {"name": "02-b"}]}), encoding="utf-8")
    (root / "shipwright_build_config.json").write_text(
        json.dumps({"current_split": "01-a", "sections": sections}), encoding="utf-8")
    assert archive_split(root, "02-b")["success"] is True  # the build skill's own step


def test_an_archived_complete_split_passes_its_build_gate(tmp_path, canon_calls):
    _archived(tmp_path, [DONE])
    assert validate_phase("build", tmp_path, split_id="01-a", run_id="r") == (True, [])
    assert canon_calls == [("build", "r", "01-a")]


def test_an_archived_incomplete_split_asks_and_is_not_retryable(tmp_path, canon_calls):
    _archived(tmp_path, [{**DONE, "status": "in_progress"}])
    valid, issues = validate_phase("build", tmp_path, split_id="01-a")
    assert not valid and "Sections not complete: s1" in issues[0]["message"]
    assert issues[0]["kind"] == "archived_split"
    assert phase_gate.is_retryable({"ask": issues}) is False


def test_an_archived_split_flags_a_finding_that_has_its_own_kind(tmp_path, monkeypatch):
    """A canon_degraded ask on an archived split must still say it is archived, or the
    ask_human answer would offer a recover that builds the next split (external review)."""
    _archived(tmp_path, [DONE])
    degraded = {"severity": "ask", "kind": "canon_degraded", "message": "old verifier"}
    monkeypatch.setattr(_pv, "_run_canon_checks",
                        lambda _p, _r, issues, **_kw: issues.append(dict(degraded)))
    _valid, issues = validate_phase("build", tmp_path, split_id="01-a", run_id="r")
    assert (issues[0]["kind"], issues[0]["archived_split"]) == ("canon_degraded", True)


def test_an_empty_current_split_keeps_the_current_split_wording(tmp_path, canon_calls):
    (tmp_path / "shipwright_build_config.json").write_text(
        json.dumps({"current_split": "01-a", "sections": []}), encoding="utf-8")
    _valid, issues = validate_phase("build", tmp_path, split_id="01-a")
    assert "No sections found for current split" in issues[0]["message"]


def test_a_split_with_nothing_archived_asks_by_name(tmp_path, canon_calls):
    (tmp_path / "shipwright_build_config.json").write_text(
        json.dumps({"current_split": "02-b", "sections": [DONE]}), encoding="utf-8")
    valid, issues = validate_phase("build", tmp_path, split_id="01-a")
    assert not valid and "No sections found for split '01-a'" in issues[0]["message"]
    assert phase_gate.is_retryable({"ask": issues}) is False  # a typo or unbuilt split


@pytest.mark.parametrize("split_id", [None, "01-a"])
def test_the_current_split_is_judged_as_before(tmp_path, canon_calls, split_id):
    (tmp_path / "shipwright_build_config.json").write_text(
        json.dumps({"current_split": "01-a", "sections": [{**DONE, "tests_total": 0}]}),
        encoding="utf-8")
    valid, issues = validate_phase("build", tmp_path, split_id=split_id)
    assert not valid and "Sections with no tests: s1" in issues[0]["message"]
    assert "kind" not in issues[0]  # retryable: the build works on this split


def test_a_current_split_build_hands_no_split_to_the_canon(tmp_path, canon_calls):
    """Same sections either way, so an older installed verifier is not refused for it."""
    (tmp_path / "shipwright_build_config.json").write_text(
        json.dumps({"current_split": "01-a", "sections": [DONE]}), encoding="utf-8")
    assert validate_phase("build", tmp_path, split_id="01-a", run_id="r") == (True, [])
    assert canon_calls == [("build", "r", None)]


def test_no_sections_without_a_split_keeps_its_old_message(tmp_path, canon_calls):
    (tmp_path / "shipwright_build_config.json").write_text("{}", encoding="utf-8")
    _valid, issues = validate_phase("build", tmp_path)
    assert "No sections found for current split" in issues[0]["message"]


_CASES = [
    ({}, None), ({}, "01-a"),
    ({"sections": [DONE]}, None),
    ({"sections": [DONE]}, "01-a"),                                   # no current_split
    ({"current_split": "01-a", "sections": [DONE]}, "01-a"),
    ({"current_split": "02-b", "sections": [], "split_01_sections": [DONE]}, "01-a"),
    ({"current_split": "02-b", "split_01_sections": [DONE], "completed_splits": ["01-a"]}, "01-a"),
    ({"current_split": "02-b", "split_01_sections": [DONE], "completed_splits": "01-a"}, "01-a"),
    ({"current_split": "auth-api", "split_auth_sections": [DONE],
      "completed_splits": ["auth"]}, "auth-x"),
    ({"current_split": "02-b", "sections": [DONE]}, "01-a"),          # nothing archived
    ({"current_split": "02-b", "split_01_sections": "bad"}, "01-a"),
    ({"current_split": "auth", "sections": [], "split_api_sections": [DONE]}, "api"),
    ({"current_split": "auth", "split_api_sections": [DONE], "completed_splits": ["api"]}, "api"),
    ({"sections": "bad"}, None),
    ("bad", "01-a"), (None, None),
]


@pytest.mark.parametrize("config,split_id", _CASES)
def test_the_run_plugin_mirror_agrees_with_the_verifier(config, split_id):
    assert split.sections_for_split(config, split_id) == build_split.sections_for_split(
        config, split_id)


def test_both_readers_agree_on_a_real_archive_split_output(tmp_path):
    _archived(tmp_path, [DONE])
    config = json.loads((tmp_path / "shipwright_build_config.json").read_text(encoding="utf-8"))
    assert split.sections_for_split(config, "01-a") == [DONE]
    assert build_split.sections_for_split(config, "01-a") == [DONE]


def test_the_bridge_hands_the_split_to_the_build_checks_only(tmp_path, monkeypatch):
    from tools.verifiers import build_checks, plan_checks

    seen: list = []
    monkeypatch.setattr(build_checks, "run_build_checks",
                        lambda _r, *, run_id, split_id=None: seen.append(split_id) or [])
    monkeypatch.setattr(plan_checks, "run_plan_checks",
                        lambda _r, *, run_id: seen.append("plan") or [])
    canon._run_canon_checks("build", tmp_path, [], run_id="r", split_id="01-a")
    canon._run_canon_checks("build", tmp_path, [], run_id="r")
    canon._run_canon_checks("plan", tmp_path, [], run_id="r", split_id="01-a")
    assert seen == ["01-a", None, "plan"]


def test_an_older_build_verifier_is_a_degraded_ask_not_a_crash(tmp_path, monkeypatch):
    from tools.verifiers import build_checks

    monkeypatch.setattr(build_checks, "run_build_checks", lambda _r, *, run_id: [])
    issues: list = []
    canon._run_canon_checks("build", tmp_path, issues, run_id="r", split_id="01-a")
    assert [(i["severity"], i["kind"]) for i in issues] == [("ask", "canon_degraded")]
    assert "older than the run plugin" in issues[0]["message"]


def test_a_compatible_verifier_that_fails_is_not_mistaken_for_an_old_one(tmp_path, monkeypatch):
    from tools.verifiers import build_checks

    def broken(_r, *, run_id, split_id=None):
        raise TypeError("a bug inside the checks")

    monkeypatch.setattr(build_checks, "run_build_checks", broken)
    with pytest.raises(TypeError, match="a bug inside"):  # the gate reports it as gate-error
        canon._run_canon_checks("build", tmp_path, [], run_id="r", split_id="01-a")


def test_a_verifier_taking_kwargs_gets_the_split(tmp_path, monkeypatch):
    from tools.verifiers import build_checks

    seen: list = []
    monkeypatch.setattr(build_checks, "run_build_checks",
                        lambda _r, **kw: seen.append(kw.get("split_id")) or [])
    issues: list = []
    canon._run_canon_checks("build", tmp_path, issues, run_id="r", split_id="01-a")
    assert seen == ["01-a"] and issues == []
