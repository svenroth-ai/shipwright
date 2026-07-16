"""Pure-core cases for the two enforcing F11 traceability gates (TT5) that pin the
false-green / false-red reasoning on synthetic manifests — collision ADVISORY, legacy
ADVISORY, unknown-provenance HARD, could-not-determine WARN — plus the run_all_checks
wiring drift guards. Split from ``test_layer_coverage.py`` to keep each file ≤300 LOC.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from tools.verifiers._layer_coverage_core import (  # noqa: E402
    behavior_changed_keys,
    collision_display_ids,
    evaluate_cross_layer,
)
from tools.verifiers._layer_coverage_removal import evaluate_removal  # noqa: E402


def _node(disp, *, status="active", layers=("e2e",), source="explicit",
          coverage=None, priority="Must", tests=None):
    return {
        "id": disp, "spec_path": "", "title": f"t-{disp}", "priority": priority,
        "status": status, "required_layers": list(layers),
        "required_layers_source": source,
        "tests": tests or {}, "coverage": coverage or {},
    }


def _manifest(nodes: dict, *, spec_hash="sha256:x", orphans=None, untagged=None):
    return {
        "schema_version": 2, "spec_hash": spec_hash, "requirements": nodes,
        "orphans": orphans or [], "invalid_tags": [], "invalid_layers": [],
        "untagged_tests": untagged or [],
    }


def test_cross_layer_collision_id_is_advisory_not_hard():
    # FR-03.02 declared in two namespaces (collision). Even with no ok coverage the gap is
    # ADVISORY — a HARD block on a structurally-ambiguous collision id would be a false-red.
    base = _manifest({
        "a::FR-03.02": _node("FR-03.02"), "b::FR-03.02": _node("FR-03.02"),
    })
    head = _manifest({
        "a::FR-03.02": _node("FR-03.02", coverage={"e2e": "MISSING"}),
        "b::FR-03.02": _node("FR-03.02", coverage={"e2e": "MISSING"}),
    }, spec_hash="sha256:y")
    assert "FR-03.02" in collision_display_ids(head)
    head["requirements"]["a::FR-03.02"]["title"] = "changed"  # force a behaviour change
    v = evaluate_cross_layer(base, head)
    assert not v.any_fail and v.advisory


def test_cross_layer_legacy_provenance_is_advisory():
    base = _manifest({"a::FR-05.01": _node("FR-05.01", source="defaulted_legacy")})
    head = _manifest({
        "a::FR-05.01": _node("FR-05.01", source="defaulted_legacy",
                              coverage={"e2e": "MISSING"}, layers=("e2e",)),
    }, spec_hash="sha256:y")
    head["requirements"]["a::FR-05.01"]["title"] = "changed"
    v = evaluate_cross_layer(base, head)
    assert not v.any_fail and v.advisory  # pre-rollout legacy → advisory, never blocks


def test_cross_layer_unknown_provenance_is_hard():
    base = _manifest({"a::FR-05.01": _node("FR-05.01", source="__weird__")})
    head = _manifest({
        "a::FR-05.01": _node("FR-05.01", source="__weird__", coverage={"e2e": "MISSING"}),
    }, spec_hash="sha256:y")
    head["requirements"]["a::FR-05.01"]["title"] = "changed"
    v = evaluate_cross_layer(base, head)
    assert v.any_fail  # unknown provenance token → fail-closed HARD (not silently advisory)


def test_cross_layer_could_not_determine_when_spec_changed_but_no_fr():
    base = _manifest({"a::FR-01.01": _node("FR-01.01")}, spec_hash="sha256:x")
    head = _manifest({}, spec_hash="sha256:CHANGED")  # spec changed, zero parseable FRs
    v = evaluate_cross_layer(base, head)
    assert v.could_not_determine and not v.changed_keys


def test_cross_layer_could_not_determine_when_spec_changed_but_no_row_delta():
    # External-review MUST-FIX: a spec delta that leaves every FR row identical is
    # undeterminable (could be a behavioural AC edit under an unchanged row), NOT a silent
    # pass — the manifest cannot see AC prose, so it WARNs for a human to adjudicate.
    base = _manifest({"a::FR-01.01": _node("FR-01.01")}, spec_hash="sha256:x")
    head = _manifest({"a::FR-01.01": _node("FR-01.01")}, spec_hash="sha256:CHANGED")
    v = evaluate_cross_layer(base, head)
    assert v.could_not_determine and not v.changed_keys


def test_cross_layer_identical_specs_no_cnd():
    base = _manifest({}, spec_hash="sha256:same")
    head = _manifest({}, spec_hash="sha256:same")
    assert not evaluate_cross_layer(base, head).could_not_determine


def test_advisory_only_verdicts_surface_as_warning_not_green():
    # External-review MUST-FIX: a legacy/collision advisory gap must NOT read as a clean
    # green PASS — it surfaces as a non-blocking WARNING so the gap is visible.
    from tools.verifiers.common import Severity
    from tools.verifiers.layer_coverage import _cross_layer_result, _removal_result

    head_legacy = _manifest({
        "a::FR-05.01": _node("FR-05.01", source="defaulted_legacy",
                             coverage={"e2e": "MISSING"}),
    }, spec_hash="sha256:y")
    head_legacy["requirements"]["a::FR-05.01"]["title"] = "changed"
    xl = evaluate_cross_layer(
        _manifest({"a::FR-05.01": _node("FR-05.01", source="defaulted_legacy")}),
        head_legacy,
    )
    xl_res = _cross_layer_result("x", xl)
    assert xl_res.ok is False and xl_res.severity == Severity.WARNING.value

    rm = evaluate_removal(
        _manifest({"a::FR-07.07": _node("FR-07.07",
                   tests={"e2e": [{"path": "e2e/x::t", "id": "e2e/x::t"}]}),
                   "b::FR-07.07": _node("FR-07.07")}),
        _manifest({"a::FR-07.07": _node("FR-07.07", status="removed"),
                   "b::FR-07.07": _node("FR-07.07")},
                  orphans=[{"test": "e2e/x::t", "tagged_fr": "FR-07.07",
                            "reason": "fr_removed", "category": "confirmed_orphan"}]),
    )
    rm_res = _removal_result("r", rm)
    assert rm_res.ok is False and rm_res.severity == Severity.WARNING.value


def test_removal_collision_id_demotes_hard_to_advisory():
    # FR-07.07 removed in ns-a but still ACTIVE in ns-b (collision). A base-linked test
    # still tagged @FR-07.07 could legitimately cover ns-b's FR → advisory, not a false-red.
    base = _manifest({
        "a::FR-07.07": _node("FR-07.07", status="active",
                             tests={"e2e": [{"path": "e2e/x.spec.ts::t", "id": "e2e/x.spec.ts::t"}]}),
        "b::FR-07.07": _node("FR-07.07", status="active"),
    })
    head = _manifest({
        "a::FR-07.07": _node("FR-07.07", status="removed"),
        "b::FR-07.07": _node("FR-07.07", status="active"),
    }, orphans=[{"test": "e2e/x.spec.ts::t", "tagged_fr": "FR-07.07",
                 "reason": "fr_removed", "category": "confirmed_orphan"}])
    v = evaluate_removal(base, head)
    assert "a::FR-07.07" in v.removed_frs
    assert not v.any_fail and v.advisory  # collision → advisory, not HARD


def test_removal_absent_key_does_not_trigger():
    # External-review MUST-FIX: a base-active FR merely ABSENT at head (deletion / relocation
    # / parse hiccup), NOT in a ## Removed Requirements row, must not trigger the gate.
    base = _manifest({"a::FR-01.01": _node("FR-01.01",
                     tests={"e2e": [{"path": "e2e/x::t", "id": "e2e/x::t"}]})})
    v = evaluate_removal(base, _manifest({}))
    assert not v.removed_frs and not v.any_fail


def test_removal_namespace_relocation_does_not_trigger():
    base = _manifest({"a::FR-01.01": _node("FR-01.01")})
    head = _manifest({"b::FR-01.01": _node("FR-01.01")})  # same display id, new namespace, active
    assert not evaluate_removal(base, head).removed_frs


_JUNIT_ONE = (
    '<testsuites><testsuite name="pytest" tests="1" failures="0">'
    '<testcase classname="tests.x" name="test_a" file="tests/x.py"/>'
    "</testsuite></testsuites>"
)


def _evio():
    from tools.verifiers._layer_coverage_regen import _load_collector  # noqa: PLC0415

    return _load_collector()[2]


def _stage_junit(root: Path, run_id: str, body: str) -> None:
    from lib import evidence_drop  # noqa: PLC0415

    junit = root / "junit.xml"
    junit.write_text(body, encoding="utf-8")
    # head_commit mandatory; no git here so commit_hash="" skips the ancestor check.
    evidence_drop.stage_reports(root, run_id=run_id, head_commit="deadbeef", junit=junit)


def test_fresh_evidence_builds_from_reports_ignoring_planted_index(tmp_path):
    # MUST-FIX 2 (R3 for evidence): the gate BUILDS the index in-memory from the staged raw
    # report and NEVER reads a persisted one — a planted stale PASS is not even consulted.
    from tools.verifiers._layer_coverage_evidence import fresh_evidence  # noqa: PLC0415

    _stage_junit(tmp_path, "r", _JUNIT_ONE)
    idx = tmp_path / ".shipwright" / "compliance" / "test-evidence-index.json"
    idx.write_text(json.dumps({
        "schema_version": 2, "source_reports": [".shipwright/compliance/evidence/junit.xml"],
        "results": {"stale::x": {"status": "enabled", "executed": "pass"}},
    }), encoding="utf-8")
    ev = fresh_evidence(tmp_path, "r", "", _evio())
    assert "tests/x.py::test_a" in ev and "stale::x" not in ev


def test_fresh_evidence_ignores_repo_root_report_fallback(tmp_path):
    # MUST-FIX 2: only the provenance-STAGED report under .shipwright/compliance/evidence/ is
    # read — a prior run's repo-ROOT test-results.json (which refresh_index would ingest) is
    # NOT consulted, so its passing e2e can never leak in.
    from tools.verifiers._layer_coverage_evidence import fresh_evidence  # noqa: PLC0415

    _stage_junit(tmp_path, "r", _JUNIT_ONE)  # stages junit-only (no e2e)
    (tmp_path / "test-results.json").write_text(json.dumps({  # stale root playwright report
        "suites": [{"title": "e.spec.ts", "file": "e2e/e.spec.ts", "specs": [
            {"title": "leaks", "ok": True,
             "tests": [{"status": "expected", "results": [{"status": "passed"}]}]}]}],
    }), encoding="utf-8")
    ev = fresh_evidence(tmp_path, "r", "", _evio())
    assert "tests/x.py::test_a" in ev
    assert not any("e2e/e.spec.ts" in k for k in ev)  # root fallback NOT ingested


def test_fresh_evidence_empty_when_no_report_staged(tmp_path):
    from lib import evidence_drop  # noqa: PLC0415
    from tools.verifiers._layer_coverage_evidence import fresh_evidence  # noqa: PLC0415

    evidence_drop.stage_reports(tmp_path, run_id="r", head_commit="x")  # provenance, no reports
    assert fresh_evidence(tmp_path, "r", "", _evio()) == {}


def test_behavior_changed_keys_new_fr_and_layer_change():
    base = _manifest({"a::FR-01.01": _node("FR-01.01", layers=("unit",))})
    head = _manifest({
        "a::FR-01.01": _node("FR-01.01", layers=("unit", "e2e")),  # layer added
        "a::FR-01.02": _node("FR-01.02"),                          # new FR
    })
    assert set(behavior_changed_keys(base, head)) == {"a::FR-01.01", "a::FR-01.02"}


# --- run_all_checks wiring drift guards ------------------------------------


def test_safe_extract_rejects_path_traversal(tmp_path, monkeypatch):
    # External-review finding: the 3.11 tar fallback must reject a `../escape` member — a
    # string prefix check would let a sibling dir through, so it uses path containment.
    import io as _io
    import tarfile

    from tools.verifiers import _layer_coverage_regen as reg

    buf = _io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name in ("ok.txt", "../escape.txt"):
            info = tarfile.TarInfo(name)
            info.size = 1
            tar.addfile(info, _io.BytesIO(b"x"))
    buf.seek(0)
    dest = tmp_path / "dest"
    dest.mkdir()
    orig = tarfile.TarFile.extractall

    def _no_filter(self, path=None, members=None, **kw):
        if "filter" in kw:
            raise TypeError("simulated pre-3.11.4 (no data filter)")
        return orig(self, path, members)

    monkeypatch.setattr(tarfile.TarFile, "extractall", _no_filter)
    with tarfile.open(fileobj=buf) as tar:
        reg._safe_extract(tar, dest)
    assert (dest / "ok.txt").is_file()
    assert not (tmp_path / "escape.txt").exists()  # traversal blocked


def test_both_gates_registered_in_run_all_checks(tmp_path):
    from tools.verifiers.iterate_checks import run_all_checks

    names = [r.name for r in run_all_checks(tmp_path, "r1", commit_hash="abc1234")]
    assert any("removal coverage" in n for n in names), names
    assert any("cross-layer coverage" in n for n in names), names


def test_gates_skip_cleanly_below_medium(tmp_path):
    # A non-git, non-medium project → both gates SKIP (ok=True), never crash / false-fail.
    from tools.verifiers.layer_coverage import (
        check_cross_layer_coverage,
        check_removal_coverage,
    )

    for fn in (check_removal_coverage, check_cross_layer_coverage):
        r = fn(tmp_path, "r-missing", "abc1234")
        assert r.ok is True and r.is_skipped


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
