#!/usr/bin/env python3
"""Triage Inbox CLI — operate on `.shipwright/triage.jsonl` from the shell.

iterate-2026-05-20-triage-launch-surface — the monorepo / CLI surface for
the launch-surface redesign. CLI = first-class operation interface; the
shipwright-webui Triage tab (Iterate B) is a thin wrapper over the same
library helpers (``triage_promote.promote`` / ``triage_promote.dismiss``).

Subcommands (positional ``<id>`` for promote/dismiss):

  list                                  list open triage items
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
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from triage import read_all_items  # noqa: E402
from tools.triage_promote import dismiss, promote  # noqa: E402

_BY_LABEL = "cli"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _strip_control_chars(text: str) -> str:
    """Strip terminal control sequences while preserving newlines and tabs.

    Review finding #10: a malformed producer could embed ESC / BEL etc.
    into ``launchPayload``. The CLI prints to a tty; stripping is the
    minimal defense.
    """
    return "".join(
        ch for ch in text
        if ch in ("\n", "\t") or (0x20 <= ord(ch) < 0x7F) or ord(ch) >= 0x80
    )


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
    title = item.get("title", "")
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


def _cmd_list(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root)
    items = [it for it in read_all_items(project_root) if it.get("status") == "triage"]
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
