"""Schema, validation, normalization, and dual-mode read for iterate entries.

Historically iterate-finalization appended an entry to the
``iterate_history`` array inside ``shipwright_run_config.json``. Two
parallel iterates on an adopted project produced a guaranteed merge
conflict on that array.

This module introduces the file-per-iterate storage pattern:

    .shipwright/agent_docs/
      iterates/
        iterate-2026-04-23-feat-x.json   # one entry per file
        iterate-2026-04-23-feat-y.json
        _quarantine/
          invalid-legacy-*.json          # migration diagnostics
        _meta/                           # reserved for future indexes

The ``read_iterate_entries`` function is MERGE-mode across legacy array
and the new directory so partial migrations never hide data. The
``validate_iterate_entry`` function supports two modes (strict for new
writes, legacy-tolerant for reads + migration). The module is pure
data-layer: writes and locking live in
``shared/scripts/tools/append_iterate_entry.py``.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TypedDict


_logger = logging.getLogger("shipwright.iterate_entry")


ITERATES_DIRNAME = "iterates"
ITERATE_FILE_PREFIX = "iterate-"
ITERATE_FILE_SUFFIX = ".json"
QUARANTINE_SUBDIR = "_quarantine"
META_SUBDIR = "_meta"
RUN_CONFIG_NAME = "shipwright_run_config.json"

# Config keys that persist migration state
MIGRATION_STATE_KEY = "_iterate_migration_state"
MIGRATION_TS_KEY = "_iterate_migration_ts"
MIGRATION_QUARANTINED_COUNT_KEY = "_iterate_migration_quarantined_count"
MIGRATION_QUARANTINE_REPORT_KEY = "_iterate_migration_quarantine_report"

# Bounds that protect readers from malicious or corrupted repos.
MAX_ENTRY_FILE_BYTES = 64 * 1024

# Canonical run-id pattern used for new writes.
RUN_ID_STRICT = re.compile(r"^iterate-\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*$")

# Legacy-tolerant pattern accepted during read + migration.
RUN_ID_LEGACY = re.compile(r"^iterate[-_][A-Za-z0-9_.\-]+$")

# Set by policy; keep in sync with KEEP_A_CHANGELOG_CATEGORIES used by
# the changelog drop-directory writer.
_VALID_TYPES: frozenset[str] = frozenset({"feature", "change", "bug"})
_VALID_COMPLEXITIES: frozenset[str] = frozenset({"trivial", "small", "medium", "large"})


class IterateEntry(TypedDict, total=False):
    run_id: str
    date: str  # ISO-8601 UTC, ``...Z`` form for new writes
    type: Literal["feature", "change", "bug"]
    complexity: Literal["trivial", "small", "medium", "large"]
    branch: str
    spec: str | None
    tests_passed: bool
    adr: str | None


_REQUIRED_FIELDS: tuple[tuple[str, type], ...] = (
    ("run_id", str),
    ("date", str),
    ("type", str),
    ("complexity", str),
    ("branch", str),
    ("tests_passed", bool),
)


def sanitize_run_id_for_filename(run_id: str) -> str:
    """Normalize a run_id into a safe filename segment.

    Replaces path separators, control characters, and dots with ``-`` so
    legacy or malformed data cannot traverse outside
    ``.shipwright/agent_docs/iterates/``. Validation is a separate defense; this
    function must produce safe output even for inputs that ``validate_iterate_entry``
    would reject.
    """
    out_chars: list[str] = []
    for ch in run_id:
        codepoint = ord(ch)
        if ch in ("/", "\\", "..", ".", ":", "*", "?", '"', "<", ">", "|"):
            out_chars.append("-")
        elif codepoint < 0x20 or codepoint == 0x7F:
            out_chars.append("-")
        else:
            out_chars.append(ch)
    result = "".join(out_chars).strip("-")
    return result or "iterate-unknown"


def normalize_legacy_entry(raw: dict[str, Any]) -> dict[str, Any]:
    """Pre-pass that repairs common legacy variants before validation.

    Older projects may have mixed-case ``type`` / ``complexity`` values or
    conventional-commit-style shorthands (``feat`` / ``fix`` / ``refactor``).
    Normalizing here keeps the quarantine rate low for historical data.
    The caller is responsible for passing this output into
    ``validate_iterate_entry``; the return value is a new dict (input not
    mutated).
    """
    out = dict(raw)
    type_raw = out.get("type")
    if isinstance(type_raw, str):
        t = type_raw.strip().lower()
        out["type"] = {
            "feat": "feature",
            "feature": "feature",
            "fix": "bug",
            "bug": "bug",
            "bugfix": "bug",
            "refactor": "change",
            "change": "change",
            "chore": "change",
        }.get(t, t)
    complexity_raw = out.get("complexity")
    if isinstance(complexity_raw, str):
        out["complexity"] = complexity_raw.strip().lower()
    return out


def validate_iterate_entry(
    data: Any, *, strict: bool = True
) -> tuple[bool, str | None]:
    """Validate a candidate entry.

    ``strict=True`` (the default) is used when appending a newly produced
    entry. ``strict=False`` is used when migrating legacy data and accepts
    a broader run-id pattern so historical rows don't end up quarantined
    for cosmetic reasons.
    """
    if not isinstance(data, dict):
        return False, "entry must be a JSON object"

    for field, typ in _REQUIRED_FIELDS:
        if field not in data:
            return False, f"missing required field: {field}"
        if not isinstance(data[field], typ):
            return False, f"wrong type for {field}: expected {typ.__name__}"

    # Optional fields with type constraints when present.
    spec_val = data.get("spec")
    if spec_val is not None and not isinstance(spec_val, str):
        return False, "spec must be string or null"
    adr_val = data.get("adr")
    if adr_val is not None and not isinstance(adr_val, str):
        return False, "adr must be string or null"

    pattern = RUN_ID_STRICT if strict else RUN_ID_LEGACY
    if not pattern.match(data["run_id"]):
        return False, f"run_id malformed: {data['run_id']!r}"

    try:
        datetime.fromisoformat(data["date"].replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False, f"date not ISO-8601: {data['date']!r}"

    if data["type"] not in _VALID_TYPES:
        return False, f"invalid type: {data['type']!r}"
    if data["complexity"] not in _VALID_COMPLEXITIES:
        return False, f"invalid complexity: {data['complexity']!r}"

    return True, None


def _parse_utc(date_str: str) -> datetime:
    """Parse ISO-8601 into a tz-aware UTC datetime. Naive dates are assumed UTC."""
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def sort_key(entry: dict[str, Any]) -> tuple[datetime, str]:
    """Sort key that tolerates mixed timezone offsets.

    ISO-8601 lexical order is only reliable when all timestamps use the
    same offset. This function parses to tz-aware UTC and uses the run_id
    as a tiebreaker for identical timestamps.
    """
    try:
        dt = _parse_utc(entry.get("date", ""))
    except (ValueError, AttributeError):
        dt = datetime.min.replace(tzinfo=timezone.utc)
    return (dt, str(entry.get("run_id", "")))


def now_utc_iso() -> str:
    """Canonical ISO-8601 UTC timestamp (`...Z` form) for new writes."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def iterates_dir(project_root: Path) -> Path:
    return project_root / ".shipwright" / "agent_docs" / ITERATES_DIRNAME


def quarantine_dir(project_root: Path) -> Path:
    return iterates_dir(project_root) / QUARANTINE_SUBDIR


def entry_file_for(project_root: Path, run_id: str) -> Path:
    """Path to an iterate entry file for ``run_id``.

    Applies ``sanitize_run_id_for_filename`` even after validation —
    defense-in-depth against accidental bypass.
    """
    safe = sanitize_run_id_for_filename(run_id)
    return iterates_dir(project_root) / f"{safe}{ITERATE_FILE_SUFFIX}"


def _is_entry_file(path: Path) -> bool:
    """Gate that restricts what ``read_iterate_entries`` will load.

    Only accepts regular files named ``iterate-*.json`` under ``iterates_dir``.
    Skips symlinks, oversized files, quarantine + meta subdirs, and any
    file that doesn't match the canonical name pattern.
    """
    if not path.is_file():
        return False
    if path.is_symlink():
        return False
    if not path.name.startswith(ITERATE_FILE_PREFIX):
        return False
    if not path.name.endswith(ITERATE_FILE_SUFFIX):
        return False
    # Reject secondary-extension sidecars like ``<run_id>.plan.json`` — the
    # gitignored WebUI session-plan card (#358) lives in THIS same dir and would
    # otherwise be mistaken for an entry: it carries no ``date``, so it sorts as
    # the retention "oldest" and its ``unlink(entry_file_for(run_id))`` deletes
    # the REAL ``<run_id>.json`` entry, and it shadows ``find_entry_by_run_id``.
    # A canonical entry stem carries no ``.`` (``sanitize_run_id_for_filename``
    # maps ``.`` → ``-``), so a dot in the stem marks a non-entry sidecar.
    # (iterate-2026-07-11-phase-completed-per-split)
    if "." in path.name[: -len(ITERATE_FILE_SUFFIX)]:
        return False
    try:
        if path.stat().st_size > MAX_ENTRY_FILE_BYTES:
            return False
    except OSError:
        return False
    return True


def _read_legacy_array(project_root: Path) -> list[dict[str, Any]]:
    """Read ``iterate_history`` from ``shipwright_run_config.json``.

    Tolerant: absent file or absent field returns an empty list. Malformed
    JSON returns an empty list and the caller is responsible for surfacing
    the corruption via logs / verifier signals.
    """
    config_path = project_root / RUN_CONFIG_NAME
    if not config_path.exists():
        return []
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    raw = data.get("iterate_history")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _read_iterates_dir(project_root: Path) -> list[dict[str, Any]]:
    """Read all canonical iterate entry files under ``.shipwright/agent_docs/iterates/``.

    Corrupt or oversized files are skipped with a diagnostic on stderr so
    one bad file cannot wedge the whole reader. The caller can detect the
    skip via a non-empty corrupt-count signal exposed by the CLI wrapper.
    """
    directory = iterates_dir(project_root)
    if not directory.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(directory.iterdir()):
        if not _is_entry_file(path):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            _logger.warning("skip corrupt entry file %s: %s", path.name, exc)
            continue
        if isinstance(data, dict):
            entries.append(data)
    return entries


def read_iterate_entries(project_root: Path) -> list[dict[str, Any]]:
    """Merge legacy + modern sources into one sorted list (UTC date, run_id).

    The merge is deliberate: a partial migration (crash after writing some
    files) must not silently hide the remaining legacy entries. New-dir
    entries win on duplicate ``run_id`` so completed migrations don't
    resurrect outdated shapes.
    """
    legacy = _read_legacy_array(project_root)
    modern = _read_iterates_dir(project_root)

    by_run_id: dict[str, dict[str, Any]] = {}
    for entry in legacy:
        run_id = entry.get("run_id")
        if isinstance(run_id, str):
            by_run_id[run_id] = entry
    for entry in modern:
        run_id = entry.get("run_id")
        if isinstance(run_id, str):
            by_run_id[run_id] = entry

    return sorted(by_run_id.values(), key=sort_key)


def last_iterate_entry(project_root: Path) -> dict[str, Any] | None:
    """Return the most recent entry, or ``None`` if there is no history."""
    entries = read_iterate_entries(project_root)
    return entries[-1] if entries else None


def find_entry_by_run_id(project_root: Path, run_id: str) -> dict[str, Any] | None:
    """Look up a specific entry by ``run_id`` via the merged reader."""
    for entry in read_iterate_entries(project_root):
        if entry.get("run_id") == run_id:
            return entry
    return None
