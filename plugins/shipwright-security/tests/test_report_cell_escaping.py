"""F32 — pipe/newline-escaping of scanner/repo-controlled report cells.

``generate_security_report.py`` renders findings into GitHub-flavored Markdown
tables with f-string row templates. A scanner-controlled finding description, a
repo file path, or a rule id containing a literal ``|`` (or a newline) splits
the row into extra columns — breaking or spoofing the summary. The --pr-mode
report is posted verbatim as a GitHub PR comment, so an attacker-influenceable
value (e.g. a workflow ``name:`` or a crafted dependency advisory string) could
forge the table a reviewer reads.

The fix routes every scanner/repo-controlled cell through the SSoT
``markdown_table.escape_cell``. These tests are the round-trip guard: a value
carrying ``|`` / newline must not change the rendered column count and must
appear in its escaped (``\\|``) form, never verbatim.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "tools"))

import generate_security_report as report_gen  # noqa: E402


def _table_columns(row: str) -> int:
    """Column count of a GFM table row, treating ``\\|`` (the escaped form) as a
    literal pipe rather than a cell separator."""
    body = row.strip().strip("|")
    return len(body.replace("\\|", "\x00").split("|"))


def _findings_row(report: str, header_fragment: str) -> tuple[str, str]:
    """Return (header_row, first_data_row) for the findings table whose header
    line contains ``header_fragment``."""
    lines = [ln for ln in report.splitlines() if ln.strip().startswith("|")]
    for idx, ln in enumerate(lines):
        if header_fragment in ln:
            # header, separator (|---|---|), then the first data row
            return ln, lines[idx + 2]
    raise AssertionError(f"no findings table with header {header_fragment!r} in:\n{report}")


# A finding whose every free-text cell carries a pipe and/or a newline.
_MALICIOUS = {
    "severity": "high",
    "type": "secret_detection",
    "rule": "rule|with|pipes",
    "affected_file": "src/a|b.py",
    "affected_line": 12,
    "description": "leaked | secret\nsecond | line",
    "_remediation_status": "open",
}


def test_pr_report_row_not_column_shifted():
    report = report_gen.generate_pr_report([dict(_MALICIOUS)], repo_name="o/r")
    header, data = _findings_row(report, "Description")
    assert _table_columns(data) == _table_columns(header)
    # Raw pipes are escaped, not passed through verbatim.
    assert "rule|with|pipes" not in report
    assert "rule\\|with\\|pipes" in report
    # The embedded newline did not split the row into a second physical line.
    assert "second | line" not in report


def test_standard_report_row_not_column_shifted():
    report = report_gen.generate_standard_report([dict(_MALICIOUS)])
    header, data = _findings_row(report, "Title")
    assert _table_columns(data) == _table_columns(header)
    assert "src/a|b.py" not in report
    assert "src/a\\|b.py" in report


def test_benign_findings_render_unchanged():
    """Escaping must be a no-op for ordinary values — no stray backslashes."""
    benign = {
        "severity": "medium",
        "type": "sca",
        "rule": "CVE-2025-0001",
        "affected_file": "uv.lock",
        "description": "Vulnerable dependency.",
        "_remediation_status": "open",
    }
    report = report_gen.generate_standard_report([dict(benign)])
    assert "CVE-2025-0001" in report
    assert "uv.lock" in report
    assert "\\|" not in report  # nothing to escape → no escape artifacts
