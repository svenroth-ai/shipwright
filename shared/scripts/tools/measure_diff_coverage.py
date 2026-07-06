#!/usr/bin/env python3
"""Diff-coverage measurement + gate tool (diff-coverage roadmap).

Reads a ``coverage.xml`` (overall line-rate -> ``total``) and a ``diff-cover``
JSON report (``diff`` = % of changed lines vs the compare-branch that tests
execute) and writes a **gitignored transient**
``.shipwright/coverage/diff_coverage.json`` — a grade-neutral Test-Health INFO
line in the compliance dashboard.

Boundary: ``diff`` is PR-local (changed lines vs merge-base), so it lives ONLY
in the transient — **never** the tracked ``shipwright_test_results.json`` (this
tool never opens that file).

Absent-input safe: a missing ``coverage.xml`` / unavailable ``diff-cover`` / "no
changed lines under coverage" all produce ``status: "n/a"`` and exit 0.

Gate mode (Phase-4 hardening): with ``--fail-under N`` the tool ALSO prints the
diff report and exits non-zero iff ``diff% < N`` (``decide_gate``). ci.yml's
warn-only step calls this instead of raw ``diff-cover`` so the fail-path is
unit/integration-testable. Without ``--fail-under`` it stays informational
(exit 0). ``--diff-cover-json`` parses a pre-computed report (no subprocess);
otherwise ``diff-cover`` is invoked (non-deprecated ``--format`` flags).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.atomic_write import durable_atomic_write  # noqa: E402
from lib.diff_coverage_gate import (  # noqa: E402
    GATE_EXIT_ERROR,
    decide_gate,
    print_gate_report,
)

SCHEMA = "diff_coverage/v1"
# Phase 2 (roadmap): the coverage.xml this tool reads is now the COMBINED
# repo-wide report (all plugins + shared + integration), so the default tier
# label is "repo". A caller measuring only one tier can still override it.
DEFAULT_TIER = "repo"
DEFAULT_COMPARE_BRANCH = "origin/main"
DEFAULT_OUTPUT_REL = Path(".shipwright") / "coverage" / "diff_coverage.json"
_NA_NOTE = (
    "no diff-coverage available — no changed lines under the measured tier, "
    "or coverage.xml / diff-cover was unavailable"
)


# --------------------------------------------------------------------------- #
# Pure parsers
# --------------------------------------------------------------------------- #
def line_rate_percent(coverage_xml: Path | str) -> float | None:
    """Overall line-rate from a coverage.py XML report, as a 0–100 percent.

    Reads the root ``<coverage line-rate="0.835">`` attribute. Returns ``None``
    when the file is missing, unparseable, or lacks the attribute."""
    path = Path(coverage_xml)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    raw = root.get("line-rate")
    if raw is None:
        return None
    try:
        return round(float(raw) * 100, 1)
    except (TypeError, ValueError):
        return None


def diff_percent_from_report(report: Any) -> float | None:
    """``total_percent_covered`` from a ``diff-cover`` JSON report payload.

    Returns ``None`` when there are no changed lines under coverage
    (``total_num_lines == 0`` — diff-cover reports a misleading 100% there) or
    the key is missing / the payload is not a dict."""
    if not isinstance(report, dict):
        return None
    n_lines = report.get("total_num_lines")
    if isinstance(n_lines, (int, float)) and n_lines == 0:
        return None
    pct = report.get("total_percent_covered")
    if isinstance(pct, bool) or not isinstance(pct, (int, float)):
        return None
    return float(pct)


# --------------------------------------------------------------------------- #
# Payload + transient write
# --------------------------------------------------------------------------- #
def build_payload(
    *,
    total: float | None,
    diff: float | None,
    compare_branch: str,
    coverage_xml: str,
    measured_tier: str = DEFAULT_TIER,
    note: str | None = None,
) -> dict[str, Any]:
    """Assemble the transient report. ``status`` is ``"ok"`` iff ``diff`` is a
    number; otherwise ``"n/a"`` with an explanatory ``note``."""
    ok = diff is not None
    return {
        "schema": SCHEMA,
        "measured_tier": measured_tier,
        "compare_branch": compare_branch,
        "coverage_xml": coverage_xml,
        "total": total,
        "diff": diff,
        "status": "ok" if ok else "n/a",
        "note": "" if ok else (note or _NA_NOTE),
    }


def write_transient(output: Path | str, payload: dict[str, Any]) -> None:
    """Durably + atomically write the transient JSON (creating parents)."""
    durable_atomic_write(Path(output), json.dumps(payload, indent=2) + "\n")


# --------------------------------------------------------------------------- #
# diff-cover invocation (only when no --diff-cover-json is supplied)
# --------------------------------------------------------------------------- #
def run_diff_cover(
    coverage_xml: Path | str,
    compare_branch: str,
    project_root: Path | str,
    *,
    json_out: Path | str | None = None,
    markdown_out: Path | str | None = None,
) -> dict[str, Any] | None:
    """Run ``diff-cover`` and return its parsed JSON report, or ``None`` on any
    failure (binary absent, git/coverage error, unreadable report) — never
    raises. ``json_out`` / ``markdown_out`` persist the reports at caller-chosen
    paths (gate mode); ``None`` json_out -> tempdir (informational). Uses ONE
    non-deprecated ``--format json:…,markdown:…`` flag (diff-cover keeps only
    the last of repeated ``--format`` flags)."""
    cov = Path(coverage_xml)
    if not cov.exists():
        return None
    with tempfile.TemporaryDirectory() as td:
        json_path = Path(json_out) if json_out is not None else Path(td) / "diff-cover.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        fmts = [f"json:{json_path}"]
        if markdown_out is not None:
            Path(markdown_out).parent.mkdir(parents=True, exist_ok=True)
            fmts.append(f"markdown:{markdown_out}")
        # Clear any stale report at the PERSISTENT outputs (a repeated local gate
        # run) so "file exists after the run" reliably means THIS run produced it
        # — else a diff-cover failure could inherit a prior run's report.
        for stale in (json_path, Path(markdown_out) if markdown_out else None):
            if stale is not None and stale.exists():
                stale.unlink()
        base_args = [
            str(cov),
            "--compare-branch", compare_branch,
            "--format", ",".join(fmts),
            # OUR wrapper owns the gate decision (decide_gate); diff-cover itself
            # must never exit non-zero, so it always runs at --fail-under 0.
            "--fail-under", "0",
        ]
        for cmd in (
            ["diff-cover", *base_args],
            [sys.executable, "-m", "diff_cover.diff_cover_tool", *base_args],
        ):
            try:
                subprocess.run(
                    cmd, cwd=str(project_root), capture_output=True,
                    text=True, timeout=180,
                )
            except (FileNotFoundError, OSError, subprocess.SubprocessError):
                continue
            if json_path.exists():
                try:
                    return json.loads(json_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    return None
        return None


def _load_report_json(path: Path | str) -> dict[str, Any] | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Measure diff/patch coverage (Phase 1).")
    ap.add_argument("--project-root", default=".", help="repo root (default: cwd)")
    ap.add_argument("--coverage-xml", required=True, help="path to coverage.xml")
    ap.add_argument("--compare-branch", default=DEFAULT_COMPARE_BRANCH,
                    help=f"diff-cover base (default: {DEFAULT_COMPARE_BRANCH})")
    ap.add_argument("--diff-cover-json", default=None,
                    help="pre-computed diff-cover JSON report (skips the subprocess)")
    ap.add_argument("--measured-tier", default=DEFAULT_TIER,
                    help=f"tier label recorded in the report (default: {DEFAULT_TIER})")
    ap.add_argument("--output", default=None,
                    help="transient report path (default: "
                         "<project-root>/.shipwright/coverage/diff_coverage.json)")
    ap.add_argument("--fail-under", type=float, default=None,
                    help="gate mode: after measuring, print the diff report and "
                         "exit non-zero iff diff-coverage %% < N (omit for "
                         "informational mode, which always exits 0)")
    ap.add_argument("--json-out", default=None,
                    help="gate mode: persist the diff-cover JSON report here "
                         "(default: <project-root>/diff-cover.json)")
    ap.add_argument("--markdown-out", default=None,
                    help="gate mode: persist the diff-cover markdown report here "
                         "(default: <project-root>/diff-cover.md)")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = Path(args.project_root).resolve()

    def _resolve(p: str) -> Path:
        # Relative paths resolve against --project-root (not the process CWD), so
        # a call from outside the repo still finds repo-relative inputs/outputs.
        q = Path(p)
        return q if q.is_absolute() else (project_root / q)

    coverage_xml = _resolve(args.coverage_xml)
    output = _resolve(args.output) if args.output else project_root / DEFAULT_OUTPUT_REL

    total = line_rate_percent(coverage_xml)

    gate_mode = args.fail_under is not None
    markdown_out: Path | None = None
    report: dict[str, Any] | None = None
    if args.diff_cover_json:
        report = _load_report_json(_resolve(args.diff_cover_json))
    elif coverage_xml.exists() and gate_mode:
        markdown_out = _resolve(args.markdown_out or "diff-cover.md")
        report = run_diff_cover(coverage_xml, args.compare_branch, project_root,
                                json_out=_resolve(args.json_out or "diff-cover.json"),
                                markdown_out=markdown_out)
    elif coverage_xml.exists():
        report = run_diff_cover(coverage_xml, args.compare_branch, project_root)
    diff = diff_percent_from_report(report)

    payload = build_payload(
        total=total,
        diff=diff,
        compare_branch=args.compare_branch,
        coverage_xml=coverage_xml.name,
        measured_tier=args.measured_tier,
    )
    write_transient(output, payload)

    if payload["status"] == "ok":
        extra = f" (tier total {total:.1f}%)" if total is not None else ""
        print(f"diff-coverage: {diff:.1f}% of changed lines covered{extra} "
              f"[{args.measured_tier}, vs {args.compare_branch}] -> {output}")
    else:
        print(f"diff-coverage: n/a — {payload['note']} -> {output}")

    if not gate_mode:
        return 0
    # Fail CLOSED when no report was produced (diff-cover crash / unavailable /
    # unreadable --diff-cover-json) — distinct from a report that legitimately
    # shows an empty diff (report present, diff None). Silently passing here
    # would make the gate strictly more lenient than raw diff-cover.
    if report is None:
        print("diff-coverage gate: ERROR — no diff-cover report produced "
              "(crash / unavailable / unreadable); failing closed.")
        return GATE_EXIT_ERROR
    print_gate_report(markdown_out, diff, args.fail_under)
    return decide_gate(diff, args.fail_under)


if __name__ == "__main__":
    sys.exit(main())
