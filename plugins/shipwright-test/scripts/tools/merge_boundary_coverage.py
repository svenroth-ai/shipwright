#!/usr/bin/env python3
"""Merge a standalone boundary-coverage JSON report into shipwright_test_results.json.

E spec HIGH-4: thin CLI helper for callers that prefer a two-step
flow (run `boundary_coverage_report.py --output-json X.json`, then
merge X.json into the test-results file). The same merge can be done
in one step via `boundary_coverage_report.py --merge-into <path>`.

Atomic write via `tmp.replace(target)`. Existing top-level keys in the
target are preserved; only `boundary_coverage_report` is set/replaced.

Usage:
    uv run "{plugin_root}/scripts/tools/merge_boundary_coverage.py" \\
      --input ".shipwright/test-reports/boundary-coverage-2026-05-03.json" \\
      --target "shipwright_test_results.json"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def merge(input_path: Path, target_path: Path) -> None:
    """Merge `input_path` (the standalone JSON report) into `target_path`
    under the `boundary_coverage_report` key. Atomic write.

    Raises FileNotFoundError if `input_path` is missing.
    """
    if not input_path.exists():
        raise FileNotFoundError(
            f"Input report not found at {input_path!s}. "
            f"Did you run boundary_coverage_report.py first?"
        )
    payload = json.loads(input_path.read_text(encoding="utf-8"))

    if target_path.exists():
        try:
            existing = json.loads(target_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
    else:
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    existing["boundary_coverage_report"] = payload

    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    tmp_path.replace(target_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to the standalone JSON report from boundary_coverage_report.py.",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("shipwright_test_results.json"),
        help="Path to shipwright_test_results.json. Created if missing.",
    )
    args = parser.parse_args(argv)

    try:
        merge(args.input, args.target)
    except FileNotFoundError as e:
        print(json.dumps({"success": False, "error": str(e)}, indent=2))
        return 1
    print(json.dumps({"success": True, "target": str(args.target)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
