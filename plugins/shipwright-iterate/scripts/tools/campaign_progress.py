#!/usr/bin/env python3
"""Campaign progress tracker for iterate campaigns.

Reads/updates status.json and provides units for autonomous_loop.py init.

Usage:
    # List units in autonomous_loop.py-compatible format
    uv run campaign_progress.py list-units --campaign-dir <path>

    # Mark the campaign as started (top-level status draft -> active)
    uv run campaign_progress.py start --campaign-dir <path>

    # Update a sub-iterate's status (auto-sets campaign status -> complete
    # once every sub-iterate is complete)
    uv run campaign_progress.py update-status --campaign-dir <path> \
        --sub-iterate-id 14.2 --status complete --commit abc123 --branch iterate/14.2-x

    # Print human-readable summary (includes the top-level lifecycle status)
    uv run campaign_progress.py summary --campaign-dir <path>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _find_shared_scripts() -> Path:
    """Locate shared/scripts/ by walking up — robust to plugin-layout depth
    (dev monorepo root vs installed plugin-cache ``shipwright/`` root). Mirrors
    ``campaign_init._find_shared_scripts``."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "shared" / "scripts"
        if candidate.is_dir():
            return candidate
    return here.parents[4] / "shared" / "scripts"  # historical fallback


_SHARED_SCRIPTS = str(_find_shared_scripts())
if _SHARED_SCRIPTS not in sys.path:
    sys.path.insert(0, _SHARED_SCRIPTS)

from lib.campaign_status import (  # noqa: E402
    all_subs_complete,
    regenerate_campaign_status,
)


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


# Producer-owned campaign lifecycle: draft -> active -> complete.
#   draft    = planned, lives only in triage (set by campaign_init.py)
#   active   = started, shown on the board (set by `start`)
#   complete = done, hidden (set automatically once every sub-iterate completes)
# The field is optional: consumers treat its absence as "legacy" and fall back
# to derived done<total, so adding it never breaks an existing campaign.
LIFECYCLE_STATUSES = ("draft", "active", "complete")


# Lifecycle ``-> complete`` rule lives in the shared SSoT
# (``lib.campaign_status.all_subs_complete``), so the producer CLI and S2/S3's
# pure projection share ONE definition. The alias preserves the historical name
# and the ``cmd_update_status`` call site (zero behaviour change — same object,
# asserted by ``test_campaign_status_projection.TestAllSubsCompleteAlias``).
_all_subs_complete = all_subs_complete


def cmd_start(args: argparse.Namespace) -> int:
    """Mark a campaign as started: top-level status -> active.

    Idempotent and legacy-safe — a campaign whose status.json predates the
    lifecycle field simply gains status='active'. The ->complete transition is
    owned by cmd_update_status (fires once every sub-iterate is complete).
    """
    campaign_dir = Path(args.campaign_dir)
    status = _load_status(campaign_dir)
    status["status"] = "active"
    _save_status(campaign_dir, status)
    print(json.dumps({"campaign": status.get("campaign"), "status": "active"}))
    return 0


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

    # Auto-advance the campaign to 'complete' once every sub-iterate is complete.
    # (The draft->active transition is owned by `start`.) Left untouched while
    # work remains, so a halted/incomplete campaign stays visible on the board.
    if _all_subs_complete(status):
        status["status"] = "complete"

    _save_status(campaign_dir, status)
    print(json.dumps({
        "updated": args.sub_iterate_id,
        "status": args.status,
        "campaign_status": status.get("status"),
    }))
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
        # Top-level lifecycle status (draft|active|complete); None for a legacy
        # campaign with no status field — consumers fall back to done<total.
        "status": status.get("status"),
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


def cmd_regenerate(args: argparse.Namespace) -> int:
    """Project the campaign's status.json from the event log and write it.

    Thin wrapper over the pure ``lib.campaign_status.regenerate_campaign_status``
    (campaign S2): reads the campaign.md skeleton + committed status.json +
    events log, never-downgrades, and persists the result. Prints a fixed-shape
    JSON summary. S3 wires the same pure core into worktree finalize.
    """
    campaign_dir = Path(args.campaign_dir)
    try:
        status, summary = regenerate_campaign_status(campaign_dir, args.events_log)
    except (FileNotFoundError, ValueError) as e:
        # FileNotFoundError: campaign.md absent. ValueError: malformed skeleton
        # (no table / duplicate / empty id). Both are clean operator errors —
        # exit 1 with a message, never a traceback. (A corrupt committed
        # status.json no longer raises — the wrapper rebuilds with no baseline.)
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    _save_status(campaign_dir, status)
    summary["output_path"] = str(campaign_dir / "status.json")
    summary["campaign_status"] = status.get("status")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Campaign progress tracker")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list-units", help="List units for autonomous_loop.py")
    p_list.add_argument("--campaign-dir", required=True)

    p_start = sub.add_parser("start", help="Mark campaign as started (status -> active)")
    p_start.add_argument("--campaign-dir", required=True)

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

    p_regen = sub.add_parser(
        "regenerate",
        help="Project status.json from the event log (never-downgrade) and write it",
    )
    p_regen.add_argument("--campaign-dir", required=True)
    p_regen.add_argument("--events-log", required=True,
                         help="Path to shipwright_events.jsonl to project from")

    args = parser.parse_args()
    cmd_map = {
        "list-units": cmd_list_units,
        "start": cmd_start,
        "update-status": cmd_update_status,
        "summary": cmd_summary,
        "regenerate": cmd_regenerate,
    }
    return cmd_map[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
