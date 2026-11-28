"""R4 — one source for "when did the audit last run?".

audit-report.md, audit-report.json and the tracked record all carry the date of
the SAME run (one instant minted per run). Tracked documents (dashboard, every
provenance header) read ONLY the tracked record; the local, gitignored json feeds
just the md's own staleness banner.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit.audit_adapters import SOURCE_DETECTIVE_ONLY, Finding  # noqa: E402
from scripts.audit.audit_detector import AuditReport  # noqa: E402
from scripts.audit.audit_report import write  # noqa: E402
from scripts.audit.run_audit import main as run_audit_main  # noqa: E402
from scripts.lib._audit_disclosure_render import (  # noqa: E402
    freshness_note,
    render_consistency_audit,
)
from scripts.lib.audit_disclosure import record_audit_run  # noqa: E402
from scripts.lib.audit_freshness import (  # noqa: E402
    AUDIT_REPORT_REL,
    mark_audit_report_stale,
)

pytestmark = pytest.mark.covers("FR-01.10")

RAN_AT = "2026-07-28T09:30:00+00:00"
JSON_REL = ".shipwright/compliance/audit-report.json"


def _report(ran_at=RAN_AT) -> AuditReport:
    f = Finding(group="B", check_id="B7", name="demo", severity="HIGH",
                source=SOURCE_DETECTIVE_ONLY, status="pass", detail="")
    return AuditReport(findings=[f], groups_run=["B"], ran_at=ran_at)


def _run(root: Path, ran_at=RAN_AT) -> dict:
    report = _report(ran_at)
    paths = write(report, root)
    record_audit_run(root, statuses=["pass"], any_fail=False, ran_at=report.ran_at)
    return paths


def _dash(root: Path) -> str:
    return "\n".join(render_consistency_audit(root, as_of=RAN_AT))


def _md(root: Path) -> str:
    return (root / AUDIT_REPORT_REL).read_text(encoding="utf-8")


def test_md_json_and_dashboard_show_the_same_date(tmp_path):
    paths = _run(tmp_path)
    js = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert js["ran_at"] == RAN_AT
    assert "Generated: 2026-07-28 09:30:00 UTC" in paths["md"].read_text(encoding="utf-8")
    assert "2026-07-28" in _dash(tmp_path)


def test_write_mints_one_instant_when_report_has_none(tmp_path):
    report = _report(ran_at=None)
    paths = write(report, tmp_path)
    js = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert js["ran_at"] == report.ran_at
    assert f"Generated: {js['ran_at'][:10]}" in paths["md"].read_text(encoding="utf-8")


def test_newer_local_json_changes_no_tracked_document(tmp_path):
    _run(tmp_path, ran_at="2026-06-14T00:00:00+00:00")
    before = (_dash(tmp_path), freshness_note(tmp_path, as_of=RAN_AT))
    write(_report(), tmp_path, markdown=False)  # a newer LOCAL json, record untouched
    assert (_dash(tmp_path), freshness_note(tmp_path, as_of=RAN_AT)) == before
    assert "2026-06-14" in before[0] and "2026-07-28" not in before[0]


def test_dashboard_without_json_reads_the_tracked_record(tmp_path):
    _run(tmp_path)
    (tmp_path / JSON_REL).unlink()
    assert "2026-07-28" in _dash(tmp_path)


def test_stale_md_older_than_the_record_is_flagged(tmp_path):
    _run(tmp_path, ran_at="2026-06-14T00:00:00+00:00")
    write(_report(), tmp_path, markdown=False)  # json-only run: stamps the old md
    mark_audit_report_stale(tmp_path)  # idempotent
    assert "Generated: 2026-06-14" in _md(tmp_path)
    assert "a newer audit run is on record (2026-07-28)" in _md(tmp_path)


def test_current_md_gets_no_newer_run_claim(tmp_path):
    _run(tmp_path)
    mark_audit_report_stale(tmp_path)
    assert "newer audit run" not in _md(tmp_path)


def test_stale_json_and_md_under_a_newer_tracked_record_are_flagged(tmp_path):
    _run(tmp_path, ran_at="2026-06-14T00:00:00+00:00")
    record_audit_run(tmp_path, statuses=["pass"], any_fail=False, ran_at=RAN_AT)  # pulled
    mark_audit_report_stale(tmp_path)
    assert "a newer audit run is on record (2026-07-28)" in _md(tmp_path)


def test_unparseable_generated_degrades_to_stale_date_unknown(tmp_path):
    _run(tmp_path)
    md = tmp_path / AUDIT_REPORT_REL
    md.write_text("# R\n\nGenerated: garbage\n\nbody\n", encoding="utf-8")
    write(_report("2026-08-02T00:00:00+00:00"), tmp_path, markdown=False)
    md.write_text("# R\n\nGenerated: garbage\n\nbody\n", encoding="utf-8")
    assert mark_audit_report_stale(tmp_path)["stamped"] is True
    assert "newer audit run is on record (2026-08-02)" in _md(tmp_path)


def test_fractional_second_run_is_not_flagged_against_its_own_md(tmp_path):
    _run(tmp_path, ran_at="2026-07-28T09:30:00.654321+00:00")
    mark_audit_report_stale(tmp_path)
    assert "newer audit run" not in _md(tmp_path)


def test_non_utc_run_renders_as_utc_and_is_not_flagged(tmp_path):
    ran = "2026-07-28T01:30:00+02:00"  # 2026-07-27 23:30 UTC
    _run(tmp_path, ran_at=ran)
    assert "Generated: 2026-07-27 23:30:00 UTC" in _md(tmp_path)
    assert "2026-07-27" in "\n".join(render_consistency_audit(tmp_path, as_of=ran))
    mark_audit_report_stale(tmp_path)
    assert "newer audit run" not in _md(tmp_path)
    # the banner names a UTC day too: 01:30+02:00 on the 29th is still the 28th UTC
    record_audit_run(tmp_path, statuses=["pass"], any_fail=False,
                     ran_at="2026-07-29T01:30:00+02:00")
    mark_audit_report_stale(tmp_path)
    assert "a newer audit run is on record (2026-07-28)" in _md(tmp_path)


def test_json_for_an_empty_run_or_without_findings_list_is_ignored(tmp_path):
    _run(tmp_path, ran_at="2026-06-14T00:00:00+00:00")
    js = tmp_path / JSON_REL
    for patch in ({"groups_run": []}, {"findings": "oops"}):
        data = {"ran_at": RAN_AT, "groups_run": ["B"], "findings": [], **patch}
        js.write_text(json.dumps(data), encoding="utf-8")
        mark_audit_report_stale(tmp_path)
        assert "newer audit run" not in _md(tmp_path)


def test_only_typo_run_changes_neither_dashboard_nor_banner(tmp_path):
    _run(tmp_path, ran_at="2026-06-14T00:00:00+00:00")
    before = (_dash(tmp_path), _md(tmp_path))
    run_audit_main(["--project-root", str(tmp_path), "--only", "Z"])
    assert _dash(tmp_path) == before[0]
    assert _md(tmp_path) == before[1]  # the valid md is not overwritten
    mark_audit_report_stale(tmp_path)
    assert "newer audit run" not in _md(tmp_path)
    assert json.loads((tmp_path / JSON_REL).read_text(encoding="utf-8"))["ran_at"].startswith("2026-06-14")
