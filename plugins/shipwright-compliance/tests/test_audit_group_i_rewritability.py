"""I9 (M7 "Rewritability") -- FR-level rendering, campaign req3-04c-ac-identity-wave2 p3.8.

Classification itself is unit-tested against
``shared/scripts/lib/rewritability_links.py`` directly
(``shared/scripts/tests/test_rewritability_links.py``); this file covers only
the Group I wiring -- that I9 is always advisory (never ``fail``), always
present, and renders the right counts for the two "not linked" outcomes
(``unlinked`` vs ``could_not_determine``) without conflating them.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.audit import group_i
from scripts.audit.audit_adapters import load_shared_lib
from scripts.audit.group_i_rewritability import rewritability_detail

HEADER = "| ID | Area | Name | Priority | Description | Basis | Layers |"
SEP = "|---|---|---|---|---|---|---|"


def _row(fr_id: str) -> str:
    return f"| {fr_id} | Adopted | Login | Must | Users sign in | code | unit (inferred) |"


def _spec(root: Path, *fr_ids: str) -> None:
    d = root / ".shipwright" / "planning" / "01-adopted"
    d.mkdir(parents=True, exist_ok=True)
    body = "\n".join([HEADER, SEP, *[_row(fr) for fr in fr_ids]]) + "\n"
    (d / "spec.md").write_text(body, encoding="utf-8")


def _write_events(root: Path, events: list[dict]) -> None:
    (root / "shipwright_events.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8",
    )


def _write_decision_drop(root: Path, run_id: str) -> None:
    dd = root / ".shipwright" / "agent_docs" / "decision-drops"
    dd.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id, "date": "2026-09-01", "section": "Iterate — test",
        "title": "A decision", "context": "Because.", "decision": "Did it.",
        "consequences": "Nothing changes.",
    }
    (dd / f"{run_id}_001.json").write_text(json.dumps(payload), encoding="utf-8")


def _i9(root: Path):
    return next(f for f in group_i.run(root, None, None) if f.check_id == "I9")


def test_never_fails_even_when_everything_is_unlinked(tmp_path: Path) -> None:
    _spec(tmp_path, "FR-01.01")
    _write_events(tmp_path, [
        {"type": "work_completed", "id": "e1", "ts": "2026-01-01T00:00:00+00:00",
         "affected_frs": ["FR-01.01"], "adr_id": "run-a"},
    ])
    finding = _i9(tmp_path)
    assert finding.status == "pass"
    assert "advisory" in finding.detail
    assert "no co-occurring rationale record" in finding.detail
    assert "FR-01.01" in finding.detail


def test_a_requirement_whose_change_has_a_decision_drop_is_linked(tmp_path: Path) -> None:
    _spec(tmp_path, "FR-01.01")
    _write_events(tmp_path, [
        {"type": "work_completed", "id": "e1", "ts": "2026-01-01T00:00:00+00:00",
         "affected_frs": ["FR-01.01"], "adr_id": "run-a"},
    ])
    _write_decision_drop(tmp_path, "run-a")
    finding = _i9(tmp_path)
    assert finding.status == "pass"
    assert "also recorded a decision-drop/ADR" in finding.detail


def test_no_recorded_changes_reports_could_not_determine_not_unlinked(tmp_path: Path) -> None:
    """The three-outcome discipline: silence in the log is not a verdict."""
    _spec(tmp_path, "FR-01.01")
    finding = _i9(tmp_path)
    assert finding.status == "pass"
    assert "cannot determine" in finding.detail
    assert "no linked rationale" not in finding.detail


def test_never_reddens_the_other_checks(tmp_path: Path) -> None:
    _spec(tmp_path, "FR-01.01")
    _write_events(tmp_path, [
        {"type": "work_completed", "id": "e1", "ts": "2026-01-01T00:00:00+00:00",
         "affected_frs": ["FR-01.01"], "adr_id": "run-a"},
    ])
    findings = {f.check_id: f for f in group_i.run(tmp_path, None, None)}
    assert findings["I9"].status == "pass"
    assert findings["I4"].status != "fail"


def test_preview_is_capped_but_the_true_count_is_reported(tmp_path: Path) -> None:
    """External code review (glm, low): the >5-ids preview-cap path had no
    direct test at the Group I wiring level."""
    fr_ids = [f"FR-01.0{i}" for i in range(1, 8)]  # 7 unlinked ids
    _spec(tmp_path, *fr_ids)
    _write_events(tmp_path, [
        {"type": "work_completed", "id": f"e{i}", "ts": "2026-01-01T00:00:00+00:00",
         "affected_frs": [fr], "adr_id": f"run-{i}"}
        for i, fr in enumerate(fr_ids)
    ])
    finding = _i9(tmp_path)
    assert finding.status == "pass"
    assert "7 requirement(s)" in finding.detail
    assert "+2 more" in finding.detail


def test_mixed_linked_and_unlinked_renders_both_parts(tmp_path: Path) -> None:
    _spec(tmp_path, "FR-01.01", "FR-01.02")
    _write_events(tmp_path, [
        {"type": "work_completed", "id": "e1", "ts": "2026-01-01T00:00:00+00:00",
         "affected_frs": ["FR-01.01"], "adr_id": "run-a"},
        {"type": "work_completed", "id": "e2", "ts": "2026-01-01T00:00:00+00:00",
         "affected_frs": ["FR-01.02"], "adr_id": "run-b"},
    ])
    _write_decision_drop(tmp_path, "run-a")
    finding = _i9(tmp_path)
    assert "FR-01.02" in finding.detail  # unlinked, named
    assert "FR-01.01" not in finding.detail  # linked, NOT in the unlinked preview


def test_event_log_unreadable_at_the_group_i_wiring_level_never_fails(
    tmp_path: Path, monkeypatch,
) -> None:
    """External code review (glm, low): the renderer's ``except
    rw.EventLogUnreadable`` clause was only proven at the shared-lib layer —
    nothing showed the Group I wiring itself survives it (e.g. an
    ``AttributeError`` if the loaded module lacked that name)."""
    _spec(tmp_path, "FR-01.01")
    rw = load_shared_lib("rewritability_links")

    def _raise(_root, _fr_ids):
        raise rw.EventLogUnreadable("simulated read fault")

    monkeypatch.setattr(rw, "scan_fr_rationale_links", _raise)
    finding = _i9(tmp_path)
    assert finding.status == "pass"
    assert "NOT EVALUATED" in finding.detail


def test_no_requirements_is_not_rendered_as_a_false_all_zero_claim(tmp_path: Path) -> None:
    """External code review (glm, low): guards the vacuous-``fr_ids`` case
    directly at the renderer, since ``group_i.run`` itself never reaches this
    function with an empty ``rows``."""
    assert rewritability_detail(tmp_path, []) == "no requirements to evaluate this run"
