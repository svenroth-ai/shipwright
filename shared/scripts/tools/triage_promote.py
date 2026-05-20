#!/usr/bin/env python3
"""Manual promote CLI for the triage inbox.

AC-7 of iterate-2026-05-11-triage-inbox-1a. For non-webui repos (or
operators who prefer the CLI), wraps `triage.mark_status` with input
validation:

- Item must exist (resolved by `read_all_items`).
- Item's current status must be `triage`. Promoting from
  `dismissed`/`snoozed` is rejected with exit code 2 — those
  transitions require explicit operator intervention out of scope
  for Iterate 1a (LOW-12 from external review).
- `--task-ref` is sanitized: no newlines, tabs, or ASCII control
  characters; max 200 chars (MED-12 from external review).

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
    TRIAGE_FILE,
    mark_status,
    read_all_items,
)

_TASK_REF_MAX_LEN = 200
_REASON_MAX_LEN = 500


def _sanitize_single_line(raw: str, *, label: str, max_len: int) -> str:
    """Shared sanitizer: strip whitespace, reject control chars, cap length.

    Used by both ``sanitize_task_ref`` (label='--task-ref', max=200) and
    ``sanitize_reason`` (label='--reason', max=500). Reasons can be more
    prose-y than task refs, hence the wider cap.

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
    # Symmetric with dismiss(): sanitize the optional reason too — code
    # review MED #3 of iterate-2026-05-20-triage-launch-surface. The
    # "manualPromote" default is treated as a known-clean literal and
    # bypasses sanitization. Empty / whitespace-only reasons fall back to
    # the default so an operator-supplied "   " doesn't store as "   ".
    if reason is not None and reason.strip():
        reason_clean = sanitize_reason(reason)
    else:
        reason_clean = "manualPromote"

    # Distinguish "store missing" from "id missing" — different exit codes
    # at the CLI layer.
    triage_path = Path(project_root) / ".shipwright" / TRIAGE_FILE
    if not triage_path.exists():
        raise FileNotFoundError(
            f"triage store not initialised at {triage_path}"
        )

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


def dismiss(
    project_root: Path,
    *,
    item_id: str,
    reason: str,
    by: str = "manualDismiss",
) -> dict:
    """Dismiss a triage item.

    Returns ``{"id", "previousStatus", "newStatus", "reason"}``.
    Symmetric with ``promote`` — only `triage` items are dismissable from
    this CLI (use ``mark_status`` for other transitions). Added in
    iterate-2026-05-20-triage-launch-surface so the new ``triage_cli.py``
    can dispatch ``dismiss`` through the same parity-tested helper as
    ``promote``.

    Raises:
        FileNotFoundError: triage store missing.
        KeyError: item_id not found.
        ValueError: invalid state (only `triage` is dismissable) or
            invalid ``reason``.
    """
    reason_clean = sanitize_reason(reason)

    triage_path = Path(project_root) / ".shipwright" / TRIAGE_FILE
    if not triage_path.exists():
        raise FileNotFoundError(
            f"triage store not initialised at {triage_path}"
        )

    item = _find_item(project_root, item_id)
    if item is None:
        raise KeyError(item_id)
    current = item.get("status")
    if current != "triage":
        raise ValueError(
            f"item {item_id} has status={current!r}; only `triage` is "
            f"dismissable from this CLI (use mark_status for other "
            f"transitions)"
        )

    mark_status(
        project_root,
        item_id,
        new_status="dismissed",
        by=by,
        reason=reason_clean,
    )

    return {
        "id": item_id,
        "previousStatus": "triage",
        "newStatus": "dismissed",
        "reason": reason_clean,
    }


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
