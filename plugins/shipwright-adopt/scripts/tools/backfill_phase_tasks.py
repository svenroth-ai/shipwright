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

# `atomic_write` and `file_lock` are unique top-level module names (unlike
# `lib.*`), so importing them straight from `shared/scripts/lib` never
# collides with this plugin's own `lib` package under the shared loader
# (ADR-045) -- the same pattern `run_config_store.py` uses for the identical
# reason. parents[4] of this file (scripts/tools/../../.. == plugins/../..)
# is the repo root in both the dev tree and the runtime plugin cache.
_SHARED_LIB = Path(__file__).resolve().parents[4] / "shared" / "scripts" / "lib"
if str(_SHARED_LIB) not in sys.path:
    sys.path.insert(0, str(_SHARED_LIB))
from atomic_write import durable_atomic_write, durable_read_text  # noqa: E402
from file_lock import LockTimeout, file_lock  # noqa: E402

RUN_CONFIG_NAME = "shipwright_run_config.json"
# Same lock-file PATH `plugins/shipwright-run/scripts/lib/run_config_store.py`
# uses -- mutual exclusion is guaranteed by the shared path, not by which
# module acquired it (see that module's docstring). This tool never imports
# run_config_store directly: that plugin's own `lib` package would collide
# with this plugin's `lib` namespace under the shared loader (ADR-045).
LOCK_SUFFIX = ".lock"
# A module-level constant, not an inline literal, so a test can monkeypatch
# it down to prove the lock-contention path without a real 30s wait.
LOCK_TIMEOUT_SECONDS = 30.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(project_root: Path, *, dry_run: bool) -> dict[str, Any]:
    config_path = project_root / RUN_CONFIG_NAME
    if not config_path.is_file():
        raise SystemExit(
            f"ERROR: {config_path} does not exist. This tool backfills an "
            "already-adopted project; run /shipwright-adopt first."
        )

    lock_path = project_root / (RUN_CONFIG_NAME + LOCK_SUFFIX)
    # The read-modify-write critical section is held under the SAME advisory
    # lock every other run-config writer (phase_task_lifecycle, the
    # orchestrator) honours, and the whole snapshot is read AFTER acquiring
    # it -- not just the write. This tool's own stated trigger scenario is a
    # repo "later picked up by /shipwright-run for a new feature": exactly
    # when a live, lock-holding orchestrator session could be concurrently
    # advancing status/current_step/phase_history/phase_tasks[] on this same
    # file. Reading first and locking only around the write would still let
    # this tool's full-document write clobber whatever the orchestrator
    # committed in between (doubt-reviewer, s2b) -- the lock has to cover
    # the read too, not just the replace.
    try:
        with file_lock(lock_path, timeout_seconds=LOCK_TIMEOUT_SECONDS):
            try:
                # utf-8-sig transparently strips a leading UTF-8 BOM (a config
                # opened and re-saved by Notepad or a similar editor) and
                # behaves identically to utf-8 when no BOM is present --
                # confidence calibration boundary probe, s2b: a bare utf-8
                # read raised JSONDecodeError on a BOM-prefixed file instead
                # of parsing it. `durable_read_text` also retries past a
                # writer's in-flight atomic replace (Windows delete-pending).
                run_config = json.loads(
                    durable_read_text(config_path, encoding="utf-8-sig")
                )
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
                        "no usable 'adoption' object -- not a shipwright-adopt "
                        "config (or it is malformed), nothing to backfill"
                    ),
                    "added_phases": [],
                    "skipped_phases": [],
                    "dry_run": dry_run,
                }

            # Backfilling entries against a repo adopted long ago should read
            # as having happened then, not now -- 'now' feeds
            # createdAt/completedAt on every seeded PhaseTask, and
            # adopted_at is the only honest timestamp this tool has for work
            # that predates its own existence. A present-but-non-string value
            # (a hand-edited config could carry anything JSON-valid) is not a
            # usable timestamp -- schema `PhaseTask.createdAt` is
            # `format: date-time`, so it falls back to `now` rather than
            # propagating garbage into every generated task record
            # (PR-review comment, s2b PR #701).
            adopted_at = adoption.get("adopted_at")
            now = adopted_at if isinstance(adopted_at, str) and adopted_at else _utc_now_iso()

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
                # tmp + os.replace: a concurrent reader (or this same lock's
                # next holder) never observes a half-written document.
                durable_atomic_write(config_path, json.dumps(updated, indent=2) + "\n")
            result["written"] = not dry_run
            return result
    except LockTimeout as exc:
        raise SystemExit(
            f"ERROR: could not acquire the run-config lock ({lock_path}) "
            f"within {LOCK_TIMEOUT_SECONDS}s -- another writer (an active "
            f"/shipwright-run session?) is holding it: {exc}"
        ) from exc


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
