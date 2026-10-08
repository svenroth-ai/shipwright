"""U6: the spec-impact gate covers fixes, wants a closed code, and runs at F5b too.

Also pins the FR-existence gate failing closed when specs exist but parse to
zero requirements. The change_type-vs-diff arm has its own file
(``test_requirement_gate_change_type_diff.py``).
"""

from __future__ import annotations

import json

import pytest

from lib import fr_gates
from lib.fr_gates import check_fr_existence, collect_known_fr_ids, existence_gate_error, run_fr_gates
from lib.spec_impact_gate import spec_impact_gate_error

_SPEC = """# Specification

## Functional Requirements

| ID | Name | Priority | Description | Source |
|----|------|----------|-------------|--------|
| FR-01.01 | Does a thing | Must | It does the thing. | `x.py` |
"""


def _event(**fields) -> dict:
    return {"type": "work_completed", "source": "iterate", **fields}


def _none(**fields) -> dict:
    return _event(spec_impact="none", spec_impact_justification="restores the documented retry",
                  spec_impact_reason_code="restores-specified-behavior", **fields)


@pytest.mark.covers("FR-01.11/AC03")
def test_a_bug_iterate_naming_nothing_is_refused():
    err = spec_impact_gate_error(_event(intent="bug"))
    assert err is not None and err["error"] == "spec_impact_unclassified"
    assert "Fixes are not exempt" in err["detail"]


@pytest.mark.covers("FR-01.11/AC03")
@pytest.mark.parametrize("intent", ["feature", "change", "bug", "BUG"])
def test_none_with_justification_and_code_passes_for_every_intent(intent):
    assert spec_impact_gate_error(_none(intent=intent)) is None


@pytest.mark.covers("FR-01.11/AC03")
def test_a_bug_naming_its_fr_passes():
    assert spec_impact_gate_error(_event(intent="bug", affected_frs=["FR-01.01"])) is None


@pytest.mark.covers("FR-01.11/AC03")
@pytest.mark.parametrize("code", [None, "", "because", ["docs-only"], "trivial-auto"])
def test_none_without_a_closed_code_is_refused(code):
    event = _none(intent="change")
    event["spec_impact_reason_code"] = code
    err = spec_impact_gate_error(event)
    assert err is not None and err["error"] == "spec_impact_none_requires_reason_code"
    assert "restores-specified-behavior" in err["detail"]


@pytest.mark.covers("FR-01.11/AC03")
def test_none_without_justification_is_refused_before_the_code():
    err = spec_impact_gate_error(_event(intent="bug", spec_impact="none",
                                        spec_impact_reason_code="docs-only"))
    assert err is not None and err["error"] == "spec_impact_none_requires_justification"


@pytest.mark.covers("FR-01.11/AC03")
@pytest.mark.parametrize("justification", [True, 7, ["why"], "line one" + chr(10) + "line two", "   "])
def test_a_justification_that_is_not_one_line_of_text_is_refused(justification):
    event = _none(intent="change", affected_frs=["FR-01.01"])
    event["spec_impact_justification"] = justification
    err = spec_impact_gate_error(event)
    assert err is not None and err["error"] == "spec_impact_none_requires_justification"


@pytest.mark.covers("FR-01.11/AC03")
def test_the_f5b_path_refuses_a_non_text_justification(tmp_path):
    from tools import finalize_iterate

    with pytest.raises(finalize_iterate.FinalizeGateError) as caught:
        finalize_iterate._record_event(tmp_path, "", "iterate-2026-10-08-u6-probe2", "probe", {
            "intent": "change", "affected_frs": ["FR-01.01"], "spec_impact": "none",
            "spec_impact_justification": True, "spec_impact_reason_code": "behavior-preserving"})
    assert caught.value.code == "spec_impact_none_requires_justification"


@pytest.mark.covers("FR-01.11/AC03")
def test_none_reason_counts_as_the_justification_like_f11_reads_it():
    event = _event(intent="change", spec_impact="none", none_reason="refactor",
                   spec_impact_reason_code="behavior-preserving")
    assert spec_impact_gate_error(event) is None


@pytest.mark.covers("FR-01.11/AC03")
def test_intent_less_events_need_not_classify_but_a_recorded_none_must_be_answered():
    assert spec_impact_gate_error(_event()) is None
    err = spec_impact_gate_error(_event(spec_impact="none", spec_impact_justification="x"))
    assert err is not None and err["error"] == "spec_impact_none_requires_reason_code"


@pytest.mark.covers("FR-01.11/AC03")
def test_non_iterate_and_non_dict_events_bypass():
    assert spec_impact_gate_error({"type": "work_completed", "source": "build", "intent": "bug"}) is None
    assert spec_impact_gate_error(None) is None


@pytest.mark.covers("FR-01.11/AC03")
def test_run_fr_gates_runs_the_spec_impact_arm(tmp_path):
    event = _event(intent="bug", change_type="tooling", none_reason="ci flake",
                   spec_impact="none", spec_impact_justification="ci flake")
    err = run_fr_gates(event, tmp_path, "test")
    assert err is not None and err["error"] == "spec_impact_none_requires_reason_code"


@pytest.mark.covers("FR-01.11/AC03")
def test_the_f5b_write_path_runs_the_spec_impact_gate(tmp_path):
    from tools import finalize_iterate

    with pytest.raises(finalize_iterate.FinalizeGateError) as caught:
        finalize_iterate._record_event(
            tmp_path, "", "iterate-2026-10-08-u6-probe", "probe",
            {"intent": "bug", "change_type": "tooling", "none_reason": "ci flake"})
    assert caught.value.code == "spec_impact_unclassified"
    assert not (tmp_path / "shipwright_events.jsonl").exists()


@pytest.mark.covers("FR-01.11/AC03")
def test_the_cli_refuses_an_unclassified_bug_and_accepts_the_reason_code(tmp_path, capsys):
    from tools import record_event

    base = ["--project-root", str(tmp_path), "--type", "work_completed", "--source", "iterate",
            "--intent", "bug", "--change-type", "tooling", "--none-reason", "ci flake"]
    assert record_event.main(base) == 1
    assert json.loads(capsys.readouterr().out)["error"] == "spec_impact_unclassified"
    ok = base + ["--spec-impact", "none", "--spec-impact-justification", "ci flake",
                 "--spec-impact-reason-code", "tooling-only"]
    assert record_event.main(ok) == 0
    events = (tmp_path / "shipwright_events.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(events[-1])["spec_impact_reason_code"] == "tooling-only"


def _f11(tmp_path, intent: str, **event_fields):
    from tools.verifiers.iterate_checks import check_spec_impact_recorded

    (tmp_path / "shipwright_run_config.json").write_text(json.dumps(
        {"iterate_history": [{"run_id": "r1", "complexity": "small", "type": intent}]}), encoding="utf-8")
    event = {"type": "work_completed", "source": "iterate", "commit": "abc1234", "adr_id": "r1",
             "intent": intent, **event_fields}
    (tmp_path / "shipwright_events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
    return check_spec_impact_recorded(tmp_path, "r1", "abc1234")


@pytest.mark.covers("FR-01.11/AC04")
def test_f11_no_longer_skips_a_bug_iterate(tmp_path):
    result = _f11(tmp_path, "bug", spec_impact="none")
    assert result.ok is False and not result.is_skipped


@pytest.mark.covers("FR-01.11/AC04")
def test_f11_passes_a_bug_iterate_that_justified_none(tmp_path):
    result = _f11(tmp_path, "bug", spec_impact="none", spec_impact_justification="restores retry",
                  spec_impact_reason_code="restores-specified-behavior")
    assert result.ok is True and not result.is_skipped


def _project(tmp_path, spec: str):
    split = tmp_path / ".shipwright" / "planning" / "01-core"
    split.mkdir(parents=True)
    (split / "spec.md").write_text(spec, encoding="utf-8")
    return tmp_path


@pytest.mark.covers("FR-01.11/AC03")
def test_specs_that_parse_to_zero_requirements_refuse_a_declared_id(tmp_path, capsys):
    root = _project(tmp_path, "# Spec\n\nNo table here.\n")
    err = check_fr_existence(_event(intent="change", affected_frs=["FR-01.01"]), root, "test")
    assert err is not None and err["error"] == "fr_gate_specs_unparsed"
    assert "FR-01.01" in err["detail"]
    assert "zero requirements parsed" in capsys.readouterr().err


@pytest.mark.covers("FR-01.11/AC03")
def test_zero_parsed_specs_do_not_block_an_event_that_declares_no_id():
    event = _event(intent="change", change_type="docs", none_reason="typo")
    assert existence_gate_error(event, frozenset(), specs_found=True) is None
    assert existence_gate_error(_event(affected_frs=["FR-01.01"]), frozenset(), specs_found=False) is None


@pytest.mark.covers("FR-01.11/AC03")
def test_a_collector_crash_on_present_specs_reads_as_found_not_absent(tmp_path, monkeypatch):
    import lib.drift_parsers as drift_parsers

    root = _project(tmp_path, _SPEC)
    assert collect_known_fr_ids(root) == (frozenset({"FR-01.01"}), True)

    def _boom(_root):
        raise RuntimeError("parser broke")

    monkeypatch.setattr(drift_parsers, "collect_requirements_from_planning", _boom)
    assert collect_known_fr_ids(root) == (frozenset(), True)
    err = fr_gates.check_fr_existence(_event(affected_frs=["FR-01.01"]), root, "test")
    assert err is not None and err["error"] == "fr_gate_specs_unparsed"
