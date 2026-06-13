"""Regression: ``update_step``'s pre-lock standalone-flag read must not
trigger the legacy-migration WRITE outside the run-config lock.

Audit WP2 (PR #226) moved ``update_step``'s read-modify-write under
``run_config_lock`` + made the write atomic, but left one residual
F11-class window: line ``is_standalone = _load_or_bootstrap(...)`` runs
BEFORE the lock, and for a *legacy* config that load implicitly migrates
(drops ``compliance`` / ``security`` from the pipeline) and persists via
``save_run_config`` — an UNLOCKED write that a concurrent locked writer
could clobber with a stale in-memory copy.

The fix reads the ``standalone`` flag WITHOUT migrating
(``load_run_config(..., migrate=False)``); the migration still happens,
but now on the in-lock ``_load_or_bootstrap`` reload — so every config
write update_step is responsible for is serialized by the lock.

``standalone`` is invariant under migration (migration only touches
``pipeline`` / ``phase_tasks``), so the unmigrated read is correct.
"""
import json
import sys
from contextlib import contextmanager
from pathlib import Path

_LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import orchestrator  # noqa: E402,F401 — installs the ``orchestrator`` shim namespace
from orchestrator_pkg import config_io, step_planning  # noqa: E402
from orchestrator_pkg.constants import CONFIG_NAME  # noqa: E402


def _legacy_config() -> dict:
    """A config whose pipeline still carries the retired ``security`` phase —
    loading it forces a one-time legacy-migration write."""
    return {
        "schemaVersion": 2,
        "scope": "full_app",
        "pipeline": ["project", "design", "plan", "build", "test", "security", "changelog", "deploy"],
        "phase_tasks": [],
        "completed_phase_task_ids": [],
        "splits_frozen": [],
        "runConditions": {"securityEnabled": True, "splitMode": None, "aikidoClientIdPresent": False},
        "status": "in_progress",
        "completed_steps": [],
        "current_step": "project",
        "standalone": False,
        "created_at": "2026-04-01T00:00:00+00:00",
        "phase_history": {},
    }


def test_update_step_legacy_migration_write_is_inside_the_lock(tmp_path, monkeypatch):
    """The legacy-migration write triggered by update_step must occur while
    the run-config lock is held — never on the pre-lock standalone read."""
    (tmp_path / CONFIG_NAME).write_text(json.dumps(_legacy_config(), indent=2), encoding="utf-8")

    held = {"value": False}
    saw_unlocked_migration_write = {"value": False}

    real_lock = step_planning.run_config_lock

    @contextmanager
    def tracking_lock(project_root, **kwargs):
        with real_lock(project_root, **kwargs):
            held["value"] = True
            try:
                yield
            finally:
                held["value"] = False

    # The migration write goes through ``legacy_migration``'s lazy
    # ``from .config_io import save_run_config`` — patching the config_io
    # binding intercepts exactly that write (update_step's own locked writes
    # use step_planning's separate module binding and are not counted).
    real_save = config_io.save_run_config

    def tracking_save(project_root, config):
        if not held["value"]:
            saw_unlocked_migration_write["value"] = True
        return real_save(project_root, config)

    monkeypatch.setattr(step_planning, "run_config_lock", tracking_lock)
    monkeypatch.setattr(config_io, "save_run_config", tracking_save)

    step_planning.update_step(tmp_path, "test", "in_progress")

    assert not saw_unlocked_migration_write["value"], (
        "legacy-config migration write happened OUTSIDE run_config_lock "
        "(residual F11 window in update_step's pre-lock standalone read)"
    )

    # Migration still happened — just relocated under the lock.
    final = json.loads((tmp_path / CONFIG_NAME).read_text(encoding="utf-8"))
    assert "security" not in final["pipeline"]


def test_load_run_config_migrate_false_skips_legacy_migration(tmp_path):
    """``migrate=False`` returns the RAW parsed config and performs no write,
    so callers can read invariant fields (``standalone``) without the
    unlocked migration side effect. ``migrate=True`` (default) still migrates."""
    (tmp_path / CONFIG_NAME).write_text(json.dumps(_legacy_config(), indent=2), encoding="utf-8")

    raw = config_io.load_run_config(tmp_path, migrate=False)
    assert "security" in raw["pipeline"], "migrate=False must not drop legacy entries"
    assert raw.get("standalone") is False, "standalone flag readable from the raw config"
    # No write occurred: save_run_config stamps updated_at, so its absence on
    # disk proves the migrate=False read did not persist anything.
    on_disk = json.loads((tmp_path / CONFIG_NAME).read_text(encoding="utf-8"))
    assert "updated_at" not in on_disk, "migrate=False must not write the config"

    migrated = config_io.load_run_config(tmp_path, migrate=True)
    assert "security" not in migrated["pipeline"], "migrate=True still drops legacy entries"


def test_read_standalone_flag_mirrors_load_or_bootstrap(tmp_path):
    """``_read_standalone_flag`` matches ``_load_or_bootstrap(...).get(
    "standalone", False)`` for all three cases: absent config (bootstrap →
    True), present-and-standalone, present-and-not-standalone."""
    # Absent → standalone bootstrap default.
    assert step_planning._read_standalone_flag(tmp_path) is True

    # Present, standalone=True.
    cfg = _legacy_config()
    cfg["standalone"] = True
    (tmp_path / CONFIG_NAME).write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    assert step_planning._read_standalone_flag(tmp_path) is True

    # Present, standalone=False.
    cfg["standalone"] = False
    (tmp_path / CONFIG_NAME).write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    assert step_planning._read_standalone_flag(tmp_path) is False
