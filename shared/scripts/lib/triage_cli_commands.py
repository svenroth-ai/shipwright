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
    SEVERITY_RANK,
    STATUSES,
    _append_ids_at,
    _outbox_path,
    _triage_path,
    amend_triage_item,
    read_all_items,
)
from lib.triage_contract import build_listing  # noqa: E402
from lib.triage_delivery import format_pending_delivery_notice  # noqa: E402
from lib.triage_integrity import store_facts  # noqa: E402
from lib.triage_render import format_item, render_deferred_section  # noqa: E402
from tools.triage_promote import defer, dismiss, promote, unpark  # noqa: E402

_BY_LABEL = "cli"


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
    # above, so it lands in the open list without anything here noticing —
    # which is the whole point of deriving expiry in the reader.
    deferred = [it for it in resolved if it.get("status") == "snoozed"]
    corruption, undelivered = store_facts(_triage_path(project_root), _outbox_path(project_root), applied_statuses=STATUSES)
    if getattr(args, "json", False):
        return _emit_json(project_root, items, deferred, undelivered, corruption)
    if not items:
        sys.stdout.write("No open triage items.\n\n")
    for item in items:
        sys.stdout.write(format_item(item) + "\n\n")
    # The third decision is not a disappearance: a deferred entry is still
    # here, still undone, and told apart from an open one by its row's own
    # marker, not only by the section header. Capped like the rendered
    # document's open list, because a parked section that prints without limit
    # crowds out the work that is actually open.
    for block in render_deferred_section(deferred, SEVERITY_RANK):
        sys.stdout.write(block + "\n\n")
    # A dismissed-but-buffered item is in NEITHER section above (it resolved to a
    # terminal status), so this summary is the only place it can appear (finding 28).
    if undelivered:
        sys.stdout.write(format_pending_delivery_notice(undelivered) + "\n\n")
    return 0


def _emit_json(project_root: Path, items: list[dict], deferred: list[dict], undelivered: set, corruption: list) -> int:
    """Serialise the machine contract. Its shape lives in `lib.triage_contract`."""
    payload = build_listing(
        items, deferred,
        tracked_ids=_append_ids_at(_triage_path(project_root)),
        outbox_ids=_append_ids_at(_outbox_path(project_root)),
        severity_rank=SEVERITY_RANK,
        undelivered_status_ids=undelivered,
        corruption=corruption,
    )
    sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root)
    try:
        result = promote(
            project_root,
            item_id=args.item_id,
            task_ref=args.task_ref,
            reason=args.reason,
            by=_BY_LABEL,
        )
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    except KeyError as exc:
        sys.stderr.write(f"error: triage item not found: {exc}\n")
        return 2
    except FileNotFoundError as exc:
        sys.stderr.write(f"error: triage store not initialised: {exc}\n")
        return 2

    sys.stderr.write(
        f"promoted {result['id']} → {result['promotedTaskId']}\n"
    )
    return 0


def _status_flip(
    decide: Callable[..., dict], args: argparse.Namespace, verb: str,
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
            **extra,
        )
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    except KeyError as exc:
        sys.stderr.write(f"error: triage item not found: {exc}\n")
        return 2
    except FileNotFoundError as exc:
        sys.stderr.write(f"error: triage store not initialised: {exc}\n")
        return 2

    sys.stderr.write(f"{verb} {result['id']} (reason: {result['reason']})\n")
    return 0


def cmd_dismiss(args: argparse.Namespace) -> int:
    return _status_flip(dismiss, args, "dismissed")


def cmd_defer(args: argparse.Namespace) -> int:
    return _status_flip(defer, args, "deferred", revisit_at=args.revisit)


def cmd_unpark(args: argparse.Namespace) -> int:
    return _status_flip(unpark, args, "un-parked")


def cmd_amend(args: argparse.Namespace) -> int:
    """AC9: the CLI is the human-only amend writer this iterate ships; `by`
    is always the fixed `_BY_LABEL` — no `--by` flag, per the operator's own
    scoping decision (human, via command line)."""
    project_root = Path(args.project_root)
    try:
        to_outbox = amend_triage_item(
            project_root, args.item_id, by=_BY_LABEL,
            title=args.title, detail=args.detail,
            severity=args.severity, kind=args.kind,
        )
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    except KeyError as exc:
        sys.stderr.write(f"error: triage item not found: {exc}\n")
        return 2
    except FileNotFoundError as exc:
        sys.stderr.write(f"error: triage store not initialised: {exc}\n")
        return 2

    changed = [f for f, v in (
        ("title", args.title), ("detail", args.detail),
        ("severity", args.severity), ("kind", args.kind),
    ) if v is not None]
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
