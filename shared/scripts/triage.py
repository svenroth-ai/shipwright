"""Triage Inbox storage API.

Append-only JSONL store under `.shipwright/triage.jsonl` for findings
from hooks, scans, and audits. Triage is the pre-backlog intake; the
backlog (ExternalTask in shipwright-webui) is a separate store reached
via the explicit `promote` action.

On-disk format (JSONL, camelCase wire keys to match webui ExternalTask):

  Line 1 (header):
    {"v":1,"schema":"triage","created":"<ISO>"}

  Append event:
    {"event":"append","id":"trg-XXXXXXXX","ts":"<ISO>","originalTs":"<ISO>",
     "source":"phaseQuality","severity":"high","kind":"bug","title":"...",
     "detail":"...","evidencePath":null,"runId":null,"commit":null,
     "status":"triage","suggestedPriority":"P1","suggestedDomain":"engineering"}

  Status event:
    {"event":"status","id":"trg-XXXXXXXX","ts":"<ISO>","newStatus":"...",
     "by":"...","reason":null,"promotedTaskId":null}

Status resolution is by **file order** (later valid line wins); the
reader is tolerant and skips lines that fail JSONDecodeError.

The module lives at `shared/scripts/triage.py` (outside `lib/`) per
ADR-045 so it can be imported from `shared/tests/` AND
`plugins/*/tests|scripts/` without colliding on `sys.modules['lib']`.

Cross-process file locking mirrors
`shared/scripts/tools/record_event.py:_FileLock`.
"""

from __future__ import annotations

import json
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# ---------------------------------------------------------------------------
# Constants (Single Source of Truth — tests assert against these)
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1
TRIAGE_FILE = "triage.jsonl"
_SHIPWRIGHT_DIR = ".shipwright"

STATUSES = ("triage", "promoted", "dismissed", "snoozed")
SEVERITIES = ("critical", "high", "medium", "low", "info")
KINDS = ("bug", "feature", "improvement", "compliance", "maintenance")
KNOWN_SOURCES = (
    "phaseQuality",
    "compliance",
    "security",
    "performance",
    "ci",
    "iterate",
    "manual",
)

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

PRIORITY_FROM_SEVERITY = {
    "critical": "P0",
    "high": "P1",
    "medium": "P2",
    "low": "P3",
    "info": "P3",
}

DEFAULT_DOMAIN = "engineering"
DOMAIN_FROM_SOURCE = {"compliance": "compliance"}


# ---------------------------------------------------------------------------
# Pure mapping helpers
# ---------------------------------------------------------------------------

def suggest_priority_from_severity(severity: str) -> str:
    """Pure: severity → P0..P3.

    Raises ValueError on unknown severity (forces producers to pick from
    the canonical SEVERITIES enum).
    """
    try:
        return PRIORITY_FROM_SEVERITY[severity]
    except KeyError as exc:
        raise ValueError(
            f"unknown severity {severity!r}; expected one of {SEVERITIES}"
        ) from exc


def suggest_domain_from_source(source: str) -> str:
    """Pure: source → domain. Falls back to DEFAULT_DOMAIN for any
    source not in DOMAIN_FROM_SOURCE.
    """
    return DOMAIN_FROM_SOURCE.get(source, DEFAULT_DOMAIN)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _triage_path(project_root: Path | str) -> Path:
    return Path(project_root) / _SHIPWRIGHT_DIR / TRIAGE_FILE


def _lock_path(project_root: Path | str) -> Path:
    return Path(project_root) / _SHIPWRIGHT_DIR / (TRIAGE_FILE + ".lock")


def _now_z() -> str:
    """ISO-8601 UTC timestamp with `Z` suffix (matches wire format)."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _generate_id() -> str:
    """Generate a unique triage item ID: `trg-` + 8 hex chars from UUID4."""
    return f"trg-{uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# File locking (cross-platform; mirrors record_event.py:_FileLock)
# ---------------------------------------------------------------------------

class _FileLock:
    """Cross-platform mutex via a dedicated `.lock` sidecar file."""

    def __init__(self, lock_path: str | Path):
        self._lock_path = Path(lock_path)
        self._fp = None

    def __enter__(self):
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = open(self._lock_path, "w", encoding="utf-8")
        if sys.platform == "win32":
            import msvcrt
            import time
            while True:
                try:
                    msvcrt.locking(self._fp.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.001)
        else:
            import fcntl
            fcntl.flock(self._fp, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        if self._fp:
            if sys.platform == "win32":
                import msvcrt
                try:
                    msvcrt.locking(self._fp.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl
                fcntl.flock(self._fp, fcntl.LOCK_UN)
            self._fp.close()


# ---------------------------------------------------------------------------
# Header bootstrap
# ---------------------------------------------------------------------------

def _has_header(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        first_raw = path.read_text(encoding="utf-8").split("\n", 1)[0].strip()
    except OSError:
        return False
    if not first_raw:
        return False
    try:
        first = json.loads(first_raw)
    except json.JSONDecodeError:
        return False
    return first.get("schema") == "triage" and "v" in first


def _ensure_header(project_root: Path | str) -> None:
    """Create `.shipwright/triage.jsonl` with the schema header if missing.

    Idempotent — never overwrites an existing header. Caller must hold
    the file lock.
    """
    path = _triage_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if _has_header(path):
        return
    header = {
        "v": SCHEMA_VERSION,
        "schema": "triage",
        "created": _now_z(),
    }
    line = json.dumps(header, ensure_ascii=False, separators=(",", ":")) + "\n"
    # If file exists but has no header (corrupted bootstrap), prepend; else create.
    if path.exists() and path.stat().st_size > 0:
        existing = path.read_text(encoding="utf-8")
        path.write_text(line + existing, encoding="utf-8")
    else:
        path.write_text(line, encoding="utf-8")


# ---------------------------------------------------------------------------
# Low-level read
# ---------------------------------------------------------------------------

def _iter_raw_lines(project_root: Path | str) -> list[dict]:
    """Tolerant reader — skip JSONDecodeError lines, keep file order."""
    path = _triage_path(project_root)
    if not path.exists():
        return []
    out: list[dict] = []
    for i, line in enumerate(path.open("r", encoding="utf-8")):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            warnings.warn(
                f"Corrupt triage line at {path.name}:{i + 1}, skipping",
                stacklevel=2,
            )
    return out


# ---------------------------------------------------------------------------
# Public API: append
# ---------------------------------------------------------------------------

def append_triage_item(
    project_root: Path | str,
    *,
    source: str,
    severity: str,
    kind: str,
    title: str,
    detail: str,
    evidence_path: str | None = None,
    run_id: str | None = None,
    commit: str | None = None,
) -> str:
    """Append a new triage item. Returns the new `trg-<8hex>` id.

    Auto-creates `.shipwright/triage.jsonl` with the schema header on
    first call (so producers are robust against adopt-not-yet-run repos
    — HIGH-3 from external review).

    Validates `severity` and `kind` against the SSoT enums; raises
    ValueError on unknown values. `source` is free-form (open vocab —
    new producers don't need code changes here), but
    `suggest_domain_from_source` only special-cases `compliance`.
    """
    if severity not in SEVERITIES:
        raise ValueError(
            f"unknown severity {severity!r}; expected one of {SEVERITIES}"
        )
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {KINDS}")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be a non-empty string")

    item_id = _generate_id()
    ts = _now_z()
    event = {
        "event": "append",
        "id": item_id,
        "ts": ts,
        "originalTs": ts,
        "source": source,
        "severity": severity,
        "kind": kind,
        "title": title,
        "detail": detail,
        "evidencePath": evidence_path,
        "runId": run_id,
        "commit": commit,
        "status": "triage",
        "suggestedPriority": suggest_priority_from_severity(severity),
        "suggestedDomain": suggest_domain_from_source(source),
    }
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"

    with _FileLock(_lock_path(project_root)):
        _ensure_header(project_root)
        path = _triage_path(project_root)
        with open(path, "a", encoding="utf-8") as fp:
            fp.write(line)
            fp.flush()
            os.fsync(fp.fileno())

    return item_id


# ---------------------------------------------------------------------------
# Public API: mark status
# ---------------------------------------------------------------------------

def mark_status(
    project_root: Path | str,
    item_id: str,
    *,
    new_status: str,
    by: str,
    reason: str | None = None,
    promoted_task_id: str | None = None,
) -> None:
    """Append a status event for an existing item.

    Never mutates prior lines. Idempotent on the resolved view (re-marking
    the same status is allowed and adds to history but doesn't change
    `read_all_items` output).

    Raises:
        FileNotFoundError: if `.shipwright/triage.jsonl` doesn't exist.
        KeyError: if `item_id` is not present in the file.
        ValueError: if `new_status` is not a known status.
    """
    if new_status not in STATUSES:
        raise ValueError(
            f"unknown status {new_status!r}; expected one of {STATUSES}"
        )

    path = _triage_path(project_root)
    if not path.exists():
        raise FileNotFoundError(
            f"triage store not initialized at {path}; "
            f"run /shipwright-adopt or append an item first"
        )

    # Confirm id exists (under lock for read-modify-write safety)
    with _FileLock(_lock_path(project_root)):
        existing_ids = {
            line["id"]
            for line in _iter_raw_lines(project_root)
            if isinstance(line, dict) and line.get("event") == "append"
        }
        if item_id not in existing_ids:
            raise KeyError(item_id)

        event = {
            "event": "status",
            "id": item_id,
            "ts": _now_z(),
            "newStatus": new_status,
            "by": by,
            "reason": reason,
            "promotedTaskId": promoted_task_id,
        }
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        with open(path, "a", encoding="utf-8") as fp:
            fp.write(line)
            fp.flush()
            os.fsync(fp.fileno())


# ---------------------------------------------------------------------------
# Public API: read (with status resolution)
# ---------------------------------------------------------------------------

def read_all_items(project_root: Path | str) -> list[dict]:
    """Return the resolved view: one dict per item, last-status-wins by
    file order. Items with status `triage` retain their original append
    fields; status flips overlay `status`, `ts`, plus optional
    `reason`/`promotedTaskId`/`by` from the most recent status event.

    Returns `[]` when the file is missing or contains only the header
    (so consumers don't need a separate existence check).
    """
    resolved: dict[str, dict] = {}
    for raw in _iter_raw_lines(project_root):
        if not isinstance(raw, dict):
            continue
        event = raw.get("event")
        if event == "append":
            item_id = raw.get("id")
            if not isinstance(item_id, str):
                continue
            # Initial record — strip "event" key (internal)
            item = {k: v for k, v in raw.items() if k != "event"}
            item["statusBy"] = None
            item["statusReason"] = None
            item["promotedTaskId"] = None
            resolved[item_id] = item
        elif event == "status":
            item_id = raw.get("id")
            if not isinstance(item_id, str) or item_id not in resolved:
                # status for unknown id (corrupt or out-of-order) — skip
                continue
            item = resolved[item_id]
            new_status = raw.get("newStatus")
            if new_status in STATUSES:
                item["status"] = new_status
            item["ts"] = raw.get("ts", item.get("ts"))
            item["statusBy"] = raw.get("by")
            item["statusReason"] = raw.get("reason")
            if raw.get("promotedTaskId") is not None:
                item["promotedTaskId"] = raw["promotedTaskId"]
        # header / unknown events ignored

    return list(resolved.values())
