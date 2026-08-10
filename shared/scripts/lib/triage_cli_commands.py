"""Subcommand handlers for `tools/triage_cli.py`.

Split out so the CLI module stays thin argparse wiring under the 300-LOC
guideline (iterate-2026-08-08-triage-amend-event — the `amend` subcommand's
handler pushed the combined file over). `triage_cli.py` re-exports nothing;
it imports these functions directly and wires them as `set_defaults(func=...)`
targets, so this split is purely a file-boundary move — no behavior changed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from triage import (  # noqa: E402
    KINDS,
    SEVERITIES,
    SEVERITY_RANK,
    STATUSES,
    _append_ids_at,
    _outbox_path,
    _triage_path,
    amend_triage_item,
    mark_status,
    read_all_items,
    StatusPreconditionError,
)
from shared_lib_loader import load_shared_lib  # noqa: E402
from lib.triage_amend import has_amend_content, validate_amend_event  # noqa: E402
from lib.triage_contract import build_listing  # noqa: E402
from lib.triage_delivery import format_pending_delivery_notice  # noqa: E402
from lib.triage_integrity import store_facts  # noqa: E402
from lib.triage_render import format_item, render_deferred_section  # noqa: E402
from tools.triage_promote import (  # noqa: E402
    TransitionPreconditionError,
    defer,
    dismiss,
    promote,
    sanitize_reason,
    unpark,
)

_BY_LABEL = "cli"
LockTimeout = load_shared_lib("file_lock").LockTimeout

# Stable machine contract.  Keep these values append-only: callers may branch
# on them without parsing human stderr text.
EXIT_USAGE = 2
EXIT_PRECONDITION = 3
EXIT_NOT_FOUND = 4
EXIT_STORE_UNINITIALISED = 5
EXIT_LOCK_TIMEOUT = 6


def ensure_utf8_stdout() -> None:
    """Pin stdout to UTF-8 regardless of the console codepage.

    On Windows ``sys.stdout`` defaults to the legacy codepage (cp1252), so
    writing ``ensure_ascii=False`` JSON — or a stripped-but-non-ASCII human
    line (`triage_render.safe_display` deliberately keeps >= 0xA0) — crashed with
    ``UnicodeEncodeError`` for any item title/detail carrying emoji/CJK/umlauts
    (iterate-2026-06-10-triage-cli-json-utf8; found by the webui
    pending-delivery-badge boundary probe). ``list --json`` is a machine
    contract consumed by the WebUI live-view: its bytes MUST be UTF-8.
    UTF-8 encodes all of Unicode, so the strict error handler can't raise.
    """
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass  # detached/closed stream — let the write surface the error


def cmd_list(args: argparse.Namespace) -> int:
    ensure_utf8_stdout()
    project_root = Path(args.project_root)
    resolved = read_all_items(project_root)
    items = [it for it in resolved if it.get("status") == "triage"]
    # A park whose revisit date has arrived already resolved back to `triage`
    # above, so it lands in the open list without anything here noticing.
    deferred = [it for it in resolved if it.get("status") == "snoozed"]
    corruption, undelivered, undelivered_amends = store_facts(
        _triage_path(project_root), _outbox_path(project_root),
        applied_statuses=STATUSES,
        is_valid_amend=lambda event: has_amend_content(event) and validate_amend_event(
            event, severities=SEVERITIES, kinds=KINDS),
    )
    if getattr(args, "json", False):
        return _emit_json(project_root, items, deferred, undelivered,
                          undelivered_amends, corruption)
    if not items:
        sys.stdout.write("No open triage items.\n\n")
    for item in items:
        sys.stdout.write(format_item(item) + "\n\n")
    # A deferred entry remains actionable and is therefore rendered separately.
    for block in render_deferred_section(deferred, SEVERITY_RANK):
        sys.stdout.write(block + "\n\n")
    # A dismissed-but-buffered item is in neither section, so this is its only
    # human-visible delivery signal; amend delivery is exposed in the JSON contract.
    if undelivered:
        sys.stdout.write(format_pending_delivery_notice(undelivered) + "\n\n")
    return 0


def _emit_json(project_root: Path, items: list[dict], deferred: list[dict],
               undelivered: set, undelivered_amends: set, corruption: list) -> int:
    """Serialise the machine contract. Its shape lives in `lib.triage_contract`."""
    payload = build_listing(
        items, deferred,
        tracked_ids=_append_ids_at(_triage_path(project_root)),
        outbox_ids=_append_ids_at(_outbox_path(project_root)),
        severity_rank=SEVERITY_RANK,
        undelivered_status_ids=undelivered,
        undelivered_amend_ids=undelivered_amends,
        corruption=corruption,
    )
    sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return 0


def _resolved_item(project_root: Path, item_id: str) -> dict:
    """Fetch one union-resolved item, preserving the store's own overlay rules."""
    if not _triage_path(project_root).exists() and not _outbox_path(project_root).exists():
        raise FileNotFoundError("triage store not initialised")
    for item in read_all_items(project_root):
        if item.get("id") == item_id:
            return item
    raise KeyError(item_id)


def _emit_result(args: argparse.Namespace, operation: str, item: dict) -> None:
    if getattr(args, "json", False):
        ensure_utf8_stdout()
        sys.stdout.write(json.dumps({"operation": operation, "item": item}, ensure_ascii=False) + "\n")


def _command_error(exc: Exception) -> int:
    if isinstance(exc, (StatusPreconditionError, TransitionPreconditionError)):
        code, label = EXIT_PRECONDITION, "status precondition failed"
    elif isinstance(exc, KeyError):
        code, label = EXIT_NOT_FOUND, "triage item not found"
    elif isinstance(exc, FileNotFoundError):
        code, label = EXIT_STORE_UNINITIALISED, "triage store not initialised"
    elif isinstance(exc, LockTimeout):
        code, label = EXIT_LOCK_TIMEOUT, "triage lock timeout"
    else:
        code, label = EXIT_USAGE, "invalid command"
    sys.stderr.write(f"error: {label}: {exc}\n")
    return code


def _optional_reason(raw: str | None) -> str | None:
    """Keep absent WebUI reasons absent, but validate every supplied value."""
    if raw is None:
        return None
    if not raw.strip():
        for ch in raw:
            if ord(ch) < 0x20 or ord(ch) == 0x7F:
                raise ValueError(f"--reason contains control character (0x{ord(ch):02X})")
        return None
    return sanitize_reason(raw)


def cmd_promote(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root)
    try:
        result = promote(
            project_root,
            item_id=args.item_id,
            task_ref=args.task_ref,
            reason=args.reason,
            by=_BY_LABEL,
            include_item=True,
        )
        item = result["item"]
    except (ValueError, KeyError, FileNotFoundError, LockTimeout) as exc:
        return _command_error(exc)

    if getattr(args, "json", False):
        _emit_result(args, "promote", item)
    else:
        sys.stderr.write(f"promoted {result['id']} → {result['promotedTaskId']}\n")
    return 0


def _status_flip(
    decide: Callable[..., dict], args: argparse.Namespace, verb: str, operation: str,
    **extra,
) -> int:
    """Shared dispatch for the decisions that need only a reason (plus, for a
    park, the date it comes back on).

    Promote is not routed through here — it also takes a task reference and
    reports the task it was linked to.
    """
    try:
        result = decide(
            Path(args.project_root),
            item_id=args.item_id,
            reason=args.reason,
            by=_BY_LABEL,
            include_item=True,
            **extra,
        )
        item = result["item"]
    except (ValueError, KeyError, FileNotFoundError, LockTimeout) as exc:
        return _command_error(exc)

    if getattr(args, "json", False):
        _emit_result(args, operation, item)
    else:
        sys.stderr.write(f"{verb} {result['id']} (reason: {result['reason']})\n")
    return 0


def cmd_dismiss(args: argparse.Namespace) -> int:
    """Dismiss through the WebUI-compatible JSON path when reason is absent."""
    if getattr(args, "json", False):
        try:
            reason = _optional_reason(args.reason)
            _, item = mark_status(
                Path(args.project_root), args.item_id, new_status="dismissed",
                by=_BY_LABEL, reason=reason, expected_status="triage", return_item=True,
            )
        except (ValueError, KeyError, FileNotFoundError, LockTimeout) as exc:
            return _command_error(exc)
        _emit_result(args, "dismiss", item)
        return 0
    return _status_flip(dismiss, args, "dismissed", "dismiss")


def cmd_defer(args: argparse.Namespace) -> int:
    return _status_flip(defer, args, "deferred", "defer", revisit_at=args.revisit)


def cmd_unpark(args: argparse.Namespace) -> int:
    return _status_flip(unpark, args, "un-parked", "unpark")


def cmd_amend(args: argparse.Namespace) -> int:
    """AC9: the CLI is the human-only amend writer this iterate ships; `by`
    is always the fixed `_BY_LABEL` — no `--by` flag, per the operator's own
    scoping decision (human, via command line)."""
    project_root = Path(args.project_root)
    try:
        amend_result = amend_triage_item(
            project_root, args.item_id, by=_BY_LABEL,
            title=args.title, detail=args.detail,
            severity=args.severity, kind=args.kind,
            expected_status="triage",
            return_item=True,
        )
        to_outbox, item = amend_result
    except (ValueError, KeyError, FileNotFoundError, LockTimeout) as exc:
        return _command_error(exc)

    changed = [f for f, v in (
        ("title", args.title), ("detail", args.detail),
        ("severity", args.severity), ("kind", args.kind),
    ) if v is not None]
    if getattr(args, "json", False):
        _emit_result(args, "amend", item)
        return 0
    sys.stderr.write(f"amended {args.item_id} ({', '.join(changed)})\n")
    if to_outbox:
        # Delivery-visibility parity for `amend` is deferred scope (AC15) — this
        # is the operator's only signal the correction hasn't reached a branch
        # yet (Stage-3 doubt review, finding 1).
        sys.stderr.write(
            "note: buffered in the local outbox, not yet on any branch — "
            "delivered on the next iterate's sweep\n"
        )
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """Read one card through the same union resolver used by the write result."""
    try:
        item = _resolved_item(Path(args.project_root), args.item_id)
    except (KeyError, FileNotFoundError) as exc:
        return _command_error(exc)
    if getattr(args, "json", False):
        _emit_result(args, "show", item)
    else:
        ensure_utf8_stdout()
        sys.stdout.write(format_item(item) + "\n")
    return 0


def cmd_snooze(args: argparse.Namespace) -> int:
    """WebUI-compatible park: unlike human ``defer``, reason/date are optional."""
    try:
        reason = _optional_reason(args.reason)
        _, item = mark_status(
            Path(args.project_root), args.item_id, new_status="snoozed", by=_BY_LABEL,
            reason=reason, revisit_at=args.revisit, expected_status="triage",
            require_future_revisit=True, return_item=True,
        )
    except (ValueError, KeyError, FileNotFoundError, LockTimeout) as exc:
        return _command_error(exc)
    if getattr(args, "json", False):
        _emit_result(args, "snooze", item)
    else:
        sys.stderr.write(f"snoozed {args.item_id}\n")
    return 0
