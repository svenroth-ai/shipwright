"""Tests for report_model — the typed view-model + n/a semantics (GPT #12)."""

from __future__ import annotations

from types import SimpleNamespace

from report_model import build_report_model


def _dim(key, label, weight, score, detail="d"):
    status = "n/a" if score is None else ("ok" if score >= 0.9 else "gap")
    return SimpleNamespace(
        key=key, label=label, weight=weight, score=score,
        status=status, anchor="anchor", detail=detail,
    )


def _report(dims, *, grade="B", score=82.5):
    return SimpleNamespace(
        grade=grade, score=score, gradeable=True, verdict="Controlled.",
        band_label="Controlled, minor gaps.", dimensions=dims,
        reasons=["Change traceability: 1/3 linked"], verified_from="heuristic @ abc",
    )


def _routing(mode="heuristic", state="absent"):
    return SimpleNamespace(effective_mode=mode, state=state, reason="no .shipwright/")


def _build(dims, **kw):
    return build_report_model(
        grade_report=_report(dims, **kw), routing=_routing(),
        target_display="repo", head_sha="deadbeefcafe1234", events_truncated=False,
    )


class TestNaSemantics:
    def test_na_dimension_is_excluded_and_listed_as_would_light(self):
        dims = [
            _dim("requirement_traceability", "Requirement traceability", 0.25, 0.9),
            _dim("security", "Security", 0.10, None),
            _dim("change_reconciliation", "Change reconciliation", 0.15, None),
        ]
        model = _build(dims)
        assert model.measurable_count == 1
        assert model.na_count == 2
        assert "Security" in model.controls_shipwright_would_light
        assert "Change reconciliation" in model.controls_shipwright_would_light
        na = [d for d in model.dimensions if d.key == "security"][0]
        assert na.status == "n/a"
        assert na.score is None  # never coerced to 0
        assert na.would_light_up is True

    def test_na_provenance_is_unavailable_scored_is_heuristic(self):
        dims = [
            _dim("change_traceability", "Change traceability", 0.15, 0.6),
            _dim("maintainability", "Size / maintainability discipline", 0.10, None),
        ]
        model = _build(dims)
        scored = [d for d in model.dimensions if d.key == "change_traceability"][0]
        na = [d for d in model.dimensions if d.key == "maintainability"][0]
        assert scored.provenance.mode == "heuristic"
        assert scored.provenance.freshness == "deadbeefcafe"
        assert na.provenance.mode == "unavailable"
        assert na.provenance.freshness == "n/a"
        assert na.provenance.disabled_enrichments  # names what would light it

    def test_detail_override_applies(self):
        dims = [_dim("test_health", "Test health", 0.20, None, detail="engine detail")]
        model = build_report_model(
            grade_report=_report(dims), routing=_routing(),
            target_display="repo", head_sha="abc", events_truncated=False,
            detail_overrides={"test_health": "12 tests — present, not executed"},
            static_test_inventory="12 tests across 1 framework",
        )
        th = model.dimensions[0]
        assert th.detail == "12 tests — present, not executed"
        assert model.static_test_inventory == "12 tests across 1 framework"

    def test_honest_ceiling_note_present(self):
        model = _build([_dim("change_traceability", "Change traceability", 0.15, 1.0)])
        assert "does not verify behaviour" in model.honest_ceiling_note

    def test_features_truncated_labels_requirement_traceability_sampled(self):
        dims = [_dim("requirement_traceability", "Requirement traceability", 0.25, 0.9)]
        model = build_report_model(
            grade_report=_report(dims), routing=_routing(),
            target_display="repo", head_sha="abc", events_truncated=False,
            features_truncated=True,
        )
        prov = model.dimensions[0].provenance
        assert prov.sampled is True
        assert prov.truncated is True
