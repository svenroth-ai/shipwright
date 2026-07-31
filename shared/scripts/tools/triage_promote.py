#!/usr/bin/env python3
"""The three triage decisions as library helpers, plus a promote-only CLI.

``promote`` / ``dismiss`` / ``defer`` wrap `triage.mark_status` with this
repo's CLI validation: the item must exist and still be undecided (`triage`);
moving out of a decided state is not offered here (use ``mark_status``).
Operator strings are sanitized — no control chars, task-ref ≤200, reason ≤500.

**Reference semantics the Command Center's Triage tab mirrors — NOT a code
path it shares**, so tightening validation here does not cover both surfaces
(verified divergence: its snooze route permits a reason-less park —
`shipwright-webui` `server/src/routes/triage.ts::parseDismissSnoozeBody`,
2026-07-27). Canonical statement: `shared/glossary.md` → *Defer (Snooze)*.

Usage:
    uv run shared/scripts/tools/triage_promote.py \
        --id trg-XXXXXXXX --task-ref "EXT:linear-ENG-123" [--reason TEXT]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from triage import (  # noqa: E402
    StatusPreconditionError,
    _outbox_path,
    _triage_path,
    mark_status,
    read_all_items,
)

_TASK_REF_MAX_LEN = 200
_REASON_MAX_LEN = 500

# Adjective per decided state. Read with .get: a KeyError HERE comes from the
# VALIDATION path, which the CLI maps to "triage item not found" — a wrong,
# quiet answer. The default stops a soft failure from lying.
_DECIDABLE = {
    "dismissed": "dismissable",
    "snoozed": "deferrable",
    "promoted": "promotable",
}


def _not_triage_error(item_id: str, current: object, new_status: str) -> ValueError:
    """The ONE wording for "this item is no longer open", both ways it is found.

    The pre-check below reads the store unlocked, so the item can be decided in
    the window between that read and the write; the store then refuses under its
    own lock. Both paths raise from here, so the CLI's documented message and
    exit code are identical whichever one fires and cannot drift apart
    (external plan review, finding #9).
    """
    return ValueError(
        f"item {item_id} has status={current!r}; only `triage` is "
        f"{_DECIDABLE.get(new_status, 'decidable')} from this CLI "
        f"(use mark_status for other transitions)"
    )


def _sanitize_single_line(raw: str, *, label: str, max_len: int) -> str:
    """Strip whitespace, reject empty, reject control chars, cap length.

    Shared by ``sanitize_task_ref`` (200) and ``sanitize_reason`` (500) —
    reasons can be more prose-y than task refs, hence the wider cap.
    Raises ValueError on invalid input.
    """
    if not isinstance(raw, str):
        raise ValueError(f"{label} must be a string")
    value = raw.strip()
    if not value:
        raise ValueError(f"{label} must not be empty")
    if len(value) > max_len:
        raise ValueError(
            f"{label} too long ({len(value)} > {max_len} chars)"
        )
    for ch in value:
        # Printable ASCII + non-ASCII allowed; control chars rejected
        # (newline, tab, NUL, etc. — a stored newline is what let a title
        # forge a row in the CLI listing before the display-side fix).
        if ord(ch) < 0x20 or ord(ch) == 0x7F:
            raise ValueError(
                f"{label} contains control character (0x{ord(ch):02X}); "
                "use a single-line printable token"
            )
    return value


def sanitize_task_ref(raw: str) -> str:
    return _sanitize_single_line(
        raw, label="--task-ref", max_len=_TASK_REF_MAX_LEN,
    )


def sanitize_reason(raw: str) -> str:
    return _sanitize_single_line(
        raw, label="--reason", max_len=_REASON_MAX_LEN,
    )


def _require_store(project_root: Path) -> None:
    """Both stores absent → the inbox was never initialised.

    Distinct from an unknown id, which gets its own exit code at the CLI layer.
    F29: the gitignored outbox counts (mirroring triage.mark_status's union
    model) — an idle-main producer appends there before the tracked store
    exists, and such an item must still be decidable.
    """
    tracked_path = _triage_path(project_root)
    outbox_path = _outbox_path(project_root)
    if not tracked_path.exists() and not outbox_path.exists():
        raise FileNotFoundError(
            f"triage store not initialised at {tracked_path} "
            f"(nor outbox at {outbox_path})"
        )


def _find_item(project_root: Path, item_id: str) -> dict | None:
    for it in read_all_items(project_root):
        if it.get("id") == item_id:
            return it
    return None


def promote(
    project_root: Path,
    *,
    item_id: str,
    task_ref: str,
    reason: str | None = None,
    by: str = "manualPromote",
) -> dict:
    """Promote a triage item to a backlog task.

    Returns ``{"id", "previousStatus", "newStatus", "promotedTaskId"}``.
    Raises:
        FileNotFoundError: triage store missing.
        KeyError: item_id not found.
        ValueError: invalid state (only `triage` is promotable) or
            invalid task_ref.
    """
    task_ref_clean = sanitize_task_ref(task_ref)
    # The optional reason is sanitized too. The "manualPromote" default is a
    # known-clean literal and bypasses it; empty / whitespace-only reasons
    # fall back to that default so an operator's "   " doesn't store as "   ".
    if reason is not None and reason.strip():
        reason_clean = sanitize_reason(reason)
    else:
        reason_clean = "manualPromote"

    _require_store(project_root)

    item = _find_item(project_root, item_id)
    if item is None:
        raise KeyError(item_id)
    current = item.get("status")
    if current != "triage":
        raise _not_triage_error(item_id, current, "promoted")

    try:
        mark_status(
            project_root,
            item_id,
            new_status="promoted",
            by=by,
            reason=reason_clean,
            promoted_task_id=task_ref_clean,
            expected_status="triage",
        )
    except StatusPreconditionError as exc:
        raise _not_triage_error(item_id, exc.actual, "promoted") from exc

    return {
        "id": item_id,
        "previousStatus": "triage",
        "newStatus": "promoted",
        "promotedTaskId": task_ref_clean,
    }


def _decide_from_triage(
    project_root: Path,
    *,
    item_id: str,
    new_status: str,
    reason: str,
    by: str,
) -> dict:
    """Move a still-open item into a decided state — the body ``dismiss`` and
    ``defer`` share so their guards cannot drift apart.

    Deliberately NOT used by ``promote``: that one also writes
    ``promotedTaskId``, and widening this helper with a parameter one caller
    never sets is how a shared helper starts lying about what it does.
    """
    reason_clean = sanitize_reason(reason)
    _require_store(project_root)

    item = _find_item(project_root, item_id)
    if item is None:
        raise KeyError(item_id)
    current = item.get("status")
    if current != "triage":
        raise _not_triage_error(item_id, current, new_status)

    try:
        mark_status(project_root, item_id, new_status=new_status, by=by,
                    reason=reason_clean, expected_status="triage")
    except StatusPreconditionError as exc:
        raise _not_triage_error(item_id, exc.actual, new_status) from exc

    return {
        "id": item_id,
        "previousStatus": "triage",
        "newStatus": new_status,
        "reason": reason_clean,
    }


def dismiss(
    project_root: Path,
    *,
    item_id: str,
    reason: str,
    by: str = "manualDismiss",
) -> dict:
    """Dismiss a triage item (false-positive / won't-fix).

    Returns ``{"id", "previousStatus", "newStatus", "reason"}``.

    Raises:
        FileNotFoundError: triage store missing.
        KeyError: item_id not found.
        ValueError: invalid state (only `triage` is dismissable) or
            invalid ``reason``.
    """
    return _decide_from_triage(
        project_root, item_id=item_id, new_status="dismissed",
        reason=reason, by=by,
    )


def defer(
    project_root: Path,
    *,
    item_id: str,
    reason: str,
    by: str = "manualDefer",
) -> dict:
    """Defer a triage item — decided, but deliberately not now.

    The third decision beside promote and dismiss (FR-01.14), stored as
    `snoozed`. Same contract as ``dismiss``: reason required, only `triage`
    items are deferrable, same three exceptions. No subcommand reverses it;
    ``mark_status(..., new_status="triage")`` is the supported correction until
    `trg-51f8e2a1` lands.
    """
    return _decide_from_triage(
        project_root, item_id=item_id, new_status="snoozed",
        reason=reason, by=by,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Promote a triage item to a backlog task (manual CLI; "
                    "non-webui repos or operator preference).",
    )
    p.add_argument("--project-root", default=".", help="Project root (default: .)")
    p.add_argument("--id", dest="item_id", required=True,
                   help="Triage item id (e.g. trg-abc12345)")
    p.add_argument("--task-ref", dest="task_ref", required=True,
                   help='External task reference, e.g. "EXT:linear-ENG-123"')
    p.add_argument("--reason", default=None,
                   help="Optional rationale recorded with the promotion event "
                        "(default: manualPromote)")
    p.add_argument("--by", default="manualPromote",
                   help='Identifier for the actor (default: "manualPromote")')
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = Path(args.project_root)
    try:
        result = promote(
            project_root,
            item_id=args.item_id,
            task_ref=args.task_ref,
            reason=args.reason,
            by=args.by,
        )
    except ValueError as exc:
        # Invalid state OR invalid task_ref → exit 2
        sys.stderr.write(f"error: {exc}\n")
        return 2
    except KeyError as exc:
        sys.stderr.write(f"error: triage item not found: {exc}\n")
        return 3
    except FileNotFoundError as exc:
        sys.stderr.write(
            f"error: triage store not initialised: {exc}\n"
            "Run /shipwright-adopt or scaffold_triage_inbox.py first.\n"
        )
        return 4

    sys.stderr.write(
        f"promoted {result['id']} → {result['promotedTaskId']}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
