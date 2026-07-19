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


def _write_manifest(tmp_path: Path, requirements: dict, **extra) -> None:
    path = tmp_path / ".shipwright" / "compliance" / "test-traceability.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 3, "collector_version": "test", "generated_at": "t",
        "source_commit": "x", "spec_hash": "h", "requirements": requirements,
        "orphans": [], "invalid_tags": [], "invalid_layers": [], "untagged_tests": [],
        **extra,
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
    _write_manifest(tmp_path, {"01::FR-01.01": _node("FR-01.01", ["unit"], {"unit": "ok"})})
    result = generate(_data(tmp_path))
    assert "| Unit | Integration | E2E |" in result


def test_unit_ok_e2e_missing_renders_glyphs_not_numbers(tmp_path):
    """AC1 — unit-but-no-E2E is visibly ``E2E: MISSING`` (a glyph, not a bare count)."""
    _write_manifest(tmp_path, {
        "01::FR-01.01": _node("FR-01.01", ["unit", "e2e"],
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
    _write_manifest(tmp_path, {"01::FR-01.01": _node("FR-01.01", ["unit"], {"unit": "ok"})})
    cells = _row(generate(_data(tmp_path)))
    assert cells[7] == "—"          # not behavior-touched
    assert cells[8] == "COVERED"    # tested event, gap<=0


def test_absent_manifest_renders_dashes(tmp_path):
    """No manifest → the FR isn't in the index → all three columns are — (graceful)."""
    cells = _row(generate(_data(tmp_path)))  # no _write_manifest
    assert cells[9] == "—"
    assert cells[10] == "—"
    assert cells[11] == "—"


def test_namespaced_key_resolves_this_rows_own_node(tmp_path):
    """The row matches its OWN namespace::FR entry — another FR does not bleed in."""
    _write_manifest(tmp_path, {
        "01::FR-01.01": _node("FR-01.01", ["e2e"], {"e2e": "ok"}),
        "02::FR-02.02": _node("FR-02.02", ["e2e"], {"e2e": "MISSING"}),
    })
    cells = _row(generate(_data(tmp_path, split="01-auth")))
    assert cells[11] == "ok"


def test_row_resolves_after_its_split_directory_is_renamed(tmp_path):
    """S3's whole point, at the RTM seam. The row's split is ``99-renamed-away`` and the
    manifest was written with no knowledge of it; under v2 the lookup was
    ``<split>::FR-01.01`` and this row would have missed its node and rendered ``—``."""
    _write_manifest(tmp_path, {"01::FR-01.01": _node("FR-01.01", ["e2e"], {"e2e": "ok"})})
    cells = _row(generate(_data(tmp_path, split="99-renamed-away")))
    assert cells[11] == "ok"


def test_collision_display_id_renders_ambiguous_not_ok(tmp_path):
    """MUST-FIX 2b — a display id shared by two nodes must not credit its fanned ``ok``.

    Under v3 the collector can no longer EMIT this (it fails closed on a duplicate id),
    so the remaining source is a hand-edited or stale artifact — which is exactly what a
    read-side guard is for, and why this stays covered rather than being deleted with the
    generator path that used to produce it."""
    _write_manifest(tmp_path, {
        "01::FR-01.01": _node("FR-01.01", ["e2e"], {"e2e": "ok"}),
        "02-other::FR-01.01": _node("FR-01.01", ["e2e"], {"e2e": "MISSING"}),
    })
    cells = _row(generate(_data(tmp_path, split="01-auth")))
    assert cells[11] == "?"  # shared display id → not credited


def test_node_whose_id_disagrees_with_its_key_is_still_a_collision(tmp_path):
    """``collision_ids`` node-counting is not dead under v3: a hand-edited manifest can
    still put two nodes on one display id by disagreeing with its own key."""
    _write_manifest(tmp_path, {
        "01::FR-01.01": _node("FR-01.01", ["e2e"], {"e2e": "ok"}),
        "02::FR-02.02": _node("FR-01.01", ["e2e"], {"e2e": "MISSING"}),
    })
    cells = _row(generate(_data(tmp_path, split="01-auth")))
    assert cells[11] == "?"


def test_local_key_derivation_matches_the_shared_model(tmp_path):
    """Drift guard: ``_rtm_layer_columns`` keeps a local copy of the key derivation so it
    stays dependency-light. Pin it to the shared original so the two cannot diverge.

    Loaded BY PATH rather than via ``sys.path.insert``: prepending
    ``shared/scripts/lib`` would make every module in it importable under a bare
    top-level name (``config``, ``state``, ``env``, ``errors``, ``spec_parser``) for the
    rest of the pytest session, and this plugin binds ``scripts.lib`` for its own
    modules (ADR-045). No collision is traced today, so that is a latent risk rather
    than a live bug — which is exactly when it is cheap to close."""
    import importlib.util  # noqa: PLC0415
    import sys  # noqa: PLC0415

    path = Path(__file__).resolve().parents[3] / "shared/scripts/lib/requirement_model.py"
    spec = importlib.util.spec_from_file_location("requirement_model", path)
    requirement_model = importlib.util.module_from_spec(spec)
    sys.modules["requirement_model"] = requirement_model  # dataclass resolves its module
    spec.loader.exec_module(requirement_model)

    from scripts.lib._rtm_layer_columns import _key_for_id  # noqa: PLC0415
    for fr in ("FR-01.01", "FR-42.99", "FR-07.02"):
        assert _key_for_id(fr) == requirement_model.key_for_id(fr)


def test_legend_decodes_layer_columns(tmp_path):
    _write_manifest(tmp_path, {"01::FR-01.01": _node("FR-01.01", ["unit"], {"unit": "ok"})})
    result = generate(_data(tmp_path))
    assert "Unit / Integration / E2E" in result
