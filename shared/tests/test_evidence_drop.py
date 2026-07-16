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
    assert (d / "junit.xml").is_file()
    assert (d / "playwright.json").is_file()
    assert prov["run_id"] == "iterate-x" and prov["head_commit"] == "deadbeef"
    assert set(prov["reports"]) == {"junit", "playwright"}
    assert evidence_drop.read_provenance(tmp_path)["run_id"] == "iterate-x"


def test_stage_clears_prior_reports_first(tmp_path):
    d = evidence_drop.evidence_dir(tmp_path)
    d.mkdir(parents=True)
    (d / "vitest.json").write_text("STALE", encoding="utf-8")  # a prior run's leftover
    junit = _report(tmp_path, "junit.xml", "<testsuites/>")
    evidence_drop.stage_reports(tmp_path, run_id="iterate-new", junit=junit)
    # The stale vitest report is gone (cleared), not carried into this run.
    assert not (d / "vitest.json").is_file()
    assert (d / "junit.xml").is_file()


def test_missing_source_report_is_skipped_not_fabricated(tmp_path):
    prov = evidence_drop.stage_reports(
        tmp_path, run_id="iterate-x", junit=tmp_path / "does-not-exist.xml",
    )
    assert prov["reports"] == {}
    assert not (evidence_drop.evidence_dir(tmp_path) / "junit.xml").is_file()


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
    rc2 = evidence_drop.main(["clear", "--project-root", str(tmp_path)])
    assert rc2 == 0
    assert evidence_drop.read_provenance(tmp_path) is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
