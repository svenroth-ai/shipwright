"""Append an iterate entry to ``agent_docs/iterates/<run_id>.json``.

Replaces the manual ``iterate_history`` array-append in
``shipwright_run_config.json`` (historic F5c in the iterate SKILL). The
move to file-per-iterate eliminates the merge-conflict hotspot that made
parallel iterates on adopted target projects unworkable.

Behavior:

* On first call against a project that still carries a legacy
  ``iterate_history`` array, the tool runs a one-shot migration under
  the same lock as the append. Invalid legacy rows and duplicate
  ``run_id`` values are diverted to
  ``agent_docs/iterates/_quarantine/`` and the count is recorded on the
  run config as ``_iterate_migration_quarantined_count`` for downstream
  visibility.
* The append itself is atomic per file; migration + append + retention
  all happen inside a single ``file_lock`` held on the run-config lock
  file so concurrent same-worktree finalize calls are serialized.
* Retention drops the oldest entries beyond
  ``ITERATE_RETENTION`` (50). Retention is applied only **after**
  migration is complete so first contact with a historic 60-entry array
  does not throw away 10 rows as a side effect of the upgrade.

CLI:

    uv run shared/scripts/tools/append_iterate_entry.py \\
        --project-root . \\
        --run-id iterate-2026-04-23-feat-x \\
        --entry-json '{"type":"feature","complexity":"medium", ...}'
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.file_lock import LockTimeout, file_lock  # noqa: E402
from lib.iterate_entry import (  # noqa: E402
    MIGRATION_QUARANTINE_REPORT_KEY,
    MIGRATION_QUARANTINED_COUNT_KEY,
    MIGRATION_STATE_KEY,
    MIGRATION_TS_KEY,
    RUN_CONFIG_NAME,
    entry_file_for,
    iterates_dir,
    normalize_legacy_entry,
    now_utc_iso,
    quarantine_dir,
    read_iterate_entries,
    sort_key,
    validate_iterate_entry,
)


ITERATE_RETENTION = 50


class IterateAppendError(RuntimeError):
    """Raised when an entry cannot be appended (validation, I/O, lock)."""


# ---------------------------------------------------------------------------
# Low-level atomic helpers
# ---------------------------------------------------------------------------


def _atomic_write_json(target: Path, data: Any) -> None:
    """Temp-file-plus-rename write so readers never see a half-file."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=target.name + ".", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(data, indent=2) + "\n")
        os.replace(tmp_name, target)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def _load_config(project_root: Path) -> dict[str, Any]:
    path = project_root / RUN_CONFIG_NAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IterateAppendError(
            f"malformed {RUN_CONFIG_NAME}: {exc}"
        ) from exc
    return data if isinstance(data, dict) else {}


def _save_config(
    project_root: Path,
    data: dict[str, Any],
    *,
    bump_updated_at: bool = False,
) -> None:
    """Write ``data`` to ``shipwright_run_config.json`` atomically.

    ``bump_updated_at`` is False by default because migration must write
    deterministic config mutations (no timestamps) so two branches running
    the same migration in parallel produce bitwise-identical diffs — git
    then auto-merges them instead of flagging a content conflict.
    """
    if bump_updated_at:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write_json(project_root / RUN_CONFIG_NAME, data)


def _write_entry_file(
    project_root: Path, entry: dict[str, Any], *, overwrite: bool = True
) -> Path:
    """Write one iterate entry as its own JSON file.

    Atomic via tempfile + ``os.replace``. ``overwrite=False`` is used during
    migration so a crash-recovery pass can skip files that the previous
    attempt already produced.
    """
    path = entry_file_for(project_root, entry["run_id"])
    if path.exists() and not overwrite:
        return path
    _atomic_write_json(path, entry)
    return path


def _write_quarantine_report(
    project_root: Path, quarantined: list[dict[str, Any]]
) -> Path:
    q_dir = quarantine_dir(project_root)
    q_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report_path = q_dir / f"invalid-legacy-{stamp}.json"
    _atomic_write_json(
        report_path,
        {
            "migration_run_ts": now_utc_iso(),
            "quarantined_count": len(quarantined),
            "quarantined_entries": quarantined,
        },
    )
    return report_path


# ---------------------------------------------------------------------------
# Migration state machine
# ---------------------------------------------------------------------------


def _migrate_legacy_array_to_dir(
    project_root: Path, config: dict[str, Any]
) -> dict[str, Any]:
    """Move legacy ``iterate_history`` rows into per-file entries.

    Multi-phase with a persistent state flag so a crash mid-migration
    can be resumed by ``_recover_migration``. Invalid rows and duplicate
    ``run_id``s land in a dated quarantine report rather than failing the
    whole migration.

    Crash-recovery contract:
      - Phase 1 flips ``state`` to ``in_progress`` via an atomic write.
      - Phase 2 writes entry files with ``overwrite=False`` so a re-run
        skips files that landed before the crash.
      - ``iterate_history`` is NOT cleared until Phase 4, so a recovery
        pass sees the original legacy rows and can resume cleanly.
      - Phase 4 atomically flips ``state`` to ``complete`` AND clears
        the legacy array. A crash between writes makes the next call
        re-enter Phase 1 with no data loss.
    """
    legacy = config.get("iterate_history", [])

    # Phase 1: flip to in_progress before any dir write. No timestamp so
    # parallel migrations across branches produce identical config diffs.
    config[MIGRATION_STATE_KEY] = "in_progress"
    _save_config(project_root, config)

    # Phase 2: normalize + validate + dedup + write per file.
    #
    # Duplicate-run_id handling: the first time we see a run_id, we store
    # it in ``seen``. On the SECOND occurrence we quarantine both rows
    # AND mark the run_id as poisoned in ``poisoned`` so any THIRD+
    # occurrence also quarantines. This closes the "3-copy silent keep"
    # gap: if we only removed from ``seen``, the third row would re-enter
    # ``seen`` and silently land as the authoritative version on disk.
    quarantined: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    poisoned: set[str] = set()
    for raw in legacy:
        if not isinstance(raw, dict):
            quarantined.append({"entry": raw, "reason": "legacy row was not a dict"})
            continue
        normalized = normalize_legacy_entry(raw)
        ok, err = validate_iterate_entry(normalized, strict=False)
        if not ok:
            quarantined.append({"entry": raw, "reason": err or "invalid"})
            continue
        run_id = normalized["run_id"]
        if run_id in poisoned:
            # An earlier duplicate already poisoned this run_id; every
            # subsequent payload for the same key goes to quarantine.
            quarantined.append({"entry": raw, "reason": f"duplicate run_id: {run_id}"})
            continue
        if run_id in seen:
            # First collision: quarantine BOTH payloads and poison the key
            # so future copies (3rd, 4th, ...) also end up quarantined.
            quarantined.append({"entry": raw, "reason": f"duplicate run_id: {run_id}"})
            quarantined.append(
                {"entry": seen[run_id], "reason": f"duplicate run_id: {run_id}"}
            )
            del seen[run_id]
            poisoned.add(run_id)
            continue
        seen[run_id] = normalized

    for entry in seen.values():
        _write_entry_file(project_root, entry, overwrite=False)

    # Phase 3: quarantine report (only if anything got quarantined).
    quarantine_report_path: Path | None = None
    if quarantined:
        quarantine_report_path = _write_quarantine_report(project_root, quarantined)

    # Phase 4: commit completion. ``iterate_history`` left as an empty
    # array (not removed) for backward-compat with any legacy external
    # reader that does ``config.get("iterate_history", [])``.
    #
    # Deliberately NO timestamps here — two branches running migration on
    # the same pre-refactor project in parallel must emit identical
    # config diffs. Timestamps would make the diffs byte-different and
    # surface as a merge conflict on run_config.json.
    config["iterate_history"] = []
    config[MIGRATION_STATE_KEY] = "complete"
    config[MIGRATION_QUARANTINED_COUNT_KEY] = len(quarantined)
    config.pop(MIGRATION_TS_KEY, None)  # remove any leftover in_progress ts
    if quarantine_report_path is not None:
        config[MIGRATION_QUARANTINE_REPORT_KEY] = str(
            quarantine_report_path.relative_to(project_root)
        )
    _save_config(project_root, config)
    return config


def _recover_migration(
    project_root: Path, config: dict[str, Any]
) -> dict[str, Any]:
    """Idempotent recovery for a crash during ``_migrate_legacy_array_to_dir``.

    Re-runs the migration. ``_write_entry_file(..., overwrite=False)`` and
    ``_write_quarantine_report`` are both safe under repetition: the former
    skips files that already exist, the latter writes a fresh timestamped
    report alongside any prior one.
    """
    return _migrate_legacy_array_to_dir(project_root, config)


def _apply_retention(project_root: Path, *, keep_last: int) -> int:
    """Delete the oldest entry files beyond ``keep_last`` (sorted by
    normalized UTC date, run_id tiebreaker).

    Race-safe: ``FileNotFoundError`` on ``unlink`` is suppressed so parallel
    callers computing the same "oldest" file don't crash each other.
    Returns the count of files actually deleted.
    """
    entries = read_iterate_entries(project_root)
    if len(entries) <= keep_last:
        return 0

    victims = sorted(entries, key=sort_key)[: len(entries) - keep_last]
    deleted = 0
    for entry in victims:
        run_id = entry.get("run_id")
        if not isinstance(run_id, str):
            continue
        victim_path = entry_file_for(project_root, run_id)
        try:
            victim_path.unlink()
            deleted += 1
        except FileNotFoundError:
            # Parallel append already removed it; that's fine.
            continue
        except OSError:
            # Filesystem said no; skip without failing the append.
            continue
    return deleted


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def append_iterate_entry(
    project_root: Path,
    entry: dict[str, Any],
    *,
    lock_timeout_seconds: float = 10.0,
    retention: int = ITERATE_RETENTION,
) -> dict[str, Any]:
    """Append ``entry`` to the file-per-iterate store.

    Returns a result dict:
        {
            "entry_path": "agent_docs/iterates/iterate-....json",
            "migrated": True | False,
            "quarantined_count": int,
            "retention_deleted": int,
        }
    """
    ok, err = validate_iterate_entry(entry, strict=True)
    if not ok:
        raise IterateAppendError(f"invalid entry: {err}")

    project_root = project_root.resolve()
    iterates_dir(project_root).mkdir(parents=True, exist_ok=True)
    lock_path = (project_root / RUN_CONFIG_NAME).with_suffix(".json.lock")

    migrated = False
    quarantined_count = 0

    with file_lock(lock_path, timeout_seconds=lock_timeout_seconds):
        config = _load_config(project_root)
        state = config.get(MIGRATION_STATE_KEY)

        if state == "in_progress":
            config = _recover_migration(project_root, config)
            state = config.get(MIGRATION_STATE_KEY)
            migrated = True
        elif state != "complete":
            # Either never migrated OR legacy installation from before the
            # refactor. Both paths go through the migration routine.
            config = _migrate_legacy_array_to_dir(project_root, config)
            migrated = True

        quarantined_count = int(config.get(MIGRATION_QUARANTINED_COUNT_KEY, 0))

        entry_path = _write_entry_file(project_root, entry, overwrite=True)
        retention_deleted = _apply_retention(project_root, keep_last=retention)

    return {
        "entry_path": str(entry_path.relative_to(project_root)),
        "migrated": migrated,
        "quarantined_count": quarantined_count,
        "retention_deleted": retention_deleted,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    p.add_argument("--project-root", default=".")
    p.add_argument(
        "--run-id",
        required=True,
        help="Canonical run_id (iterate-YYYY-MM-DD-short-slug)",
    )
    p.add_argument(
        "--entry-json",
        required=True,
        help=(
            "JSON object with type, complexity, branch, tests_passed, "
            "optional spec, optional adr"
        ),
    )
    p.add_argument(
        "--retention",
        type=int,
        default=ITERATE_RETENTION,
        help=f"Keep at most N entries post-migration (default {ITERATE_RETENTION})",
    )
    p.add_argument("--lock-timeout", type=float, default=10.0)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        extra = json.loads(args.entry_json)
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid --entry-json: {exc}", file=sys.stderr)
        return 1
    if not isinstance(extra, dict):
        print("ERROR: --entry-json must be a JSON object", file=sys.stderr)
        return 1
    for forbidden in ("run_id", "date"):
        if forbidden in extra:
            print(
                f"ERROR: --entry-json must not set {forbidden} (canonical fields)",
                file=sys.stderr,
            )
            return 1

    entry: dict[str, Any] = {
        "run_id": args.run_id,
        "date": now_utc_iso(),
        **extra,
    }

    try:
        result = append_iterate_entry(
            Path(args.project_root),
            entry,
            lock_timeout_seconds=args.lock_timeout,
            retention=args.retention,
        )
    except LockTimeout as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except IterateAppendError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({"entry": entry, **result}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
