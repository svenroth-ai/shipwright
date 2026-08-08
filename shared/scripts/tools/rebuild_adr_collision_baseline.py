#!/usr/bin/env python3
"""Regenerate ``<project_root>/shipwright_adr_collision_baseline.json``. Nothing else.

This is the ONLY documented way to update the ADR-collision anti-ratchet
baseline. It exists as a separate, explicitly-invoked command — not a side
effect of running the drift-guard test — so a same-run collision can never
quietly become part of the "known, accepted" baseline (external-review
finding 5, iterate-2026-08-08-index-readers-adr-lock).

Run it deliberately, after reviewing what changed, whenever a numeric ADR
spec-folder collision is knowingly accepted. New ADR spec files should not
be adding to this baseline going forward — they are named
``<run_id_sanitized>-<slug>.md`` (see F3.md), which cannot collide.

CLI:
    uv run shared/scripts/tools/rebuild_adr_collision_baseline.py --project-root .
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.adr_collision_baseline import BASELINE_RELPATH, collect_collisions  # noqa: E402
from lib.adr_index import ADR_SPEC_FOLDER, adr_spec_folder  # noqa: E402
from lib.atomic_write import durable_atomic_write  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate the ADR spec-folder collision baseline.",
    )
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root)
    folder = adr_spec_folder(project_root)
    if not folder.is_dir():
        print(f"no ADR spec folder at {ADR_SPEC_FOLDER} - nothing to do")
        return 0

    entries = collect_collisions(folder)
    baseline_path = project_root / BASELINE_RELPATH
    body = json.dumps({"version": 1, "entries": entries}, indent=2, sort_keys=True) + "\n"
    try:
        durable_atomic_write(baseline_path, body)
    except OSError as exc:
        print(f"ERROR: could not write {baseline_path}: {exc}", file=sys.stderr)
        return 1

    total_files = sum(len(v) for v in entries.values())
    print(
        f"regenerated {baseline_path}: {len(entries)} colliding number(s), "
        f"{total_files} file(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
