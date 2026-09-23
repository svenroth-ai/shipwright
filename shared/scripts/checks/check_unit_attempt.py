#!/usr/bin/env python3
"""Fencing-token pre-flight check CLI (campaign-dag-scheduler R4).

The sub-iterate-runner's own last line of defense, immediately before its F6
commit / Step 5 push: confirms this runner's `(unit_id, attempt_id)` is
STILL the current claim on `loop_state.json` before it pushes anything. A
reclaim (lease expiry at a wave boundary/`cmd_init`) between this runner's
own claim and now means someone else may already be building the same unit
— the push must abort, never silently proceed.

See `lib.loop_state.validate_attempt_token` for the actual comparison this
wraps; this CLI just makes it callable from a runner's own Bash step without
importing Python.

Exit codes:
- 0 — token matches (ALLOW — proceed with commit/push)
- 1 — state file missing/unreadable, or unit id not found (structural
  failure — never a reason to assume the token matched)
- 5 — token mismatch (BLOCK — `stale_attempt`, mirrors
  `autonomous_loop.cmd_record`'s own exit code for the same condition)

CLI:
    uv run shared/scripts/checks/check_unit_attempt.py \\
        --state "{state_path}" --unit "{unit_id}" --attempt-id "{attempt_id}" [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SHARED_LIB = Path(__file__).resolve().parents[1]
if str(_SHARED_LIB) not in sys.path:
    sys.path.insert(0, str(_SHARED_LIB))

from lib.loop_state import ACTIVE, find_unit_row, validate_attempt_token  # noqa: E402


def _emit(args: argparse.Namespace, *, decision: str, reason_code: str, detail: str) -> None:
    payload = {
        "decision": decision, "reason_code": reason_code,
        "state": str(Path(args.state).resolve()), "unit_id": args.unit,
        "attempt_id": args.attempt_id, "detail": detail,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"check_unit_attempt: {'ALLOW' if decision == 'allow' else 'BLOCK'} — {detail}",
              file=sys.stderr if decision == "block" else sys.stdout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fencing-token pre-flight check on a loop_state.json row.")
    parser.add_argument("--state", required=True, help="Path to loop_state.json")
    parser.add_argument("--unit", required=True, help="Unit id")
    parser.add_argument("--attempt-id", required=True, help="This runner's own claimed attempt_id")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    state_path = Path(args.state)
    if not state_path.exists():
        _emit(args, decision="block", reason_code="state_not_found", detail=f"state file not found: {state_path}")
        return 1
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _emit(args, decision="block", reason_code="state_unreadable", detail=f"could not read {state_path}: {exc}")
        return 1

    unit = find_unit_row(state, args.unit)
    if unit is None:
        _emit(args, decision="block", reason_code="unit_not_found", detail=f"unit {args.unit!r} not found")
        return 1

    if not validate_attempt_token(unit, args.attempt_id):
        _emit(args, decision="block", reason_code="stale_attempt",
              detail=f"unit {args.unit!r}'s current attempt_id is {unit.get('attempt_id')!r}, "
                     f"not the given {args.attempt_id!r} — a reclaim already happened")
        return 5

    # External Tier-3 PR review (GPT, round 18): a matching `attempt_id`
    # alone is not enough. `cmd_release` moves a claimed unit back to
    # `pending` (or `failed`) WITHOUT rotating `attempt_id` — the token
    # stays exactly what it was at claim time. In the window between a
    # release and any later reclaim (which would mint a fresh token), a
    # stale runner whose claim was released out from under it still
    # presents its OLD, still-matching token here and would otherwise be
    # ALLOWed to push for a unit it no longer owns. `lib.loop_state.ACTIVE`
    # is the state machine's own definition of "a runner or the merge
    # lane currently owns it" — require membership in it, not just a
    # matching token.
    if unit.get("status") not in ACTIVE:
        _emit(args, decision="block", reason_code="unit_not_active",
              detail=f"unit {args.unit!r}'s attempt_id matches, but its status is "
                     f"{unit.get('status')!r}, not one of {sorted(ACTIVE)} — "
                     "the claim was released or reused; refusing a stale push")
        return 5

    _emit(args, decision="allow", reason_code="ok", detail=f"attempt_id {args.attempt_id!r} is still current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
