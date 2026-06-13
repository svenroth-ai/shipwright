"""Triage Inbox storage API.

Append-only JSONL store under `.shipwright/triage.jsonl` for findings
from hooks, scans, and audits. Triage is the pre-backlog intake; the
backlog (ExternalTask in shipwright-webui) is a separate store reached
via the explicit `promote` action.

On-disk format (JSONL, camelCase wire keys to match webui ExternalTask)
is authoritatively codified at ``shared/schemas/triage_item.schema.json``
(iterate-2026-05-21-triage-producer-contract / ADR-054). Three event
kinds share the file: a one-time header (line 1), ``append`` events
(one per new triage item), and ``status`` events (one per
Promote / Dismiss / Snooze). See the schema for the full field list
including optional `dedupKey`, `launchPayload`, `frId`, `suiteId`,
`eventId`.

Status resolution is by **file order** (later valid line wins); the
reader is tolerant and skips lines that fail JSONDecodeError.

The module lives at `shared/scripts/triage.py` (outside `lib/`) per
ADR-045 so it can be imported from `shared/tests/` AND
`plugins/*/tests|scripts/` without colliding on `sys.modules['lib']`.

Cross-process file locking uses the shared `FileLock` class from
`shared/scripts/lib/file_lock.py` (aliased to the historical private
`_FileLock` name on import; iterate-2026-06-13-shc-file-lock).
"""

from __future__ import annotations

import json
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# Wire up shared/scripts so `lib.file_lock` resolves at import time. triage.py
# lives at shared/scripts/triage.py (parent == shared/scripts), and its
# consumers add that dir to sys.path; do it here too so the module-level
# import below works regardless of import path.
_SCRIPTS_ROOT = Path(__file__).resolve().parent  # shared/scripts
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

# Cross-platform append-log mutex. Extracted to lib/file_lock.py
# (iterate-2026-06-13-shc-file-lock); aliased to the historical private name so
# module attribute `triage._FileLock` stays importable (sweep_outbox, triage_gc,
# reconcile_triage, and tests do `from triage import _FileLock` /
# `triage._FileLock`) and the `with _FileLock(...)` call sites resolve via the
# module global.
from lib.file_lock import FileLock as _FileLock  # noqa: E402

# ---------------------------------------------------------------------------
# Constants (Single Source of Truth — tests assert against these)
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1
TRIAGE_FILE = "triage.jsonl"
# Per-tree, GITIGNORED transient buffer for background main-tree producers
# (campaign 2026-06-08-triage-outbox-delivery / D1). Idle-main producers route
# here instead of the tracked TRIAGE_FILE so the tracked log stays clean (no
# main drift); the sweep (D2) folds it into the PR branch and GCs it. The
# outbox carries NO schema header — it is a buffer, not a store — and shares
# the canonical TRIAGE_FILE lock so producer-append and sweep serialize.
OUTBOX_FILE = "triage.outbox.jsonl"
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
    "f0.5",
    "drift",
    "github",
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

def _check_optional_str(name: str, value: object) -> None:
    """Reject non-string, non-None values for camelCase optional fields.

    Iterate B0 (2026-05-21) — caught by external review (H1): producers
    that pass `fr_id=42` (or any non-string) silently wrote an integer to
    disk, breaking the JSON schema at validation time. This guard turns
    that into a producer-side ValueError so misuse fails fast.
    """
    if value is None or isinstance(value, str):
        return
    raise ValueError(
        f"{name!r} must be str or None, got {type(value).__name__}"
    )


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


def _outbox_path(project_root: Path | str) -> Path:
    return Path(project_root) / _SHIPWRIGHT_DIR / OUTBOX_FILE


def _lock_path(project_root: Path | str) -> Path:
    # The outbox shares this ONE canonical lock so producer-append and the D2
    # sweep (which holds it across read->commit) serialize — do NOT add a
    # separate outbox lock (Codex Q4 data-loss invariant).
    return Path(project_root) / _SHIPWRIGHT_DIR / (TRIAGE_FILE + ".lock")


def should_route_to_outbox(project_root: Path | str) -> bool:
    """True iff a real delivery path exists AND HEAD is the default branch.

    BOTH required (D1 review cascade, F2): (1) an ``origin`` remote — the outbox
    is only delivered via the D2 sweep → PR → ``origin`` path, and
    ``default_branch`` falls back to literal ``"main"`` with no ``origin/HEAD``,
    so a no-origin repo on ``main`` would route spuriously and BURY the finding;
    (2) ``current_branch == default_branch`` (idle main, not an ``iterate/*``
    branch whose writes ship in the PR — branch-based, NOT ``is_worktree``).
    Every no-origin repo, non-default branch, and git error fail safe to tracked.
    """
    try:
        scripts_dir = str(Path(__file__).resolve().parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from lib.worktree_isolation import (  # noqa: PLC0415
            current_branch,
            default_branch,
            run_git,
        )

        root = Path(project_root)
        has_origin = (
            run_git(["remote", "get-url", "origin"], cwd=root, check=False).returncode
            == 0
        )
        return has_origin and current_branch(root) == default_branch(root)
    except Exception:  # noqa: BLE001
        return False


def _now_z() -> str:
    """ISO-8601 UTC timestamp with `Z` suffix (matches wire format)."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _generate_id() -> str:
    """Generate a unique triage item ID: `trg-` + 8 hex chars from UUID4."""
    return f"trg-{uuid4().hex[:8]}"


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

def _iter_raw_lines_at(path: Path) -> list[dict]:
    """Tolerant reader for ONE file — skip JSONDecodeError lines, keep order.

    ``line.strip()`` already absorbs a trailing ``\\r`` (CRLF probe), so a
    Windows-written or human-edited outbox line round-trips unchanged.
    """
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


def _append_ids_at(path: Path) -> set[str]:
    """Set of `append`-event ids in ONE file (residence probe for mark_status)."""
    return {
        ln["id"] for ln in _iter_raw_lines_at(path)
        if isinstance(ln, dict) and ln.get("event") == "append"
    }


def _iter_raw_lines(project_root: Path | str) -> list[dict]:
    """Tolerant union reader — tracked lines THEN outbox lines, file order.

    The union (campaign 2026-06-08-triage-outbox-delivery / D1) makes
    background producer appends + status-flips that land in the outbox visible
    to every Python consumer immediately, without a sweep. Resolution is by id
    in :func:`read_all_items`, so a line present in both (post-sweep, pre-GC)
    collapses to one item.
    """
    out: list[dict] = []
    for path in (_triage_path(project_root), _outbox_path(project_root)):
        out.extend(_iter_raw_lines_at(path))
    return out


# ---------------------------------------------------------------------------
# Low-level write (caller holds the lock)
# ---------------------------------------------------------------------------

def _append_line(project_root: Path | str, line: str, *, to_outbox: bool) -> None:
    """Append one JSONL line under the held lock.

    Tracked target → ensure the schema header first. Outbox target → no
    header (it is a transient buffer; :func:`read_all_items` ignores
    non-append/status events anyway), just ensure the directory exists.
    """
    if to_outbox:
        path = _outbox_path(project_root)
        path.parent.mkdir(parents=True, exist_ok=True)
    else:
        _ensure_header(project_root)
        path = _triage_path(project_root)
    # FIX A: gitignored outbox → newline="" keeps LF on all platforms (D2 ADR).
    with open(path, "a", encoding="utf-8", newline="" if to_outbox else None) as fp:
        fp.write(line)
        fp.flush()
        os.fsync(fp.fileno())


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
    dedup_key: str | None = None,
    launch_payload: str | None = None,
    fr_id: str | None = None,
    suite_id: str | None = None,
    event_id: str | None = None,
    to_outbox: bool = False,
) -> str:
    """Append a new triage item. Returns the new `trg-<8hex>` id.

    `to_outbox` (D1): True writes the per-tree GITIGNORED outbox buffer
    instead of the tracked store (idle-main background producers → no main
    drift). Default False preserves prior behavior; the write still serializes
    on the canonical lock and is visible immediately via the union reader.

    Auto-creates `.shipwright/triage.jsonl` with the schema header on
    first call (so producers are robust against adopt-not-yet-run repos
    — HIGH-3 from external review).

    Validates `severity` and `kind` against the SSoT enums; raises
    ValueError on unknown values. `source` is free-form (open vocab —
    new producers don't need code changes here), but
    `suggest_domain_from_source` only special-cases `compliance`.

    `dedup_key` is an optional producer-supplied stable identifier
    (e.g. Phase-Quality check id `C1`, compliance finding code
    `RLS-MISSING-X`). It does NOT enforce uniqueness on the wire — see
    `append_triage_item_idempotent` for the deduplicated path. The
    field is preserved so the aggregator and downstream tooling can
    correlate items across runs.

    `launch_payload` (iterate-2026-05-20-triage-launch-surface) is an optional
    ready-to-paste block (slash command + context) the operator copies into a
    new session. Stored verbatim under `launchPayload`, ALWAYS persisted (null
    when omitted), frozen at first append (AC-8).

    `fr_id` / `suite_id` / `event_id` (iterate-2026-05-21-triage-producer-contract):
    optional cross-artifact refs the RTM generator uses to render
    `FAIL → [trg-XXX](...)` links. Persisted under camelCase `frId` / `suiteId`
    / `eventId`; null is the wire default. Schema:
    `shared/schemas/triage_item.schema.json`.
    """
    if severity not in SEVERITIES:
        raise ValueError(
            f"unknown severity {severity!r}; expected one of {SEVERITIES}"
        )
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {KINDS}")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be a non-empty string")
    _check_optional_str("fr_id", fr_id)
    _check_optional_str("suite_id", suite_id)
    _check_optional_str("event_id", event_id)

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
        "dedupKey": dedup_key,
        "launchPayload": launch_payload,
        "frId": fr_id,
        "suiteId": suite_id,
        "eventId": event_id,
        "status": "triage",
        "suggestedPriority": suggest_priority_from_severity(severity),
        "suggestedDomain": suggest_domain_from_source(source),
    }
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"

    with _FileLock(_lock_path(project_root)):
        _append_line(project_root, line, to_outbox=to_outbox)

    return item_id


def append_triage_item_idempotent(
    project_root: Path | str,
    *,
    source: str,
    severity: str,
    kind: str,
    title: str,
    detail: str,
    dedup_key: str,
    evidence_path: str | None = None,
    run_id: str | None = None,
    commit: str | None = None,
    match_commit: bool = True,
    window_seconds: int | None = 24 * 3600,
    launch_payload: str | None = None,
    fr_id: str | None = None,
    suite_id: str | None = None,
    event_id: str | None = None,
    to_outbox: bool = False,
) -> str | None:
    """Append a triage item only if no matching item is currently open.

    `to_outbox` (D1): write the gitignored outbox buffer instead of the tracked
    store (idle-main background producers). The dedup scan runs against the
    UNION (`read_all_items`), so an open match in EITHER file suppresses the
    append regardless of where the new line lands.

    Match = same `source` + `dedup_key` + (optionally) `commit` AND
    status is `triage` (items already promoted / dismissed / snoozed
    are not re-evaluated — operators get them back if the underlying
    issue re-fires under a new id).

    `window_seconds` controls the recency horizon:

    - ``int``  — only items appended within that many seconds count as
      duplicates. Re-firing after the window appends a new item.
      Phase-Quality producer uses 24h to deliberately re-flag stale
      issues daily.
    - ``None`` — no window check; any open `triage` item with the same
      key suppresses the append, regardless of age. Compliance
      producer uses this because the same finding code is the same
      issue indefinitely until the operator resolves it.

    Returns the new item id, or `None` if a duplicate was found and
    the append was skipped.

    **Atomicity:** the dedup scan and append happen inside the same
    file-lock critical section. Two concurrent producers with the same
    `(source, dedup_key, commit)` cannot both pass the dedup check and
    both append (HIGH-1 from external code review).
    """
    if not dedup_key:
        raise ValueError("dedup_key is required for idempotent append")

    cutoff: float | None
    if window_seconds is None:
        cutoff = None
    else:
        cutoff = datetime.now(timezone.utc).timestamp() - window_seconds

    # Build the new event payload up front so the critical section is
    # tight — only the read + decision + write happen under lock.
    if severity not in SEVERITIES:
        raise ValueError(
            f"unknown severity {severity!r}; expected one of {SEVERITIES}"
        )
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {KINDS}")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be a non-empty string")

    _check_optional_str("fr_id", fr_id)
    _check_optional_str("suite_id", suite_id)
    _check_optional_str("event_id", event_id)

    new_id = _generate_id()
    ts = _now_z()
    new_event = {
        "event": "append",
        "id": new_id,
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
        "dedupKey": dedup_key,
        "launchPayload": launch_payload,
        "frId": fr_id,
        "suiteId": suite_id,
        "eventId": event_id,
        "status": "triage",
        "suggestedPriority": suggest_priority_from_severity(severity),
        "suggestedDomain": suggest_domain_from_source(source),
    }
    new_line = json.dumps(new_event, ensure_ascii=False, separators=(",", ":")) + "\n"

    with _FileLock(_lock_path(project_root)):
        # Dedup-scan under the same lock — readers see the merged (union) view.
        for existing in read_all_items(project_root):
            if existing.get("status") != "triage":
                continue
            if existing.get("source") != source:
                continue
            if existing.get("dedupKey") != dedup_key:
                continue
            if match_commit and existing.get("commit") != commit:
                continue
            if cutoff is None:
                # Window-less dedup — any open match suppresses.
                return None
            original_ts = existing.get("originalTs") or existing.get("ts") or ""
            try:
                existing_dt = datetime.fromisoformat(
                    original_ts.replace("Z", "+00:00")
                )
                if existing_dt.timestamp() >= cutoff:
                    return None
            except ValueError:
                # Malformed ts → conservative: treat as recent, skip.
                return None

        # No duplicate — append.
        _append_line(project_root, new_line, to_outbox=to_outbox)

    return new_id


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
    """Append a status event for an existing item (never mutates prior lines).

    **Write target is DERIVED (never a caller flag), under the lock:** idle main
    with a delivery path (`should_route_to_outbox` — origin + HEAD==default) →
    outbox, symmetric with `append_triage_item` (2026-06-12). Else a tracked-item
    flip on idle main is undelivered drift (sweep delivers only the outbox;
    `reconcile_main_triage` is manual-CLI-only post-D2) → blocks a hand pull,
    never reaches origin; loss-proof via union-read + sweep + GC. Otherwise
    residence-derived: outbox-only → outbox (no orphan/resurrect); tracked/both →
    tracked (TRACKED-PREFERRED: a worktree flip ships in the PR).

    Raises:
        FileNotFoundError: if NEITHER the tracked store NOR the outbox exists.
        KeyError: if `item_id` is not an `append` id in (tracked ∪ outbox).
        ValueError: if `new_status` is not a known status.
    """
    if new_status not in STATUSES:
        raise ValueError(
            f"unknown status {new_status!r}; expected one of {STATUSES}"
        )

    if not _triage_path(project_root).exists() and not _outbox_path(project_root).exists():
        raise FileNotFoundError(
            f"triage store not initialized at {_triage_path(project_root)} "
            f"(nor outbox at {_outbox_path(project_root)}); "
            f"run /shipwright-adopt or append an item first"
        )

    # Derive residence + write the status to the SAME store, under the lock.
    with _FileLock(_lock_path(project_root)):
        tracked_ids = _append_ids_at(_triage_path(project_root))
        outbox_ids = _append_ids_at(_outbox_path(project_root))
        if item_id not in tracked_ids and item_id not in outbox_ids:
            raise KeyError(item_id)
        # Idle main → outbox (like append); else residence-derived. See docstring.
        to_outbox = should_route_to_outbox(project_root) or (item_id in outbox_ids and item_id not in tracked_ids)

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
        _append_line(project_root, line, to_outbox=to_outbox)


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

    **Two-pass union resolution (D1):** sources tracked ∪ outbox lines. Pass 1
    applies ALL `append` events (base records); Pass 2 applies ALL `status`
    events ordered by ``(ts, file-order)``. Load-bearing across the split: (1)
    the append-first split stops an OUTBOX `append` (status:triage) from
    clobbering a TRACKED `status` flip back to `triage`; (2) ``ts``-primary
    ordering makes the chronologically-later flip win regardless of source file
    (file order is only a STABLE tiebreaker for equal ts), preserving the
    single-file "later valid line wins by file order" contract. Both bugs were
    flagged by external review (OpenAI #5 / Gemini #1) and reproduced by probes.
    """
    raw_lines = [r for r in _iter_raw_lines(project_root) if isinstance(r, dict)]

    # Pass 1 — every append establishes a base record (union of both files).
    resolved: dict[str, dict] = {}
    for raw in raw_lines:
        if raw.get("event") != "append":
            continue
        item_id = raw.get("id")
        if not isinstance(item_id, str):
            continue
        # Initial record — strip "event" key (internal). A duplicate append for
        # the same id (post-sweep, pre-GC window) collapses to one record; the
        # later line's fields win, which is harmless (identical content).
        item = {k: v for k, v in raw.items() if k != "event"}
        item["statusBy"] = None
        item["statusReason"] = None
        item["promotedTaskId"] = None
        resolved[item_id] = item

    # Pass 2 — overlay status flips. Order by (ts, file-order): timestamp is
    # primary so a chronologically-later status in EITHER file wins; file order
    # is a STABLE tiebreaker for equal ts (clock-resolution collisions) so the
    # single-file contract "later valid line wins by file order" is preserved
    # exactly (within one file, appends are written in ascending ts; ties keep
    # file order). This resolves the cross-file status-vs-status ambiguity the
    # external plan review (OpenAI #5 / Gemini #1) flagged without breaking
    # same-ts determinism. ``enumerate`` index is the file-order tiebreaker;
    # ``_ts_key`` returns the ISO-8601-Z ``ts`` string, which sorts
    # lexicographically == chronologically (malformed ts → "" → earliest).
    def _ts_key(raw: dict) -> str:
        # Only a real ISO-8601-Z string participates in chronological ordering;
        # a malformed/missing ts (non-str, null, int) coerces to "" so it sorts
        # EARLIEST — i.e. is treated as "oldest / unknown time" and can never
        # outrank a later valid status (external code review, OpenAI High). The
        # file-order index then keeps malformed events stable among themselves.
        ts = raw.get("ts")
        return ts if isinstance(ts, str) else ""

    status_events = [
        (idx, raw) for idx, raw in enumerate(raw_lines)
        if raw.get("event") == "status"
    ]
    status_events.sort(key=lambda t: (_ts_key(t[1]), t[0]))
    for _idx, raw in status_events:
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

    return list(resolved.values())
