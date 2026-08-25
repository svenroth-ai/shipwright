"""Tests for the execution-evidence emit-side (TT5 carry-forward from TT-EV).

Pins the provenance freshness contract the cross-layer gate relies on: a run stages its
reports + a run_id-stamped sidecar; the dir is cleared first so a prior run's report
cannot survive; and ``evidence_is_fresh`` is fail-closed for a missing/mismatched sidecar.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib import evidence_drop  # noqa: E402


def _report(tmp: Path, name: str, body: str) -> Path:
    p = tmp / name
    p.write_text(body, encoding="utf-8")
    return p


def test_stage_copies_reports_and_writes_provenance(tmp_path):
    junit = _report(tmp_path, "junit.xml", "<testsuites/>")
    pw = _report(tmp_path, "pw.json", "{}")
    prov = evidence_drop.stage_reports(
        tmp_path, run_id="iterate-x", head_commit="deadbeef",
        junit=junit, playwright=pw,
    )
    d = evidence_drop.evidence_dir(tmp_path)
    # Legacy single-report form still stages as junit-01.xml (E-B: uniform naming so
    # refresh_index/_layer_coverage_evidence have exactly one convention to read).
    assert (d / "junit-01.xml").is_file()
    assert (d / "playwright.json").is_file()
    assert prov["run_id"] == "iterate-x" and prov["head_commit"] == "deadbeef"
    assert set(prov["reports"]) == {"junit", "playwright"}
    assert prov["reports"]["junit"] == [
        {"name": "junit-01.xml", "base": "", "mtime": prov["reports"]["junit"][0]["mtime"]}
    ]
    assert evidence_drop.read_provenance(tmp_path)["run_id"] == "iterate-x"


def test_stage_clears_prior_reports_first(tmp_path):
    d = evidence_drop.evidence_dir(tmp_path)
    d.mkdir(parents=True)
    (d / "vitest.json").write_text("STALE", encoding="utf-8")  # a prior run's leftover
    (d / "junit-03.xml").write_text("STALE", encoding="utf-8")  # a wider prior run's leftover
    junit = _report(tmp_path, "junit.xml", "<testsuites/>")
    evidence_drop.stage_reports(tmp_path, run_id="iterate-new", junit=junit)
    # The stale reports are gone (cleared), not carried into this run.
    assert not (d / "vitest.json").is_file()
    assert not (d / "junit-03.xml").is_file()
    assert (d / "junit-01.xml").is_file()


def test_stage_multiple_junit_reports_are_byte_identical_and_indexed(tmp_path):
    # E-A: raw reports are staged byte-identical, never rewritten. E-B: N reports land
    # as junit-01.xml .. junit-NN.xml, each with its base recorded in provenance.
    r1 = _report(tmp_path, "shared.xml", "<testsuites><testsuite/></testsuites>")
    r2 = _report(tmp_path, "compliance.xml", "<testsuites><testsuite id='x'/></testsuites>")
    prov = evidence_drop.stage_reports(
        tmp_path, run_id="iterate-multi",
        junit_reports=[("", r1), ("plugins/shipwright-compliance", r2)],
    )
    d = evidence_drop.evidence_dir(tmp_path)
    assert (d / "junit-01.xml").read_bytes() == r1.read_bytes()
    assert (d / "junit-02.xml").read_bytes() == r2.read_bytes()
    assert not (d / "junit.xml").exists()  # no longer a single conventional name
    entries = prov["reports"]["junit"]
    assert [e["name"] for e in entries] == ["junit-01.xml", "junit-02.xml"]
    assert [e["base"] for e in entries] == ["", "plugins/shipwright-compliance"]


def test_stage_missing_junit_report_in_a_multi_call_is_skipped_not_fabricated(tmp_path):
    r1 = _report(tmp_path, "shared.xml", "<testsuites/>")
    prov = evidence_drop.stage_reports(
        tmp_path, run_id="iterate-partial",
        junit_reports=[("", r1), ("plugins/ghost", tmp_path / "does-not-exist.xml")],
    )
    entries = prov["reports"]["junit"]
    # Only the report that actually exists is staged; the numbering is not padded
    # with a gap for the missing one, mirroring the existing single-report skip rule.
    assert [e["name"] for e in entries] == ["junit-01.xml"]
    assert [e["base"] for e in entries] == [""]


def test_clear_sweeps_every_junit_dash_n_file(tmp_path):
    d = evidence_drop.evidence_dir(tmp_path)
    d.mkdir(parents=True)
    for name in ("junit-01.xml", "junit-02.xml", "junit-18.xml"):
        (d / name).write_text("STALE", encoding="utf-8")
    evidence_drop.clear_evidence_reports(tmp_path)
    assert not any(d.glob(evidence_drop.JUNIT_GLOB))


def test_missing_source_report_is_skipped_not_fabricated(tmp_path):
    prov = evidence_drop.stage_reports(
        tmp_path, run_id="iterate-x", junit=tmp_path / "does-not-exist.xml",
    )
    assert prov["reports"] == {}
    assert not (evidence_drop.evidence_dir(tmp_path) / "junit.xml").is_file()
    assert not (evidence_drop.evidence_dir(tmp_path) / "junit-01.xml").is_file()


def test_evidence_is_fresh_matches_run_id(tmp_path):
    junit = _report(tmp_path, "junit.xml", "<testsuites/>")
    evidence_drop.stage_reports(tmp_path, run_id="iterate-A", junit=junit)
    assert evidence_drop.evidence_is_fresh(tmp_path, "iterate-A") is True
    # A different run's evidence must read as NOT fresh (fail-closed).
    assert evidence_drop.evidence_is_fresh(tmp_path, "iterate-B") is False


def test_evidence_is_fresh_false_without_provenance(tmp_path):
    assert evidence_drop.evidence_is_fresh(tmp_path, "iterate-A") is False


def test_evidence_is_fresh_false_when_no_report_staged(tmp_path):
    evidence_drop.stage_reports(tmp_path, run_id="iterate-A")  # provenance, but no reports
    assert evidence_drop.evidence_is_fresh(tmp_path, "iterate-A") is False


def test_clear_is_idempotent_on_missing_dir(tmp_path):
    evidence_drop.clear_evidence_reports(tmp_path)  # no dir yet — must not raise
    assert not evidence_drop.evidence_dir(tmp_path).exists()


def test_clear_also_removes_the_normalized_index(tmp_path):
    # External-review MUST-FIX: the gate consumes test-evidence-index.json, so clearing
    # only the reports would let a stale index survive beside a fresh sidecar. Clear must
    # invalidate the index too, so a missing refresh_index run reads as empty (fail-closed).
    index = evidence_drop.evidence_dir(tmp_path).parent / "test-evidence-index.json"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text('{"schema_version": 2, "results": {}}', encoding="utf-8")
    evidence_drop.clear_evidence_reports(tmp_path)
    assert not index.is_file()


def test_cli_clear_and_stage(tmp_path):
    junit = _report(tmp_path, "junit.xml", "<testsuites/>")
    rc = evidence_drop.main([
        "stage", "--project-root", str(tmp_path), "--run-id", "iterate-cli",
        "--junit", str(junit), "--head-commit", "abc123",
    ])
    assert rc == 0
    prov = evidence_drop.read_provenance(tmp_path)
    assert prov["run_id"] == "iterate-cli"
    assert prov["reports"]["junit"][0]["base"] == ""
    rc2 = evidence_drop.main(["clear", "--project-root", str(tmp_path)])
    assert rc2 == 0
    assert evidence_drop.read_provenance(tmp_path) is None


def test_cli_stage_repeatable_junit_with_explicit_bases(tmp_path):
    r1 = _report(tmp_path, "shared.xml", "<testsuites/>")
    r2 = _report(tmp_path, "compliance.xml", "<testsuites/>")
    rc = evidence_drop.main([
        "stage", "--project-root", str(tmp_path), "--run-id", "iterate-cli-multi",
        "--junit", f"={r1}",
        "--junit", f"plugins/shipwright-compliance={r2}",
    ])
    assert rc == 0
    prov = evidence_drop.read_provenance(tmp_path)
    entries = prov["reports"]["junit"]
    assert [e["base"] for e in entries] == ["", "plugins/shipwright-compliance"]
    assert [e["name"] for e in entries] == ["junit-01.xml", "junit-02.xml"]


def test_cli_stage_rejects_a_bare_junit_path_among_multiple(tmp_path):
    # AC: a report given without an explicit base once the call is unambiguously
    # multi-report is REJECTED, never silently defaulted to the project root.
    r1 = _report(tmp_path, "shared.xml", "<testsuites/>")
    r2 = _report(tmp_path, "compliance.xml", "<testsuites/>")
    with pytest.raises(SystemExit):
        evidence_drop.main([
            "stage", "--project-root", str(tmp_path), "--run-id", "iterate-cli-bad",
            "--junit", str(r1),       # bare — fine alone, but NOT alone here
            "--junit", f"plugins/x={r2}",
        ])


def test_cli_stage_allows_a_repeated_base_with_distinct_paths(tmp_path):
    # Stage-2 review: a duplicate BASE is legal and common — this repo has FOUR
    # roots that all rebase at base "". Staged entries are an ordered list of
    # {name, base}; nothing is keyed by base, so nothing silently "wins".
    r1 = _report(tmp_path, "a.xml", "<testsuites/>")
    r2 = _report(tmp_path, "b.xml", "<testsuites/>")
    rc = evidence_drop.main([
        "stage", "--project-root", str(tmp_path), "--run-id", "iterate-dup",
        "--junit", f"plugins/x={r1}",
        "--junit", f"plugins/x={r2}",
    ])
    assert rc == 0
    entries = evidence_drop.read_provenance(tmp_path)["reports"]["junit"]
    assert [e["base"] for e in entries] == ["plugins/x", "plugins/x"]
    assert [e["name"] for e in entries] == ["junit-01.xml", "junit-02.xml"]


def test_cli_stage_rejects_the_exact_same_base_and_path_twice(tmp_path):
    # An exact duplicate (base, path) pair is a copy-paste mistake, not a
    # legitimate multi-root call — still rejected.
    r1 = _report(tmp_path, "a.xml", "<testsuites/>")
    r2 = _report(tmp_path, "b.xml", "<testsuites/>")
    with pytest.raises(SystemExit):
        evidence_drop.main([
            "stage", "--project-root", str(tmp_path), "--run-id", "iterate-dup",
            "--junit", f"plugins/x={r1}",
            "--junit", f"plugins/x={r1}",
            "--junit", f"plugins/y={r2}",
        ])


def test_cli_stage_rejects_the_same_source_path_under_different_bases(tmp_path):
    # The identical physical report file staged twice (even under different
    # bases) is still a mistake — reject on the source path alone.
    r1 = _report(tmp_path, "a.xml", "<testsuites/>")
    with pytest.raises(SystemExit):
        evidence_drop.main([
            "stage", "--project-root", str(tmp_path), "--run-id", "iterate-dup",
            "--junit", f"plugins/x={r1}",
            "--junit", f"plugins/y={r1}",
        ])


def test_clear_removes_pre_e_b_legacy_junit_xml(tmp_path):
    # External-review finding: a run staged before this iterate could have left a
    # single evidence/junit.xml behind; clear must sweep it too, or a fresh run that
    # produces zero staged reports would have discover_reports fall back to it.
    d = evidence_drop.evidence_dir(tmp_path)
    d.mkdir(parents=True)
    (d / "junit.xml").write_text("STALE-LEGACY", encoding="utf-8")
    evidence_drop.clear_evidence_reports(tmp_path)
    assert not (d / "junit.xml").is_file()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
