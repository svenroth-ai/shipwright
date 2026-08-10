#!/usr/bin/env python3
"""The four triage decisions as library helpers, plus a promote-only CLI.

``promote`` / ``dismiss`` / ``defer`` / ``unpark`` wrap `triage.mark_status`
with this repo's CLI validation. Each names the EFFECTIVE statuses it may
start from — promote and dismiss from open only, defer from open or already
parked (re-parking replaces the date), unpark from parked only — and the
store re-checks that same set under its lock. Effective, not stored: a park
whose revisit date has passed reads open and behaves like any open entry.
Operator strings are sanitized — no control chars, task-ref ≤200, reason ≤500.

**Reference semantics the Command Center's Triage tab mirrors — NOT a code
path it shares**, so tightening validation here does not cover both surfaces
(verified divergence: its snooze route permits a park with neither a reason
nor a revisit date — `shipwright-webui`
`server/src/routes/triage.ts::parseDismissSnoozeBody`, 2026-07-27; such a
park resolves parked-but-never-due rather than being silently re-opened,
and WebUI-store `trg-f2214310` carries the consumer work). Canonical statement:
`shared/glossary.md` → *Defer (Park)*.

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
from shared_lib_loader import load_shared_lib  # noqa: E402

# ADR-045: NOT `from lib.triage_defer import …`. This module is imported by
# test sessions that may already have a different `lib` package cached, and an
# eager package import would bind to that one — CI red while a local F0 stays
# green (iterate-2026-07-27-test-phase-record-honesty). `triage_defer` has no
# intra-package imports, which is the loader's documented precondition.
_defer = load_shared_lib("triage_defer")
DEFERRABLE_STATUSES = _defer.DEFERRABLE_STATUSES
UNPARKABLE_STATUSES = _defer.UNPARKABLE_STATUSES
TransitionPreconditionError = load_shared_lib("triage_transition").TransitionPreconditionError
_TASK_REF_MAX_LEN = 200
_REASON_MAX_LEN = 500
_DECIDABLE = {
    "dismissed": "dismissable",
    "snoozed": "deferrable",
    "promoted": "promotable",
    "triage": "un-parkable",
}


def _wrong_status_error(
    item_id: str, current: object, new_status: str, allowed: tuple[str, ...],
) -> TransitionPreconditionError:
    """The ONE wording for "this item is not in a state you can do that from".

    Both ways it is found raise from here: the pre-check below reads the store
    unlocked, so the item can be decided in the window between that read and the
    write, and the store then refuses under its own lock. One constructor keeps
    the CLI's message and exit code identical whichever fires (external plan
    review of iterate-2026-07-27, finding #9).

    ``allowed`` is named rather than assumed `triage`-only since
    iterate-2026-08-01-triage-defer-lifecycle: `defer` also accepts an already
    parked entry (re-park with a corrected date) and `unpark` accepts only a
    parked one. The status compared against is always the EFFECTIVE one, so an
    entry whose park expired reads `triage` here and is reported as open.
    """
    allowed_phrase = " or ".join(f"`{s}`" for s in allowed)
    return TransitionPreconditionError(
        f"item {item_id} has status={current!r}; only {allowed_phrase} is "
        f"{_DECIDABLE.get(new_status, 'decidable')} from this CLI "
        f"(use mark_status for other transitions)"
    )


def _not_triage_error(item_id: str, current: object, new_status: str) -> ValueError:
    """Back-compat shim for the `triage`-only callers (promote, dismiss)."""
    return _wrong_status_error(item_id, current, new_status, ("triage",))


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
    include_item: bool = False,
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
        mark_result = mark_status(
            project_root,
            item_id,
            new_status="promoted",
            by=by,
            reason=reason_clean,
            promoted_task_id=task_ref_clean,
            expected_status="triage",
            return_item=include_item,
        )
    except StatusPreconditionError as exc:
        raise _not_triage_error(item_id, exc.actual, "promoted") from exc

    result = {
        "id": item_id,
        "previousStatus": "triage",
        "newStatus": "promoted",
        "promotedTaskId": task_ref_clean,
    }
    if include_item:
        result["item"] = mark_result[1]
    return result


def _transition(
    project_root: Path,
    *,
    item_id: str,
    new_status: str,
    allowed: tuple[str, ...],
    reason: str,
    by: str,
    revisit_at: str | None = None,
    include_item: bool = False,
) -> dict:
    """The one body ``dismiss``, ``defer`` and ``unpark`` share.

    ``allowed`` is the set of EFFECTIVE statuses the transition may start from,
    and it is checked twice on purpose: once against this unlocked read (so the
    common case gets the good message) and once by the store, under its lock,
    via ``expected_status``. Both refusals raise from
    :func:`_wrong_status_error`, so the message and the exit code cannot drift
    apart between the two paths.

    ``allowed`` became a parameter in iterate-2026-08-01-triage-defer-lifecycle:
    `dismiss` starts only from open, `defer` also from already-parked (a re-park
    replaces the date), and `unpark` only from parked.

    """
    reason_clean = sanitize_reason(reason)
    _require_store(project_root)

    item = _find_item(project_root, item_id)
    if item is None:
        raise KeyError(item_id)
    current = item.get("status")
    if current not in allowed:
        raise _wrong_status_error(item_id, current, new_status, allowed)

    try:
        mark_result = mark_status(
            project_root, item_id, new_status=new_status, by=by,
            reason=reason_clean, expected_status=allowed,
            revisit_at=revisit_at,
            return_item=include_item,
        )
    except StatusPreconditionError as exc:
        raise _wrong_status_error(
            item_id, exc.actual, new_status, allowed,
        ) from exc

    previous = mark_result[0] if include_item else mark_result
    result = {
        "id": item_id,
        "previousStatus": previous,
        "newStatus": new_status,
        "reason": reason_clean,
    }
    if revisit_at is not None:
        result["revisitAt"] = revisit_at
    if include_item:
        result["item"] = mark_result[1]
    return result


def dismiss(
    project_root: Path,
    *,
    item_id: str,
    reason: str,
    by: str = "manualDismiss",
    include_item: bool = False,
) -> dict:
    """Dismiss a triage item (false-positive / won't-fix).

    Returns ``{"id", "previousStatus", "newStatus", "reason"}``.

    Raises:
        FileNotFoundError: triage store missing.
        KeyError: item_id not found.
        ValueError: invalid state (only `triage` is dismissable) or
            invalid ``reason``.
    """
    return _transition(
        project_root, item_id=item_id, new_status="dismissed",
        allowed=("triage",), reason=reason, by=by, include_item=include_item,
    )


def defer(
    project_root: Path,
    *,
    item_id: str,
    reason: str,
    revisit_at: str,
    by: str = "manualDefer",
    include_item: bool = False,
) -> dict:
    """Park a triage item — decided, but deliberately not now, until a date.

    The third decision beside promote and dismiss (FR-01.14), stored as
    `snoozed`. ``revisit_at`` (``YYYY-MM-DD``) is **required here** and names
    the day the entry returns to the open list by itself; a park with no date
    is what let a deferral become permanent through inattention, and what let a
    machine-raised finding re-appear as a duplicate on the very next import.
    The store keeps the parameter optional so the Command Center's date-less
    park and every pre-existing one still resolve (as parked-but-not-due) — the
    requirement belongs to the decision surface, not to the log.

    Accepts an entry that is effectively open **or** already parked: re-parking
    replaces the date, so a mistyped one is correctable without un-parking
    first. `dismissed` and `promoted` are refused.

    Returns ``{"id", "previousStatus", "newStatus", "reason", "revisitAt"}``.
    """
    if revisit_at is None:
        raise ValueError("revisit_at is required when deferring an item")
    return _transition(
        project_root, item_id=item_id, new_status="snoozed",
        allowed=DEFERRABLE_STATUSES, reason=reason, by=by,
        revisit_at=revisit_at, include_item=include_item,
    )


def unpark(
    project_root: Path,
    *,
    item_id: str,
    reason: str,
    by: str = "manualUnpark",
    include_item: bool = False,
) -> dict:
    """Reverse a park — the entry returns to the open list, date cleared.

    The store always permitted this transition; only the command was missing,
    so a mistaken park pushed an operator toward hand-editing the log — the
    exact untrusted-input path the renderer exists to defend against
    (`trg-51f8e2a1` part 4, operator decision #4 of 2026-07-27).

    Judged on the **effective** status: an entry whose revisit date has already
    passed reads `triage` and is refused as *already open*, rather than being
    handed a second event that changes nothing.

    Returns ``{"id", "previousStatus", "newStatus", "reason"}``.
    """
    return _transition(
        project_root, item_id=item_id, new_status="triage",
        allowed=UNPARKABLE_STATUSES, reason=reason, by=by, include_item=include_item,
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
