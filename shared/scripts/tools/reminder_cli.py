#!/usr/bin/env python3
"""Reminder CLI — the ONLY writer of `.shipwright/reminders.jsonl`.

  add <title> --due YYYY-MM-DD --why W [--decided D] [--open O] [--command C]
      [--link LABEL=KIND=REF ...]           KIND: campaign | triage | file | url
  list [--all] [--json]                     open/snoozed reminders (--all adds done)
  show <id> [--json]
  done <id>
  snooze <id> --until YYYY-MM-DD            must be after today (UTC); never on a
                                            reminder that is already done
  due [--on YYYY-MM-DD] [--json]            reminders AND expired triage parks due that
                                            UTC day (read-only; see lib/reminder_due.py)

`--json` is the machine contract and is never capped: `{"contractVersion": 1,
"reminders": [...]}` with every reminder, done ones included. The store lives at
the MAIN repo root, so a reminder written from a worktree lands in one place.
Anything that must write a reminder (the WebUI included) calls this CLI; nothing
appends the file directly. Text is refused when it looks like it holds a secret.

Exit codes: 0 ok, 2 refused (message on stderr; argparse usage errors also exit 2), 3 no such
reminder, 4 store busy or
unreadable (lock timeout / OS error). Only `list --json` is wrapped in the versioned
envelope; it also carries `corruptLines` so a damaged store is never read as absence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.file_lock import LockTimeout  # noqa: E402
from lib.reminder_due import build_due  # noqa: E402
from lib.reminder_store import (  # noqa: E402
    LINK_KINDS, ReminderError, ReminderNotFound, add_reminder, parse_day, read_folded,
    set_status, store_path, not_found_message,
)

CONTRACT_VERSION = 1


def _parse_link(raw: str) -> dict:
    parts = raw.split("=", 2)
    if len(parts) != 3:
        raise ReminderError(
            f"--link must look like LABEL=KIND=REF (KIND: {', '.join(LINK_KINDS)})."
        )
    return {"label": parts[0], "kind": parts[1], "ref": parts[2]}


def _sorted(reminders: dict) -> list[dict]:
    return sorted(reminders.values(), key=lambda r: (r["due"], r["id"]))


def _line(r: dict) -> str:
    due = r["snoozed_until"] if r["status"] == "snoozed" else r["due"]
    return f"{r['id']}  {r['status']:<7}  {due}  {r['title']}"


def _print_one(r: dict) -> None:
    print(_line(r))
    for key in ("why", "decided", "open", "command"):
        if r.get(key):
            print(f"  {key}: {r[key]}")
    for link in r.get("links", []):
        print(f"  link: {link['label']} ({link['kind']}) {link['ref']}")


def cmd_add(args) -> int:
    rec = add_reminder(
        args.project_root, title=args.title, due=args.due, why=args.why,
        decided=args.decided, open_=args.open, command=args.command,
        links=[_parse_link(x) for x in args.link],
    )
    print(json.dumps(rec, ensure_ascii=False) if args.json else f"added {_line(rec)}")
    return 0


def cmd_list(args) -> int:
    folded = read_folded(store_path(args.project_root))
    rows = _sorted(folded.reminders)
    if args.json:
        print(json.dumps({"contractVersion": CONTRACT_VERSION, "reminders": rows,
                          "corruptLines": folded.damaged},
                         ensure_ascii=False))
    else:
        shown = [r for r in rows if args.all or r["status"] != "done"]
        for r in shown:
            print(_line(r))
        if not shown:
            print("no reminders")
    if folded.damaged:
        print(f"warning: {folded.damaged} unreadable or rejected line(s) in the reminder store",
              file=sys.stderr)
    return 0


def cmd_show(args) -> int:
    folded = read_folded(store_path(args.project_root))
    rec = folded.reminders.get(args.reminder_id)
    if rec is None:
        raise ReminderNotFound(not_found_message(args.reminder_id, folded))
    if args.json:
        print(json.dumps(rec, ensure_ascii=False))
    else:
        _print_one(rec)
    return 0


def cmd_done(args) -> int:
    print(f"done {_line(set_status(args.project_root, args.reminder_id, 'done'))}")
    return 0


def cmd_snooze(args) -> int:
    rec = set_status(args.project_root, args.reminder_id, "snoozed", until=args.until)
    print(f"snoozed {_line(rec)}")
    return 0


def cmd_due(args) -> int:
    answer = build_due(args.project_root, parse_day(args.on, "--on") if args.on else None)
    if args.json:
        print(json.dumps(answer, ensure_ascii=False))
    else:
        for it in answer["items"]:
            print(f"{it['kind']:<8}  {it['id']}  {it['due']}  {it['title']}")
        if not answer["items"]:
            print(f"nothing due on {answer['on']}")
        print(f"source_root: {answer['sourceRoot']}")
    if answer["triageError"]:
        print(f"warning: the triage side could not be read: {answer['triageError']}",
              file=sys.stderr)
    if answer["reminderCorruptLines"]:
        print(f"warning: {answer['reminderCorruptLines']} unreadable or rejected line(s) in the "
              "reminder store", file=sys.stderr)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reminder_cli", description=__doc__.split("\n")[0])
    parser.add_argument("--project-root", default=".", help="Project root (default: .)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="add a reminder")
    p.add_argument("title")
    p.add_argument("--due", required=True, metavar="YYYY-MM-DD")
    p.add_argument("--why", required=True, help="why this matters")
    p.add_argument("--decided", default=None, help="what was already decided")
    p.add_argument("--open", default=None, help="what is still open")
    p.add_argument("--command", default=None, help="the command to run when it is due")
    p.add_argument("--link", action="append", default=[], metavar="LABEL=KIND=REF")
    p.add_argument("--json", action="store_true", help="print the added reminder as JSON")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="list reminders")
    p.add_argument("--all", action="store_true", help="include done reminders (text output)")
    p.add_argument("--json", action="store_true", help="machine contract, never capped")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="show one reminder")
    p.add_argument("reminder_id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("done", help="mark a reminder done")
    p.add_argument("reminder_id")
    p.set_defaults(func=cmd_done)

    p = sub.add_parser("snooze", help="hide a reminder until a later day")
    p.add_argument("reminder_id")
    p.add_argument("--until", required=True, metavar="YYYY-MM-DD")
    p.set_defaults(func=cmd_snooze)

    p = sub.add_parser("due", help="everything due: reminders and expired triage parks")
    p.add_argument("--on", default=None, metavar="YYYY-MM-DD", help="the UTC day (default: today)")
    p.add_argument("--json", action="store_true", help="versioned machine contract, never capped")
    p.set_defaults(func=cmd_due)

    # Root accepted before AND after the verb, like triage_cli.py.
    for sp in {id(q): q for q in sub.choices.values()}.values():
        sp.add_argument("--project-root", default=argparse.SUPPRESS,
                        help="Project root (same as before the verb)")
    return parser


def main(argv: list[str] | None = None) -> int:
    # Non-ASCII titles must not crash on a legacy console codepage (cp1252), and the
    # machine contract is UTF-8 whatever the host default is.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ReminderNotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except ReminderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (LockTimeout, OSError) as exc:
        print(f"error: the reminder store is busy or unreadable: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
