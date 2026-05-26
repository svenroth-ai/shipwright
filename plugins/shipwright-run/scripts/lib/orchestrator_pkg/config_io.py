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
    """Save orchestrator config (stamps ``updated_at``)."""
    path = project_root / CONFIG_NAME
    config["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def is_v2_config(config: dict[str, Any]) -> bool:
    """Return True if config carries the multi-session schema (v2)."""
    return config.get("schemaVersion") == SCHEMA_VERSION
