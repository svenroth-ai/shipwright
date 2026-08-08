#!/usr/bin/env python3
"""CLI: report whether a mandated-load path list fits inside one `Read` call.

See ``lib.mandated_load_coverage`` for what this reports and why
(TC3.2, trg-c0d83dce). Accepts a repo-root-relative glob so a "read ALL
X across all splits" instruction can be checked in one call rather than
requiring the caller to enumerate paths first.

Usage::

    uv run check_mandated_load_coverage.py --project-root . \
        --glob ".shipwright/planning/*/spec.md"

Prints, e.g.::

    {
      "files": [
        {"path": "...", "exists": true, "total_lines": 1300,
         "cap_lines": 2000, "exceeds_cap": false}
      ],
      "any_exceeds_cap": false,
      "escaped_project_root": []
    }

`--path`/`--glob` are project-root-relative; a candidate that resolves
outside `--project-root` (an absolute path, a `../`-laden one) is reported
in `escaped_project_root` and excluded from `files` rather than followed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.mandated_load_coverage import READ_LINE_CAP, check_coverage  # noqa: E402


def _resolve_under_root(root: Path, raw: str) -> tuple[str | None, bool]:
    """Resolve `raw` against `root`; return `(resolved, escaped)`.

    `--path`/`--glob` are documented as project-root-relative, but
    ``root / raw`` silently discards `root` for an absolute `raw` (pathlib's
    own ``__truediv__`` semantics), and a `../`-laden `raw` can walk outside
    `root` even when relative. Resolving and checking containment closes
    both (external code review, iterate-2026-08-08) -- a candidate this
    check cannot place under `root` is reported, never silently followed or
    silently dropped.
    """
    resolved_root = root.resolve()
    candidate = (root / raw).resolve()
    if candidate == resolved_root or resolved_root in candidate.parents:
        return str(candidate), False
    return None, True


def main() -> int:
    parser = argparse.ArgumentParser(description="Check mandated-load file(s) against the single-Read line cap")
    parser.add_argument("--project-root", default=".", help="Project root the glob is resolved against")
    parser.add_argument("--glob", action="append", default=[], help="Repo-relative glob (repeatable)")
    parser.add_argument("--path", action="append", default=[], help="Repo-relative exact path (repeatable)")
    parser.add_argument("--cap-lines", type=int, default=READ_LINE_CAP)
    args = parser.parse_args()

    root = Path(args.project_root)
    raw_candidates = list(args.path)
    for pattern in args.glob:
        raw_candidates.extend(str(p.relative_to(root)) for p in sorted(root.glob(pattern)))

    resolved: list[str] = []
    escaped: list[str] = []
    for raw in raw_candidates:
        candidate, is_escaped = _resolve_under_root(root, raw)
        (escaped if is_escaped else resolved).append(raw if is_escaped else candidate)

    report = check_coverage(resolved, cap_lines=args.cap_lines)
    report["escaped_project_root"] = escaped
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
