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

from .constants import (
    CONFIG_NAME,
    DEFAULT_RUN_MODE,
    LEGACY_MODE_MESSAGE,
    LEGACY_MULTI_SESSION,
    MODE_REQUIRED_MESSAGE,
    SCHEMA_VERSION,
)

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
    """Return True if config carries the pipeline schema (v2)."""
    return config.get("schemaVersion") == SCHEMA_VERSION


# --------------------------------------------------------------------------- #
# Mode
#
# THE INVARIANT: a run is a driven single-session pipeline **iff its config
# records the explicit literal `mode: "single_session"`.** Nothing is inferred.
#
# `gate_policy.read_run_config_mode` applies the identical explicit-literal test,
# so the orchestrator loop and the gate mechanism can never disagree about
# whether a run is being driven — the conflation that made the old
# multi_session-as-fallback model dangerous to remove.
# --------------------------------------------------------------------------- #

# NOTE: there is deliberately NO ``run_mode()`` reporter here. One existed briefly and
# was a trap: for a mode-less config it answered "single_session" (the sole mode) while
# ``is_single_session()`` answered False (not drivable) — two functions, same config,
# opposite answers, inviting the next caller to write `run_mode(cfg) == "single_session"`
# and silently reintroduce the reinterpretation this module exists to prevent. Read the
# raw value with ``config.get("mode")`` and ask ``is_single_session`` about drivability.


def is_single_session(config: dict[str, Any]) -> bool:
    """THE drivability predicate — explicit literal only (see THE INVARIANT)."""
    return config.get("mode") == DEFAULT_RUN_MODE


def is_legacy_multi_session(config: dict[str, Any]) -> bool:
    """True when ``config`` records the removed ``multi_session`` mode."""
    return config.get("mode") == LEGACY_MULTI_SESSION


def mode_rejection(config: dict[str, Any]) -> dict[str, Any]:
    """The actionable fail-closed payload for a config that is NOT drivable.

    Returned — before anything is claimed, completed, mutated or emitted — by every
    entry point that would ADVANCE a run:

      * ``write-config`` (and ``create_config``, which raises instead);
      * the ``single-session-*`` subcommands (loop + resume/gate/recover);
      * the ADVANCING phase-lifecycle subcommands (``router._ADVANCING_COMMANDS``:
        claim / complete / mark-failed / freeze-splits / plan-next-phase).

    Two paths are exempt ON PURPOSE, and the exemptions are the point rather than an
    oversight: the READ-ONLY lifecycle commands (a historical run must stay
    inspectable — the guard is never in the read path), and ``recover-phase-task``,
    the manual escape hatch the documented migration of a wedged run depends on.

    Two shapes, one fix (``set mode: single_session``):
      * the removed ``multi_session`` literal — an explicit choice whose engine is
        gone; say so rather than silently reinterpreting the user's intent;
      * anything else, incl. a mode-less pre-SS1 config — never opted into a mode;
        it just has to declare the only one there is.
    """
    mode = config.get("mode")
    message = LEGACY_MODE_MESSAGE if mode == LEGACY_MULTI_SESSION else MODE_REQUIRED_MESSAGE
    return {
        "ok": False,
        "action": "mode_unsupported",
        "reason": "mode_unsupported",
        "mode": mode,
        "message": message,
    }
