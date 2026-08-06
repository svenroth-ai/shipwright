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
from run_config_store import atomic_write_json, durable_read_text  # noqa: E402


# The error contract lives in its own module (five importers, and this one is at
# its LOC budget); re-exported so callers keep a single import site.
from .run_config_errors import MAX_DETAIL_CHARS, RunConfigUnreadable  # noqa: E402,F401


def _read_parse_shape(path: Path) -> tuple[dict[str, Any], bool]:
    """The whole read boundary, once: read -> decode -> parse -> is-it-an-object.

    Returns ``(config, present)``; raises :class:`RunConfigUnreadable`. Shared by
    BOTH readers so the tolerant and strict paths can never drift on what counts
    as absent, malformed or usable — they differ only in how they DISPOSE of a
    failure, never in how they DETECT one.

    Absence is decided by the READ (``FileNotFoundError``), never by a preceding
    ``path.exists()``: a check-then-read pair can straddle a concurrent delete.
    No migration happens here — see :func:`read_run_config`.
    """
    try:
        # durable_read_text, not path.read_text: this read is deliberately
        # UNLOCKED, so a concurrent writer's os.replace can leave the entry
        # delete-pending and the open fails with PermissionError on Windows.
        #
        # utf-8-SIG, matching the five sibling readers moved there for this
        # reason (CHANGELOG: "Config readers now uniformly tolerate a UTF-8 BOM").
        # It decodes plain UTF-8 identically; without it a BOM — emitted by
        # PowerShell 5.1 `Out-File -Encoding utf8` and VS Code's `utf8bom` on this
        # repo's primary platform — fails at "line 1 column 1" on a file that
        # looks valid in any editor, so fail-closed would turn an INVISIBLE byte
        # into a wedged run.
        raw = durable_read_text(path, encoding="utf-8-sig")
    except (FileNotFoundError, NotADirectoryError):
        # NotADirectoryError = a FILE sits where project_root should be, so the
        # config genuinely is not there. `Path.exists()` (the old absence test)
        # answered False for it, and the tolerant reader must keep degrading.
        return {}, False  # Valid: first run, no config yet
    except UnicodeDecodeError as exc:
        raise RunConfigUnreadable(
            path, f"{type(exc).__name__}: {exc}", "decode", original=exc) from exc
    except OSError as exc:
        raise RunConfigUnreadable(
            path, f"{type(exc).__name__}: {exc}", "io", original=exc) from exc

    try:
        config = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RunConfigUnreadable(path, str(exc), "parse", original=exc) from exc
    except RecursionError as exc:
        # json.loads raises this — NOT JSONDecodeError — past its nesting limit.
        # Left unclassified it would bypass the taxonomy AND defeat recovery.
        # MemoryError and other process-level failures are deliberately not caught.
        raise RunConfigUnreadable(
            path, "JSON nested too deeply to parse", "parse", original=exc) from exc

    if not isinstance(config, dict):
        # `null`, `[]`, `123`, `"str"` all parse cleanly, so this never reached
        # the JSONDecodeError arm: the falsy ones demoted the run with NO warning
        # at all, and the truthy ones crashed on `.get` with a bare AttributeError.
        raise RunConfigUnreadable(
            path, f"top-level JSON is {type(config).__name__}, expected an object", "shape",
        )
    return config, True


def read_run_config(
    project_root: Path, *, migrate: bool = True,
) -> tuple[dict[str, Any], bool]:
    """STRICT read: returns ``(config, present)``, or raises ``RunConfigUnreadable``.

    Used by every path that can ADVANCE or CHANGE a run, so an unusable config
    stops it rather than being guessed at. ``present`` is what separates an absent
    config from one that merely holds ``{}`` — a truthiness test cannot, and a
    file containing ``{}`` was therefore bootstrapped over.

    **Total at the read boundary only.** Migration runs after it and its own
    failures propagate UNCHANGED: a ``KeyError`` there is a bug in our migration
    and an ``OSError`` from the write it performs is a disk fault. Relabelling
    either as "your config is corrupt" would send the operator to delete a file
    that is fine.
    """
    config, present = _read_parse_shape(project_root / CONFIG_NAME)
    if not present or not migrate:
        return config, present
    # Lazy import to avoid a circular dep: legacy_migration imports config_io.
    from .legacy_migration import _migrate_legacy_pipeline_if_needed
    return _migrate_legacy_pipeline_if_needed(project_root, config), True


def load_run_config(project_root: Path, *, migrate: bool = True) -> dict[str, Any]:
    """TOLERANT read (with implicit legacy migration) — for callers that only
    DISPLAY. Anything that can advance or change a run uses ``read_run_config``.

    ``migrate=False`` returns the RAW parsed config and runs NO legacy
    migration — so it performs none of the migration's UNLOCKED
    ``save_run_config`` write. Callers that only need a migration-invariant
    field (e.g. ``standalone``, which lives outside ``pipeline`` /
    ``phase_tasks`` — the only keys migration rewrites) use it to avoid an
    out-of-lock write; the migration still runs on the next in-lock load
    (audit WP2/F11 residual window).

    Damaged CONTENT (``parse`` / ``shape``) warns and degrades to ``{}``. A
    ``decode`` or ``io`` failure re-raises the ORIGINAL exception, not the
    wrapper: ``durable_read_text`` is deliberately strict and
    ``test_read_gives_up_loudly_rather_than_inventing_an_empty_config`` pins that
    a decode failure is never turned into an empty config. Re-typing it would
    regress that pin just as surely as swallowing it.
    """
    try:
        config, _present = read_run_config(project_root, migrate=migrate)
    except RunConfigUnreadable as exc:
        if exc.category in ("decode", "io"):
            # self.original, not __cause__: see RunConfigUnreadable.__init__.
            raise (exc.original if exc.original is not None else exc) from None
        print(json.dumps({
            "warning": "Corrupt orchestrator config",
            "error_category": "validation",
            "what_failed": f"Parse {CONFIG_NAME}",
            "exception": exc.detail,
            "alternative": "Delete the file and re-run /shipwright-run to recreate",
        }), file=sys.stderr)
        return {}
    return config


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
# `gate_policy.read_run_config_mode` applies the identical explicit-literal test
# ON A USABLE CONFIG, so the orchestrator loop and the gate mechanism cannot
# disagree about whether a run is being driven — the conflation that made the old
# multi_session-as-fallback model dangerous to remove.
#
# Scoped to a USABLE config on purpose: `read_run_config_mode` guards only
# `(JSONDecodeError, OSError)`, so the `shape` and `decode` cases this module now
# classifies escape its handler instead of reading as INERT_MODE. An availability
# gap in a read-only reporter, in `shared/` outside this iterate's scope
# (trg-406d7c3c) — stated, not papered over with an unconditional parity claim.
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
