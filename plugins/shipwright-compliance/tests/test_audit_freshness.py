"""Tests for the audit-report.md staleness marker (F4).

Routine compliance regens (update_compliance.py --phase <name>) refresh the
dashboard but not the detective audit-report.md; this marker announces that the
on-disk audit may be stale. The banner is keyed only to the audit's own
``Generated:`` timestamp, so re-stamping is byte-stable (no churn on repos that
track the report). run_audit.py rewrites the file from scratch, clearing it.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit.audit_adapters import (  # noqa: E402
    SOURCE_DETECTIVE_ONLY,
    Finding,
)
from scripts.audit.audit_detector import AuditReport  # noqa: E402
from scripts.audit.audit_report import render_markdown, write  # noqa: E402
from scripts.lib.audit_freshness import (  # noqa: E402
    AUDIT_REPORT_REL,
    mark_audit_report_stale,
)

_MARKER_START = "<!-- shipwright:audit-staleness:start -->"
_MARKER_END = "<!-- shipwright:audit-staleness:end -->"
_AUDIT_TS = "2026-05-01 00:00:00 UTC"


def _finding(**kw) -> Finding:
    defaults = dict(
        group="B", check_id="B7", name="demo", severity="HIGH",
        source=SOURCE_DETECTIVE_ONLY, status="fail", detail="",
    )
    defaults.update(kw)
    return Finding(**defaults)


def _write_report(root: Path) -> Path:
    """Write a deterministic on-disk audit-report.md (run_audit's shape)."""
    path = root / AUDIT_REPORT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# Shipwright Detective Audit\n\nGenerated: {_AUDIT_TS}\n"
        f"Project: `x`\n\n## Findings\n\n- ❌ **B7** demo\n",
        encoding="utf-8",
    )
    return path


def test_noop_when_absent(tmp_path):
    result = mark_audit_report_stale(tmp_path)
    assert result == {"stamped": False, "reason": "absent"}
    assert not (tmp_path / AUDIT_REPORT_REL).exists()


def test_stamps_when_present(tmp_path):
    path = _write_report(tmp_path)
    result = mark_audit_report_stale(tmp_path)
    assert result == {"stamped": True, "audit_generated": _AUDIT_TS}
    text = path.read_text(encoding="utf-8")
    assert _MARKER_START in text and _MARKER_END in text
    assert "Possibly stale" in text
    assert _AUDIT_TS in text  # banner references the audit's own Generated ts
    # Original audit content survives.
    assert "**B7**" in text
    assert "# Shipwright Detective Audit" in text


def test_idempotent_and_churn_free(tmp_path):
    path = _write_report(tmp_path)
    assert mark_audit_report_stale(tmp_path)["stamped"] is True
    first = path.read_text(encoding="utf-8")
    # Re-stamp: byte-identical content → no write, no churn (the MEDIUM fix).
    result2 = mark_audit_report_stale(tmp_path)
    assert result2 == {"stamped": False, "reason": "unchanged"}
    assert path.read_text(encoding="utf-8") == first
    # Markers appear exactly once (no stacking).
    assert first.count(_MARKER_START) == 1
    assert first.count(_MARKER_END) == 1


def test_fresh_render_has_no_marker(tmp_path):
    # run_audit.py writes via render_markdown — a freshly rendered report must
    # carry NO staleness banner.
    assert _MARKER_START not in render_markdown(AuditReport(findings=[_finding()]))
    # And re-running the audit (full overwrite) clears a prior banner.
    path = _write_report(tmp_path)
    mark_audit_report_stale(tmp_path)
    assert _MARKER_START in path.read_text(encoding="utf-8")
    write(AuditReport(findings=[_finding()]), tmp_path)  # simulate run_audit
    assert _MARKER_START not in path.read_text(encoding="utf-8")
