"""Audit-report rendering tests (plan v7, Step 9)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit.audit_adapters import (  # noqa: E402
    SOURCE_DETECTIVE_ONLY,
    SOURCE_PREVENTIVE_RERUN,
    Finding,
)
from scripts.audit.audit_detector import AuditReport  # noqa: E402
from scripts.audit.audit_report import (  # noqa: E402
    render_json,
    render_markdown,
    write,
)


def _finding(**kw) -> Finding:
    defaults = dict(
        group="A", check_id="A2", name="demo", severity="LOW",
        source=SOURCE_DETECTIVE_ONLY, status="pass", detail="",
    )
    defaults.update(kw)
    return Finding(**defaults)


def test_render_markdown_splits_preventive_and_detective():
    report = AuditReport(findings=[
        _finding(group="C", check_id="C2", source=SOURCE_PREVENTIVE_RERUN),
        _finding(group="B", check_id="B7", source=SOURCE_DETECTIVE_ONLY),
    ])
    md = render_markdown(report)
    assert "# Shipwright Detective Audit" in md
    assert "Preventive re-checks" in md
    assert "Detective-only checks" in md
    # Each finding appears under its own section
    p_idx = md.index("Preventive re-checks")
    d_idx = md.index("Detective-only checks")
    assert md.index("**C2**") < d_idx
    assert md.index("**B7**") > d_idx


def test_render_markdown_summary_table_counts():
    report = AuditReport(findings=[
        _finding(group="C", status="fail"),
        _finding(group="C", status="pass"),
        _finding(group="F", status="fail"),
    ])
    md = render_markdown(report)
    # Summary table has a row per group with per-status counts.
    assert "| C | 1 | 0 | 1 |" in md
    assert "| F | 1 | 0 | 0 |" in md


def test_render_markdown_includes_import_gate_error():
    report = AuditReport(import_gate_error="symbol X missing")
    md = render_markdown(report)
    assert "Import Gate Error" in md
    assert "symbol X missing" in md


def test_render_markdown_empty_findings_reports_none():
    report = AuditReport()
    md = render_markdown(report)
    assert "_(no findings collected)_" in md
    assert "_(none)_" in md


def test_render_markdown_orders_failures_first():
    report = AuditReport(findings=[
        _finding(group="C", check_id="C3", status="pass"),
        _finding(group="C", check_id="C2", status="fail"),
    ])
    md = render_markdown(report)
    # Fail precedes pass regardless of check_id order.
    assert md.index("**C2**") < md.index("**C3**")


def test_render_markdown_lists_groups_skipped():
    report = AuditReport(groups_skipped=[("A", "not-implemented"),
                                         ("B", "not-implemented")])
    md = render_markdown(report)
    assert "Groups Skipped" in md
    assert "**A** — not-implemented" in md
    assert "**B** — not-implemented" in md


def test_render_json_round_trip():
    report = AuditReport(findings=[
        _finding(source=SOURCE_PREVENTIVE_RERUN, status="fail"),
    ])
    parsed = json.loads(render_json(report))
    assert parsed["findings"][0]["source"] == SOURCE_PREVENTIVE_RERUN
    assert parsed["any_fail"] is True


def test_write_creates_both_artifacts(tmp_path):
    report = AuditReport(findings=[_finding(status="fail")])
    paths = write(report, tmp_path)
    assert set(paths) == {"md", "json"}
    assert paths["md"] == tmp_path / ".shipwright" / "compliance" / "audit-report.md"
    assert paths["json"] == tmp_path / "shipwright_audit_report.json"
    assert paths["md"].exists()
    assert paths["json"].exists()
    # JSON is valid + preserves source field
    parsed = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert parsed["findings"][0]["source"] == SOURCE_DETECTIVE_ONLY


def test_write_respects_format_flags(tmp_path):
    report = AuditReport()
    paths = write(report, tmp_path, markdown=False, json_out=True)
    assert set(paths) == {"json"}
    assert not (tmp_path / ".shipwright" / "compliance" / "audit-report.md").exists()


# ---------------------------------------------------------------------------
# End-to-end CLI integration
# ---------------------------------------------------------------------------


RUN_AUDIT = PLUGIN_ROOT / "scripts" / "audit" / "run_audit.py"


def test_run_audit_cli_writes_both_artifacts_by_default(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text("{}\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(RUN_AUDIT),
         "--project-root", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode in (0, 1), result.stderr
    payload = json.loads(result.stdout)
    # ``written`` map points at the on-disk artifacts.
    assert "written" in payload
    assert "md" in payload["written"]
    assert "json" in payload["written"]
    md_path = tmp_path / payload["written"]["md"]
    assert md_path.exists()
    assert "# Shipwright Detective Audit" in md_path.read_text(encoding="utf-8")


def test_run_audit_cli_respects_json_only_format(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text("{}\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(RUN_AUDIT),
         "--project-root", str(tmp_path), "--format", "json"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode in (0, 1), result.stderr
    payload = json.loads(result.stdout)
    assert set(payload["written"]) == {"json"}
    assert not (tmp_path / ".shipwright" / "compliance" / "audit-report.md").exists()
