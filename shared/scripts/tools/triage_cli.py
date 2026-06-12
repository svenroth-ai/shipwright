#!/usr/bin/env python3
"""Triage Inbox CLI — operate on `.shipwright/triage.jsonl` from the shell.

iterate-2026-05-20-triage-launch-surface — the monorepo / CLI surface for
the launch-surface redesign. CLI = first-class operation interface; the
shipwright-webui Triage tab (Iterate B) is a thin wrapper over the same
library helpers (``triage_promote.promote`` / ``triage_promote.dismiss``).

Subcommands (positional ``<id>`` for promote/dismiss):

  list [--json]                         list open triage items (--json = a
                                        machine-readable contract for the WebUI;
                                        adds pendingDelivery for outbox-only items)
  promote <id> --task-ref EXT:<ref>     promote → backlog task
  dismiss <id> --reason <reason>        dismiss (false-positive / won't-fix)

Fix-now flow:
  - operators open ``.shipwright/agent_docs/triage_inbox.md`` (or run
    ``triage_cli.py list``)
  - they copy the ``launchPayload`` fence into a new Claude session
  - the matching slash command (``/shipwright-security``,
    ``/shipwright-iterate --type bug``, etc.) auto-fires there
  - the lifecycle hook flips this item once the resulting run completes
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from triage import (  # noqa: E402
    _append_ids_at,
    _outbox_path,
    _triage_path,
    read_all_items,
)
from lib.tty_sanitize import strip_control_chars as _strip_control_chars  # noqa: E402
from tools.triage_promote import dismiss, promote  # noqa: E402

_BY_LABEL = "cli"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _fence_opener(payload: str) -> str:
    """Pick a fence opener long enough to contain ``payload``."""
    longest = 0
    run = 0
    for ch in payload:
        if ch == "`":
            run += 1
            if run > longest:
                longest = run
        else:
            run = 0
    return "`" * max(3, longest + 1)


def _format_item(item: dict) -> str:
    item_id = item.get("id", "")
    severity = item.get("severity", "")
    kind = item.get("kind", "")
    # F31 (SECURITY): strip terminal control chars from the title — the list
    # view prints straight to a TTY, and the title can carry an attacker-
    # influenceable GitHub workflow name / branch with embedded ESC/BEL.
    # launchPayload was already stripped below; the title was not.
    title = _strip_control_chars(str(item.get("title", "")))
    source = item.get("source", "")
    dedup_key = item.get("dedupKey") or ""
    payload = item.get("launchPayload")
    lines = [
        f"- {item_id}  severity={severity} kind={kind} source={source}"
        + (f" dedupKey={dedup_key}" if dedup_key else ""),
        f"  title: {title}",
    ]
    if isinstance(payload, str) and payload.strip():
        clean = _strip_control_chars(payload)
        fence = _fence_opener(clean)
        lines.append("  launch payload (copy into a new Claude session):")
        lines.append(f"  {fence}text")
        for line in clean.splitlines():
            lines.append(f"  {line}")
        lines.append(f"  {fence}")
    elif source == "github":
        lines.append("  [!] no launch payload — producer bug; please report")
    return "\n".join(lines)


def _ensure_utf8_stdout() -> None:
    """Pin stdout to UTF-8 regardless of the console codepage.

    On Windows ``sys.stdout`` defaults to the legacy codepage (cp1252), so
    writing ``ensure_ascii=False`` JSON — or a stripped-but-non-ASCII human
    line (`_strip_control_chars` deliberately keeps >= 0xA0) — crashed with
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
    items = [it for it in read_all_items(project_root) if it.get("status") == "triage"]
    if getattr(args, "json", False):
        # Machine-readable contract for the WebUI live-view (trg-e2a0ebb3): the
        # SAME unioned open items, plus `pendingDelivery` = the item lives ONLY
        # in the gitignored outbox buffer (not yet swept into the tracked log),
        # so the UI can badge it. TRACKED-PREFERRED: an id in BOTH files is NOT
        # pending (parallels triage.mark_status residence). Empty → `[]`.
        outbox_ids = _append_ids_at(_outbox_path(project_root))
        tracked_ids = _append_ids_at(_triage_path(project_root))
        enriched = [
            {**it, "pendingDelivery": (it.get("id") in outbox_ids
                                       and it.get("id") not in tracked_ids)}
            for it in items
        ]
        sys.stdout.write(json.dumps(enriched, indent=2, ensure_ascii=False) + "\n")
        return 0
    if not items:
        sys.stdout.write("No open triage items.\n")
        return 0
    for item in items:
        sys.stdout.write(_format_item(item) + "\n\n")
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


def _cmd_dismiss(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root)
    try:
        result = dismiss(
            project_root,
            item_id=args.item_id,
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

    sys.stderr.write(f"dismissed {result['id']} (reason: {result['reason']})\n")
    return 0


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

    p_list = sub.add_parser("list", help="list open triage items")
    p_list.add_argument(
        "--json", action="store_true",
        help="emit open items as a JSON array (machine-readable contract for the "
             "WebUI; each item gains a pendingDelivery bool for outbox-only items)",
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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
