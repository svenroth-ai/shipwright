"""RTM per-FR layer columns (traceability campaign TT2, Spec §5 / AC1).

RED before TT2 (the ``Unit | Integration | E2E`` columns did not exist); green after.
Kept separate from ``test_rtm_generator.py`` (a frozen anti-ratchet baseline entry).
Pins: the header gains the three layer columns; a coverage glyph (ok / MISSING / n/a /
—) renders per FR; an FR with unit-but-no-E2E is visibly ``E2E: MISSING`` (AC1); and
the pre-existing positional columns (Reconciled?=7, Status=8) are UNSHIFTED.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.lib.data_collector import ComplianceData, RequirementInfo, WorkEvent
from scripts.lib.rtm_generator import generate


def _write_manifest(tmp_path: Path, requirements: dict) -> None:
    path = tmp_path / ".shipwright" / "compliance" / "test-traceability.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 2, "collector_version": "test", "generated_at": "t",
        "source_commit": "x", "spec_hash": "h", "requirements": requirements,
        "orphans": [], "invalid_tags": [], "invalid_layers": [], "untagged_tests": [],
    }), encoding="utf-8")


def _node(fr_id, required, coverage):
    return {
        "id": fr_id, "spec_path": "s/spec.md", "title": fr_id, "priority": "Must",
        "status": "active", "required_layers": list(required),
        "required_layers_source": "explicit", "tests": {}, "coverage": coverage,
    }


def _data(tmp_path, *, split="01-auth", fr_id="FR-01.01"):
    data = ComplianceData(project_root=tmp_path, timestamp="2026-06-28T00:00:00Z")
    data.requirements = [
        RequirementInfo(id=fr_id, text="Login works", priority="Must", split=split),
    ]
    data.work_events = [
        WorkEvent(id="evt-00000001", timestamp="2026-06-01T00:00:00Z", source="iterate",
                  tests_passed=5, tests_total=5, affected_frs=[fr_id]),
    ]
    return data


def _row(result: str, fr_id="FR-01.01") -> list[str]:
    rows = [l for l in result.splitlines() if l.startswith(f"| [{fr_id}]")]
    assert rows, f"{fr_id} row missing"
    return [c.strip() for c in rows[0].split("|")]


def test_header_has_layer_columns(tmp_path):
    _write_manifest(tmp_path, {"01-auth::FR-01.01": _node("FR-01.01", ["unit"], {"unit": "ok"})})
    result = generate(_data(tmp_path))
    assert "| Unit | Integration | E2E |" in result


def test_unit_ok_e2e_missing_renders_glyphs_not_numbers(tmp_path):
    """AC1 — unit-but-no-E2E is visibly ``E2E: MISSING`` (a glyph, not a bare count)."""
    _write_manifest(tmp_path, {
        "01-auth::FR-01.01": _node("FR-01.01", ["unit", "e2e"],
                                   {"unit": "ok", "e2e": "MISSING"}),
    })
    cells = _row(generate(_data(tmp_path)))
    # 7=Reconciled? 8=Status 9=Unit 10=Integration 11=E2E (leading | → index 0 empty).
    assert cells[9] == "ok"
    assert cells[10] == "—"       # integration not required → absent
    assert cells[11] == "MISSING"


def test_pre_existing_positional_columns_unshifted(tmp_path):
    """Reconciled?=7 and Status=8 keep their indices — the layer columns are appended
    AFTER Status, so ``test_rtm_reconciled_column``'s _cell(row, 7/8) stays valid."""
    _write_manifest(tmp_path, {"01-auth::FR-01.01": _node("FR-01.01", ["unit"], {"unit": "ok"})})
    cells = _row(generate(_data(tmp_path)))
    assert cells[7] == "—"          # not behavior-touched
    assert cells[8] == "COVERED"    # tested event, gap<=0


def test_absent_manifest_renders_dashes(tmp_path):
    """No manifest → the FR isn't in the index → all three columns are — (graceful)."""
    cells = _row(generate(_data(tmp_path)))  # no _write_manifest
    assert cells[9] == "—"
    assert cells[10] == "—"
    assert cells[11] == "—"


def test_namespaced_key_resolves_this_rows_split(tmp_path):
    """The row matches its OWN split::FR entry (distinct ids, no collision) — a different
    FR in another namespace does not bleed in."""
    _write_manifest(tmp_path, {
        "01-auth::FR-01.01": _node("FR-01.01", ["e2e"], {"e2e": "ok"}),
        "02-other::FR-02.02": _node("FR-02.02", ["e2e"], {"e2e": "MISSING"}),
    })
    cells = _row(generate(_data(tmp_path, split="01-auth")))
    assert cells[11] == "ok"  # 01-auth's own entry


def test_collision_display_id_renders_ambiguous_not_ok(tmp_path):
    """MUST-FIX 2b — when the display id is shared across namespaces the fanned ``ok`` is
    rendered ``?`` (RTM agrees with D-layer's fail-closed ``ambiguous_fanout``)."""
    _write_manifest(tmp_path, {
        "01-auth::FR-01.01": _node("FR-01.01", ["e2e"], {"e2e": "ok"}),
        "02-other::FR-01.01": _node("FR-01.01", ["e2e"], {"e2e": "MISSING"}),
    })
    cells = _row(generate(_data(tmp_path, split="01-auth")))
    assert cells[11] == "?"  # collision → not credited


def test_legend_decodes_layer_columns(tmp_path):
    _write_manifest(tmp_path, {"01-auth::FR-01.01": _node("FR-01.01", ["unit"], {"unit": "ok"})})
    result = generate(_data(tmp_path))
    assert "Unit / Integration / E2E" in result
