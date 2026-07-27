#!/usr/bin/env python3
"""The three triage decisions as library helpers, plus a promote-only CLI.

``promote`` / ``dismiss`` / ``defer`` wrap `triage.mark_status` with the
validation both operator surfaces share — ``triage_cli.py`` and the Command
Center's Triage tab dispatch through these, so an audit trail cannot depend on
which surface made the call. All three require the item to exist and to still
be undecided (`triage`); moving out of a decided state is deliberately not
offered here (use ``mark_status``). Operator strings are sanitized: no control
characters, `--task-ref` ≤200 chars, `--reason` ≤500.

Usage:
    uv run shared/scripts/tools/triage_promote.py \\
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
    _outbox_path,
    _triage_path,
    mark_status,
    read_all_items,
)

_TASK_REF_MAX_LEN = 200
_REASON_MAX_LEN = 500

# Adjective per decided state, so the rejection message reads naturally for
# whichever transition was refused.
_DECIDABLE = {"dismissed": "dismissable", "snoozed": "deferrable"}


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
        # Allow printable ASCII + non-ASCII; reject control chars
        # (newline, tab, NUL, etc.).
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

    Distinct from an unknown id, which gets its own exit code at the CLI
    layer. F29: the gitignored outbox counts, mirroring triage.mark_status's
    union model — an idle-main background producer can append there before the
    tracked store exists, and such an item must still be decidable.
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
        raise ValueError(
            f"item {item_id} has status={current!r}; only `triage` is "
            f"promotable from this CLI (use mark_status for other "
            f"transitions)"
        )

    mark_status(
        project_root,
        item_id,
        new_status="promoted",
        by=by,
        reason=reason_clean,
        promoted_task_id=task_ref_clean,
    )

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
        raise ValueError(
            f"item {item_id} has status={current!r}; only `triage` is "
            f"{_DECIDABLE[new_status]} from this CLI (use mark_status for "
            f"other transitions)"
        )

    mark_status(project_root, item_id, new_status=new_status, by=by,
                reason=reason_clean)

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
    items are deferrable, same three exceptions. Neither surface can un-defer
    — the Command Center's status-flip route also accepts `triage` alone.
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
