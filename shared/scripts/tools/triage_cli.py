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
                                        `contractVersion`, `open`, `deferred`,
                                        `corruption`, and both undelivered blocks;
                                        rows carry pendingDelivery + independent
                                        pendingStatusDelivery/pendingAmendDelivery.
                                        `lib.triage_contract`
  promote <id> --task-ref EXT:<ref>     promote → backlog task
  dismiss <id> --reason <reason>        dismiss (false-positive / won't-fix)
  defer   <id> --reason <r> --revisit D defer until day D (YYYY-MM-DD), after
                                        which it returns to the open list by
                                        itself; until then the same finding is
                                        not recorded a second time
  unpark  <id> --reason <reason>        reverse a defer, back onto the open list
  amend   <id> [--title T] [--detail D] [--severity S] [--kind K]
                                        correct title/detail/severity/kind in
                                        place (id stable, prior lines never
                                        mutated) — at least one required

Fix-now flow: operators open ``.shipwright/agent_docs/triage_inbox.md`` (or run
``triage_cli.py list``), copy the ``launchPayload`` fence into a new Claude
session, the matching slash command (``/shipwright-security``,
``/shipwright-iterate --type bug``, ...) auto-fires there, and the lifecycle hook
flips this item once the resulting run completes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from triage import KINDS, SEVERITIES  # noqa: E402
from lib.triage_cli_commands import (  # noqa: E402
    cmd_amend,
    cmd_defer,
    cmd_dismiss,
    cmd_list,
    cmd_promote,
    cmd_unpark,
)

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
             "(never capped). Each item carries pendingDelivery and independent "
             "pendingStatusDelivery/pendingAmendDelivery booleans; the envelope "
             "also reports capped undelivered decisions and amends. Shape and "
             "version: lib/triage_contract.py",
    )
    p_list.set_defaults(func=cmd_list)

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
    p_promote.set_defaults(func=cmd_promote)

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
    p_dismiss.set_defaults(func=cmd_dismiss)

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
    p_defer.set_defaults(func=cmd_defer)

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
    p_unpark.set_defaults(func=cmd_unpark)

    p_amend = sub.add_parser(
        "amend", help="correct a triage item's title/detail/severity/kind in place",
    )
    p_amend.add_argument("item_id", help="triage item id (e.g. trg-abc12345)")
    p_amend.add_argument("--title", default=None, help="corrected title")
    p_amend.add_argument("--detail", default=None, help="corrected detail")
    p_amend.add_argument("--severity", default=None, choices=SEVERITIES, help="corrected severity")
    p_amend.add_argument("--kind", default=None, choices=KINDS, help="corrected category")
    p_amend.set_defaults(func=cmd_amend)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
