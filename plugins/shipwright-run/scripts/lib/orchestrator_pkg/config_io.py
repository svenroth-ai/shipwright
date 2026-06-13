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

from .constants import CONFIG_NAME, SCHEMA_VERSION

# ``run_config_store`` is a top-level module in this plugin's scripts/lib;
# importing ``.constants`` above already put that dir on sys.path.
from run_config_store import atomic_write_json  # noqa: E402


def load_run_config(project_root: Path) -> dict[str, Any]:
    """Load orchestrator config (with implicit legacy migration)."""
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
