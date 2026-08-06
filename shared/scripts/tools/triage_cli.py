#!/usr/bin/env python3
"""Triage Inbox CLI — operate on `.shipwright/triage.jsonl` from the shell.

CLI = first-class operation interface. Every decision the requirement promises
can be made here — ``triage_promote.promote`` / ``.dismiss`` / ``.defer``, and
since iterate-2026-08-01-triage-defer-lifecycle ``.unpark``, which reverses the
third one. The shipwright-webui Triage tab reaches the same store through its
OWN implementation and mirrors these semantics rather than sharing the code —
see ``triage_promote``'s header for the known divergence.

Subcommands (positional ``<id>`` for every decision):

  list [--json]                         open items, then any deferred ones in their
                                        own capped section. ``--json`` is the machine
                                        contract for the WebUI: an envelope with
                                        `contractVersion`, `open`, `deferred` and
                                        `corruption`; rows carry pendingDelivery +
                                        pendingStatusDelivery. `lib.triage_contract`
  promote <id> --task-ref EXT:<ref>     promote → backlog task
  dismiss <id> --reason <reason>        dismiss (false-positive / won't-fix)
  defer   <id> --reason <r> --revisit D defer until day D (YYYY-MM-DD), after
                                        which it returns to the open list by
                                        itself; until then the same finding is
                                        not recorded a second time
  unpark  <id> --reason <reason>        reverse a defer, back onto the open list

Fix-now flow: operators open ``.shipwright/agent_docs/triage_inbox.md`` (or run
``triage_cli.py list``), copy the ``launchPayload`` fence into a new Claude
session, the matching slash command (``/shipwright-security``,
``/shipwright-iterate --type bug``, ...) auto-fires there, and the lifecycle hook
flips this item once the resulting run completes.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from triage import (  # noqa: E402
    SEVERITY_RANK,
    STATUSES,
    _append_ids_at,
    _outbox_path,
    _triage_path,
    read_all_items,
)
from lib.triage_contract import build_listing  # noqa: E402
from lib.triage_delivery import format_pending_delivery_notice  # noqa: E402
from lib.triage_integrity import store_facts  # noqa: E402
from lib.triage_render import format_item, render_deferred_section  # noqa: E402
from tools.triage_promote import defer, dismiss, promote, unpark  # noqa: E402

_BY_LABEL = "cli"


def _ensure_utf8_stdout() -> None:
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


def _cmd_list(args: argparse.Namespace) -> int:
    _ensure_utf8_stdout()
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


# ---------------------------------------------------------------------------
# Mutating subcommands
# ---------------------------------------------------------------------------

def _cmd_promote(args: argparse.Namespace) -> int:
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


def _cmd_dismiss(args: argparse.Namespace) -> int:
    return _status_flip(dismiss, args, "dismissed")


def _cmd_defer(args: argparse.Namespace) -> int:
    return _status_flip(defer, args, "deferred", revisit_at=args.revisit)


def _cmd_unpark(args: argparse.Namespace) -> int:
    return _status_flip(unpark, args, "un-parked")


# ---------------------------------------------------------------------------
# Argparse wiring
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="triage_cli",
        description=(
            "Operate on the Triage Inbox from the shell. "
            "First-class CLI surface (parallel to the WebUI Triage tab)."
        ),
    )
    parser.add_argument(
        "--project-root", default=".", help="Project root (default: .)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser(
        "list", help="list open triage items, then any deferred ones",
    )
    p_list.add_argument(
        "--json", action="store_true",
        help="emit the machine contract for the WebUI: an envelope with "
             "contractVersion, plus complete `open` and `deferred` arrays "
             "(never capped). Each item gains a pendingDelivery bool for "
             "outbox-only items, and a deferred one carries revisitAt + "
             "revisitDue. Shape and version: lib/triage_contract.py",
    )
    p_list.set_defaults(func=_cmd_list)

    p_promote = sub.add_parser(
        "promote", help="promote a triage item to a backlog task",
    )
    p_promote.add_argument(
        "item_id", help="triage item id (e.g. trg-abc12345)",
    )
    p_promote.add_argument(
        "--task-ref", dest="task_ref", required=True,
        help='external task reference, e.g. "EXT:linear-ENG-123"',
    )
    p_promote.add_argument(
        "--reason", default=None,
        help="optional rationale (default: manualPromote)",
    )
    p_promote.set_defaults(func=_cmd_promote)

    p_dismiss = sub.add_parser(
        "dismiss", help="dismiss a triage item (false-positive / won't-fix)",
    )
    p_dismiss.add_argument(
        "item_id", help="triage item id (e.g. trg-abc12345)",
    )
    p_dismiss.add_argument(
        "--reason", required=True,
        help="rationale for dismissal (required)",
    )
    p_dismiss.set_defaults(func=_cmd_dismiss)

    p_defer = sub.add_parser(
        "defer", help="defer a triage item (decided, but deliberately not now)",
    )
    p_defer.add_argument(
        "item_id", help="triage item id (e.g. trg-abc12345)",
    )
    p_defer.add_argument(
        "--reason", required=True,
        help="rationale for deferring (required)",
    )
    p_defer.add_argument(
        "--revisit", required=True, metavar="YYYY-MM-DD",
        help="the day this comes back to the open list by itself (required). "
             "It returns from 00:00 UTC on that date, and until then the same "
             "finding will not be recorded a second time. Re-run defer with a "
             "different date to change it.",
    )
    p_defer.set_defaults(func=_cmd_defer)

    p_unpark = sub.add_parser(
        "unpark", help="reverse a defer — put a parked item back on the open list",
    )
    p_unpark.add_argument(
        "item_id", help="triage item id (e.g. trg-abc12345)",
    )
    p_unpark.add_argument(
        "--reason", required=True,
        help="rationale for un-parking (required)",
    )
    p_unpark.set_defaults(func=_cmd_unpark)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
