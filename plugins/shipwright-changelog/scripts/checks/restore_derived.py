#!/usr/bin/env python3
"""Put the derived snapshots a release step rewrote back to ``HEAD`` (operator decision F10): they are never committed.

A process of its own: ``derived_snapshots`` imports the shared ``lib`` package, and this plugin has a ``lib`` of its own.

    uv run restore_derived.py --shared-root <shared> --project-root .

Prints ``{"restored": [paths]}``; exit 0.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shared-root", required=True)
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(Path(args.shared_root) / "scripts"))
    from lib.derived_snapshots import restore_derived_to_head  # noqa: E402

    print(json.dumps({"restored": sorted(restore_derived_to_head(Path(args.project_root).resolve()))}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
