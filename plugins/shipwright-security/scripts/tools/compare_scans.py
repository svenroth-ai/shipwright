#!/usr/bin/env python3
"""Compare the latest security scan with a previous one — over shared ground only.

A finding present on Monday and gone on Tuesday means FIXED only if Tuesday
checked the same class of weakness. This CLI reads two scan sidecars, applies
that gate (see ``scan_compare``), and reports which classes could not be
compared instead of quietly counting their findings as resolved.

Usage:
    uv run scripts/tools/compare_scans.py --project-root .
    uv run scripts/tools/compare_scans.py --previous a.json --current b.json

Exit codes:
    0  comparison produced
    2  a sidecar is missing or unreadable
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

from scan_compare import compare_scans, render_comparison  # noqa: E402
from scan_history import HISTORY_DIRNAME, previous_scan_json  # noqa: E402

REPORTS_DIR = ".shipwright/securityreports"
LATEST_JSON = "latest.json"


def _fix_windows_encoding() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer, encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _load(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def resolve_pair(
    project_root: Path, previous: str | None, current: str | None
) -> tuple[Path | None, Path | None]:
    """Resolve the (previous, current) sidecar paths.

    Explicit flags win. Otherwise ``latest.json`` is the current scan and the
    newest archived sidecar that is not the current one is the previous.
    """
    reports_dir = project_root / REPORTS_DIR
    current_path = Path(current) if current else reports_dir / LATEST_JSON
    if previous:
        return Path(previous), current_path

    current_payload = _load(current_path) if current_path.exists() else None
    exclude = str(current_payload.get("scan_id")) if current_payload else None
    return previous_scan_json(reports_dir / HISTORY_DIRNAME, exclude), current_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".", help="Project root (default: cwd)")
    parser.add_argument("--previous", help="Path to the earlier scan sidecar JSON")
    parser.add_argument("--current", help="Path to the later scan sidecar JSON")
    parser.add_argument(
        "--format", choices=["markdown", "json"], default="markdown",
        help="Output format (default: markdown)",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    prev_path, curr_path = resolve_pair(project_root, args.previous, args.current)

    if prev_path is None or not prev_path.exists():
        print(
            "[shipwright-security] no previous scan to compare against "
            f"(looked under {project_root / REPORTS_DIR / HISTORY_DIRNAME}).",
            file=sys.stderr,
        )
        return 2
    if curr_path is None or not curr_path.exists():
        print(
            f"[shipwright-security] current scan not found at {curr_path}. "
            "Run the scan first.",
            file=sys.stderr,
        )
        return 2

    previous, current = _load(prev_path), _load(curr_path)
    if previous is None or current is None:
        print(
            "[shipwright-security] a scan sidecar is not valid JSON.",
            file=sys.stderr,
        )
        return 2

    result = compare_scans(previous, current)
    result["previous_path"] = str(prev_path)
    result["current_path"] = str(curr_path)

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("\n".join(render_comparison(result)))
    return 0


if __name__ == "__main__":
    _fix_windows_encoding()
    sys.exit(main())
