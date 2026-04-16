#!/usr/bin/env python3
"""Campaign progress tracker for iterate campaigns.

Reads/updates status.json and provides units for autonomous_loop.py init.

Usage:
    # List units in autonomous_loop.py-compatible format
    uv run campaign_progress.py list-units --campaign-dir <path>

    # Update a sub-iterate's status
    uv run campaign_progress.py update-status --campaign-dir <path> \
        --sub-iterate-id 14.2 --status complete --commit abc123 --branch iterate/14.2-x

    # Print human-readable summary
    uv run campaign_progress.py summary --campaign-dir <path>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_status(campaign_dir: Path) -> dict:
    status_path = campaign_dir / "status.json"
    if not status_path.exists():
        print(f"ERROR: status.json not found in {campaign_dir}", file=sys.stderr)
        sys.exit(1)
    return json.loads(status_path.read_text(encoding="utf-8"))


def _save_status(campaign_dir: Path, status: dict) -> None:
    status_path = campaign_dir / "status.json"
    status_path.write_text(
        json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def cmd_list_units(args: argparse.Namespace) -> int:
    """Output units in the format autonomous_loop.py init --units-from expects."""
    status = _load_status(Path(args.campaign_dir))
    output = {"sub_iterates": status.get("sub_iterates", [])}
    print(json.dumps(output, indent=2))
    return 0


def cmd_update_status(args: argparse.Namespace) -> int:
    campaign_dir = Path(args.campaign_dir)
    status = _load_status(campaign_dir)

    found = False
    for si in status.get("sub_iterates", []):
        if si["id"] == args.sub_iterate_id:
            si["status"] = args.status
            if args.commit:
                si["commit"] = args.commit
            if args.branch:
                si["branch"] = args.branch
            if args.tests_passed is not None:
                si["tests_passed"] = args.tests_passed
            if args.tests_total is not None:
                si["tests_total"] = args.tests_total
            found = True
            break

    if not found:
        print(f"ERROR: Sub-iterate {args.sub_iterate_id} not found", file=sys.stderr)
        return 1

    _save_status(campaign_dir, status)
    print(json.dumps({"updated": args.sub_iterate_id, "status": args.status}))
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    status = _load_status(Path(args.campaign_dir))
    subs = status.get("sub_iterates", [])

    complete = sum(1 for s in subs if s.get("status") == "complete")
    failed = sum(1 for s in subs if s.get("status") == "failed")
    escalated = sum(1 for s in subs if s.get("status") == "escalated")
    pending = sum(1 for s in subs if s.get("status") in ("pending", None))

    summary = {
        "campaign": status.get("campaign"),
        "branch_strategy": status.get("branch_strategy"),
        "total": len(subs),
        "complete": complete,
        "failed": failed,
        "escalated": escalated,
        "pending": pending,
        "sub_iterates": [
            {"id": s["id"], "slug": s.get("slug", ""), "status": s.get("status", "pending")}
            for s in subs
        ],
    }
    print(json.dumps(summary, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Campaign progress tracker")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list-units", help="List units for autonomous_loop.py")
    p_list.add_argument("--campaign-dir", required=True)

    p_update = sub.add_parser("update-status", help="Update sub-iterate status")
    p_update.add_argument("--campaign-dir", required=True)
    p_update.add_argument("--sub-iterate-id", required=True)
    p_update.add_argument("--status", required=True,
                          choices=["pending", "in_progress", "complete", "failed", "escalated"])
    p_update.add_argument("--commit", default=None)
    p_update.add_argument("--branch", default=None)
    p_update.add_argument("--tests-passed", type=int, default=None)
    p_update.add_argument("--tests-total", type=int, default=None)

    p_summary = sub.add_parser("summary", help="Print campaign summary")
    p_summary.add_argument("--campaign-dir", required=True)

    args = parser.parse_args()
    cmd_map = {
        "list-units": cmd_list_units,
        "update-status": cmd_update_status,
        "summary": cmd_summary,
    }
    return cmd_map[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
