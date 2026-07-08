"""Config I/O for the orchestrator package.

Read/write/migrate ``shipwright_run_config.json``. The legacy-migration
logic itself lives in ``legacy_migration.py``; this module is the thin
read/write/json layer plus the v2 detector.

Split out of the monolithic ``orchestrator.py`` in Campaign B5
(2026-05-26).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import CONFIG_NAME, LEGACY_FALLBACK_MODE, RUN_MODES, SCHEMA_VERSION

# ``run_config_store`` is a top-level module in this plugin's scripts/lib;
# importing ``.constants`` above already put that dir on sys.path.
from run_config_store import atomic_write_json  # noqa: E402


def load_run_config(project_root: Path, *, migrate: bool = True) -> dict[str, Any]:
    """Load orchestrator config (with implicit legacy migration).

    ``migrate=False`` returns the RAW parsed config and runs NO legacy
    migration — so it performs none of the migration's UNLOCKED
    ``save_run_config`` write. Callers that only need a migration-invariant
    field (e.g. ``standalone``, which lives outside ``pipeline`` /
    ``phase_tasks`` — the only keys migration rewrites) use it to avoid an
    out-of-lock write; the migration still runs on the next in-lock load
    (audit WP2/F11 residual window).
    """
    path = project_root / CONFIG_NAME
    if not path.exists():
        return {}  # Valid: first run, no config yet
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(json.dumps({
            "warning": "Corrupt orchestrator config",
            "error_category": "validation",
            "what_failed": f"Parse {CONFIG_NAME}",
            "exception": str(exc),
            "alternative": "Delete the file and re-run /shipwright-run to recreate",
        }), file=sys.stderr)
        return {}
    if not migrate:
        return config
    # Lazy import to avoid a circular dep: legacy_migration imports config_io.
    from .legacy_migration import _migrate_legacy_pipeline_if_needed
    return _migrate_legacy_pipeline_if_needed(project_root, config)


def save_run_config(project_root: Path, config: dict[str, Any]) -> None:
    """Save orchestrator config (stamps ``updated_at``) atomically.

    The write is ``tmp + os.replace`` (audit WP2/F11) so a concurrent reader
    never observes a half-written file. This is the low-level writer: the
    advisory run-config lock that serialises read-modify-write windows is held
    by callers (``update_step``, ``phase_task_lifecycle``), NOT here — so the
    legacy-migration-on-load path can call it from inside a held lock without
    re-entering (deadlocking) it.
    """
    config["updated_at"] = datetime.now(timezone.utc).isoformat()
    atomic_write_json(project_root / CONFIG_NAME, config)


def is_v2_config(config: dict[str, Any]) -> bool:
    """Return True if config carries the multi-session schema (v2)."""
    return config.get("schemaVersion") == SCHEMA_VERSION


def run_mode(config: dict[str, Any]) -> str:
    """Return the pipeline execution mode, defaulting legacy configs safely.

    Back-compat (Campaign 2026-07-07, SS1): the ``mode`` field is additive and
    optional. A config written before SS1 has no ``mode`` key — it is read as
    ``multi_session`` (``LEGACY_FALLBACK_MODE``, the pre-SS1 behaviour), so old
    runs keep working unchanged. An unrecognised value is *also* coerced to it so
    a hand-edited typo can never silently select an unbuilt execution path.

    SS8 (2026-07-08): a FRESH run now defaults to ``single_session``
    (``DEFAULT_RUN_MODE``), but this READ path deliberately keeps the legacy
    fallback at ``multi_session`` — flipping the fresh default must NOT silently
    reinterpret an existing mode-less run; that run migrates EXPLICITLY (set
    ``mode: single_session`` + resume; docs/migrations/multi-session-to-single-session.md).
    """
    mode = config.get("mode")
    return mode if mode in RUN_MODES else LEGACY_FALLBACK_MODE
