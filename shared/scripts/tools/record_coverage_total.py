#!/usr/bin/env python3
"""Record the combined repo-wide line-rate into the tracked ``coverage.total``.

Diff-coverage roadmap **Phase 2**. The Phase-1 boundary was strict: the transient
``measure_diff_coverage.py`` must NEVER touch the tracked
``shipwright_test_results.json`` (``coverage.diff`` is PR-local — committing it
would show stale data on ``main``). Phase 2 introduces the *other* number —
``coverage.total``, the repo-**stable** whole-repo line-rate that lights the W4
verifier — and it DOES belong in the tracked file. This tool is that deliberate,
isolated writer: it parses a combined ``coverage.xml`` (produced by
``combine_coverage.py``) and writes ONLY the top-level ``coverage.total`` block,
**preserving** ``iterate_latest`` and any other top-level keys.

W4 (``tools/verifiers/test_compliance.py``) reads ``coverage.total`` here and
compares it to ``shipwright_test_config.json.coverage.min``. The paired writer +
reader make this the ``touches_io_boundary`` round-trip for this iterate.

Usage::

    record_coverage_total.py --project-root . --coverage-xml coverage.xml \
        [--measured-tier repo] [--source "..."] [--measured-at <iso8601>]

Exits non-zero (writes nothing) when the coverage.xml is missing/unparseable —
the tracked baseline must never be a fabricated number. Feed it a ``coverage.xml``
from a **fully-successful** ``combine_coverage.py`` run: that tool exits non-zero
on a PARTIAL combine (a tier failed to fold in), so chain them —
``combine_coverage.py … && record_coverage_total.py …`` — and a subset baseline
never reaches the tracked file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_TOOLS_ROOT = Path(__file__).resolve().parent
if str(_TOOLS_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_TOOLS_ROOT.parent))

from lib.atomic_write import durable_atomic_write  # noqa: E402
from tools.measure_diff_coverage import line_rate_percent  # noqa: E402

RESULTS_REL = "shipwright_test_results.json"
DEFAULT_TIER = "repo"
DEFAULT_SOURCE = "combined coverage.xml (all plugins + shared + integration)"


def _load_results(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def merge_coverage_total(
    existing: dict[str, Any],
    total: float,
    *,
    measured_tier: str = DEFAULT_TIER,
    source: str = DEFAULT_SOURCE,
    measured_at: str | None = None,
) -> dict[str, Any]:
    """Return ``existing`` with a fresh top-level ``coverage`` block. Every other
    top-level key (notably ``iterate_latest``) is preserved untouched. Any prior
    ``coverage.diff`` is intentionally NOT carried here — ``.diff`` is transient
    and never tracked."""
    out = dict(existing)
    block: dict[str, Any] = {
        "total": total,
        "measured_tier": measured_tier,
        "source": source,
    }
    if measured_at is not None:
        block["measured_at"] = measured_at
    out["coverage"] = block
    return out


def write_results(path: Path, data: dict[str, Any]) -> None:
    durable_atomic_write(path, json.dumps(data, indent=2) + "\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Record combined repo-wide coverage.total (Phase 2).")
    ap.add_argument("--project-root", default=".", help="repo root (default: cwd)")
    ap.add_argument("--coverage-xml", required=True, help="combined coverage.xml")
    ap.add_argument("--results", default=None,
                    help=f"tracked results file (default: <root>/{RESULTS_REL})")
    ap.add_argument("--measured-tier", default=DEFAULT_TIER)
    ap.add_argument("--source", default=DEFAULT_SOURCE)
    ap.add_argument("--measured-at", default=None,
                    help="ISO-8601 stamp (optional; omit to leave it out)")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = Path(args.project_root).resolve()

    def _resolve(p: str) -> Path:
        q = Path(p)
        return q if q.is_absolute() else (project_root / q)

    coverage_xml = _resolve(args.coverage_xml)
    total = line_rate_percent(coverage_xml)
    if total is None:
        sys.stderr.write(
            f"record_coverage_total: cannot read a line-rate from "
            f"{coverage_xml} — refusing to write a fabricated total.\n")
        return 1

    results = _resolve(args.results) if args.results else project_root / RESULTS_REL
    data = merge_coverage_total(
        _load_results(results), total,
        measured_tier=args.measured_tier, source=args.source,
        measured_at=args.measured_at,
    )
    write_results(results, data)
    print(f"record_coverage_total: coverage.total={total:.1f}% "
          f"[{args.measured_tier}] -> {results}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
