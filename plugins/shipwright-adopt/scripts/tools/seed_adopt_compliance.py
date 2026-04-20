#!/usr/bin/env python3
"""CLI wrapper: seed compliance reports for an adopted project.

Primary path: run `update_compliance.py --phase X` for each retroactive
phase marker. Fallback path: direct lib-import of the compliance generators.
Non-blocking — reports what succeeded and what didn't.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_lib() -> None:
    lib_dir = Path(__file__).resolve().parent.parent / "lib"
    sys.path.insert(0, str(lib_dir))


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed compliance for /shipwright-adopt")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument(
        "--phases", nargs="*",
        default=["project", "plan", "build", "test"],
        help="Retroactive phases to trigger update_compliance for",
    )
    parser.add_argument(
        "--fallback", action="store_true",
        help="Always run direct-lib fallback in addition to update_compliance",
    )
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    if not project_root.is_dir():
        print(f"ERROR: not a directory: {project_root}", file=sys.stderr)
        return 1

    _load_lib()
    from compliance_bridge import run_update_compliance, run_lib_fallback  # type: ignore

    primary = run_update_compliance(project_root, phases=args.phases)
    results = {"primary": primary}

    # If primary failed to find script OR user asks for fallback explicitly,
    # run the lib-import path.
    if primary.get("script") is None or args.fallback:
        results["fallback"] = run_lib_fallback(project_root)

    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
