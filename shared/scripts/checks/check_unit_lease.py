#!/usr/bin/env python3
"""Per-unit lease heartbeat CLI (campaign-dag-scheduler R2 capability).

Naming precedent: ``check_campaign_session_lock.py`` in this same directory
guards the shared campaign worktree; this one guards ONE unit's own row in
``loop_state.json``. See ``lib/unit_lease.py`` for the full mechanism (why a
field-creating upsert, why no fencing yet, why warn-and-continue).

One command:

- ``touch`` — call at the runner's own step boundaries (Step 1 after branch
  setup, before Step 4 Finalization, before Step 5 Push), using the
  ``campaign_worktree``/``state_path`` brief parameters and this unit's own
  ``sub_iterate_id``. **Never fatal to the caller's own build** — a non-zero
  exit here means log and continue, exactly like a failed touch of the
  campaign session lock (``campaign-worktree.md``'s "touch coverage gap").

Exit codes:
- 0 — lease touched (fields written, echoed as JSON on stdout)
- 1 — could not touch (state file missing/unreadable, unit id not found, or
  the write itself failed) — warn-and-continue at the caller, never a reason
  to abort a build

CLI:
    uv run shared/scripts/checks/check_unit_lease.py touch \\
        --state "{state_path}" --unit-id "{sub_iterate_id}" \\
        --worktree "{campaign_worktree}" --branch "{branch_name}" \\
        [--campaign-worktree "{campaign_worktree}"] \\
        [--attempt 0] [--attempt-id <id>] [--stale-after-seconds N] [--json]

``--campaign-worktree`` (optional) cross-checks that ``--state`` actually
resolves under ``{campaign_worktree}/.shipwright/`` — catches the two brief
parameters having drifted apart (external plan review finding) rather than
silently touching an unrelated file. Omit it and no such check runs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SHARED_LIB = Path(__file__).resolve().parents[1]
if str(_SHARED_LIB) not in sys.path:
    sys.path.insert(0, str(_SHARED_LIB))

from lib.unit_lease import (  # noqa: E402
    DEFAULT_STALE_AFTER_SECONDS,
    UnitLeaseError,
    touch_unit_lease,
)


def _emit(args: argparse.Namespace, *, decision: str, detail: str, lease: dict | None = None) -> None:
    payload = {
        "decision": decision,
        "state": str(Path(args.state).resolve()),
        "unit_id": args.unit_id,
        "detail": detail,
    }
    if lease is not None:
        payload["lease"] = lease
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        verdict = "ALLOW" if decision == "allow" else "BLOCK"
        print(f"check_unit_lease {args.command}: {verdict}")
        print(detail, file=sys.stderr if decision == "block" else sys.stdout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Per-unit lease heartbeat on a loop_state.json row.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    touch_p = sub.add_parser("touch")
    touch_p.add_argument("--state", required=True, help="Path to loop_state.json")
    touch_p.add_argument("--unit-id", required=True)
    touch_p.add_argument("--worktree", required=True,
                          help="This unit's own worktree path (pre-flip: the shared campaign worktree)")
    touch_p.add_argument("--branch", default=None)
    touch_p.add_argument("--attempt", type=int, default=0)
    touch_p.add_argument("--attempt-id", default=None)
    touch_p.add_argument("--stale-after-seconds", type=float, default=DEFAULT_STALE_AFTER_SECONDS)
    touch_p.add_argument("--campaign-worktree", default=None,
                          help="Optional: cross-check --state resolves under "
                               "{this}/.shipwright/")
    touch_p.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    try:
        lease = touch_unit_lease(
            args.state, args.unit_id,
            worktree=args.worktree, branch=args.branch,
            attempt=args.attempt, attempt_id=args.attempt_id,
            stale_after_seconds=args.stale_after_seconds,
            expected_campaign_worktree=args.campaign_worktree,
        )
    except UnitLeaseError as exc:
        _emit(args, decision="block", detail=str(exc))
        return 1

    if lease.get("stale_attempt_conflict"):
        print(
            f"check_unit_lease: WARNING — touching a row no longer mine "
            f"(unit {args.unit_id!r} attempt {args.attempt} < recorded attempt "
            f"{lease.get('row_attempt')}) — a reconcile may have already reclaimed "
            "this unit (doubt-reviewer note: expected/noisy until R4 wires the "
            "real attempt through to this call — not yet a trustworthy signal)",
            file=sys.stderr,
        )

    _emit(args, decision="allow",
          detail=f"lease touched for unit {args.unit_id!r} (lease_touched_at={lease['lease_touched_at']:.0f})",
          lease=lease)
    return 0


if __name__ == "__main__":
    sys.exit(main())
