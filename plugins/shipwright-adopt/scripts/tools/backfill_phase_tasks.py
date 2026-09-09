#!/usr/bin/env python3
"""Backfill ``phase_tasks[]`` into an already-adopted project's
``shipwright_run_config.json``.

Campaign p4-04-retire-write-once-steps, sub-iterate s2: shipwright-adopt
started seeding ``phase_tasks[]`` entries marked ``establishedAtAdoption``
for every NEW adoption (``write_run_config``, via ``write_all``). That only
serves future adoptions — a repo adopted BEFORE s2 landed (2026-09-09) has
``completed_steps`` and no ``phase_tasks[]`` at all, so phase_tasks[]-driven
readers that no longer consult ``completed_steps`` (e.g.
``plugins/shipwright-compliance/scripts/lib/mermaid.py``'s
``_get_phase_status``, once that repo is later picked up by a
``/shipwright-run`` for a NEW feature) would render its adoption-era phases
as pending, not the "not outstanding" they actually are. This tool is that
gap's owner: sub-iterate s2b.

Usage::

    uv run backfill_phase_tasks.py --project-root <path> [--dry-run]

The write-time logic (which entries to add) lives in
``lib.adopted_phase_tasks.backfill_missing_phase_tasks`` — this file is I/O
only: read the config, call the pure function, write it back if (and only
if) something changed.

Idempotent: a second run against an already-backfilled (or freshly, post-s2
adopted) config finds nothing to add and does not touch the file — verified
in ``tests/test_backfill_phase_tasks_cli.py`` at the file level, and against
a real pre-2026-09 adopted config's actual on-disk shape (not only a
synthetic fixture) in
``tests/fixtures/backfill_phase_tasks/leadwright_run_config.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.adopted_phase_tasks import backfill_missing_phase_tasks  # noqa: E402
from lib.cli_paths import unquoted_path  # noqa: E402

RUN_CONFIG_NAME = "shipwright_run_config.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(project_root: Path, *, dry_run: bool) -> dict[str, Any]:
    config_path = project_root / RUN_CONFIG_NAME
    if not config_path.is_file():
        raise SystemExit(
            f"ERROR: {config_path} does not exist. This tool backfills an "
            "already-adopted project; run /shipwright-adopt first."
        )
    try:
        # utf-8-sig transparently strips a leading UTF-8 BOM (a config
        # opened and re-saved by Notepad or a similar editor) and behaves
        # identically to utf-8 when no BOM is present -- confidence
        # calibration boundary probe, s2b: a bare utf-8 read raised
        # JSONDecodeError on a BOM-prefixed file instead of parsing it.
        run_config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ERROR: {config_path} is not valid JSON: {exc}") from exc
    if not isinstance(run_config, dict):
        raise SystemExit(
            f"ERROR: {config_path} is not a JSON object (got "
            f"{type(run_config).__name__})."
        )

    adoption = run_config.get("adoption")
    if not isinstance(adoption, dict):
        return {
            "success": True,
            "applicable": False,
            "reason": (
                "no usable 'adoption' object -- not a shipwright-adopt config "
                "(or it is malformed), nothing to backfill"
            ),
            "added_phases": [],
            "skipped_phases": [],
            "dry_run": dry_run,
        }

    # Backfilling entries against a repo adopted long ago should read as
    # having happened then, not now -- 'now' feeds createdAt/completedAt on
    # every seeded PhaseTask, and adopted_at is the only honest timestamp
    # this tool has for work that predates its own existence.
    now = adoption.get("adopted_at") or _utc_now_iso()

    updated, added, skipped = backfill_missing_phase_tasks(run_config, now=now)

    result: dict[str, Any] = {
        "success": True,
        "applicable": True,
        "project_root": str(project_root),
        "added_phases": added,
        "skipped_phases": skipped,
        "dry_run": dry_run,
    }
    if not added:
        result["written"] = False
        return result

    if not dry_run:
        config_path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    result["written"] = not dry_run
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill phase_tasks[] into an already-adopted shipwright_run_config.json",
    )
    parser.add_argument("--project-root", required=True, type=unquoted_path)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would change without writing the file.",
    )
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve()
    if not project_root.is_dir():
        print(json.dumps({"success": False, "error": f"not a directory: {project_root}"}))
        return 1

    summary = run(project_root, dry_run=args.dry_run)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
