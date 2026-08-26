#!/usr/bin/env python3
"""Session-liveness guard for the shared campaign worktree.

Closes ``campaign-worktree.md``'s "No cross-session lock" known limitation.
Three commands, all against the same lock keyed to ``{campaign_wt}``:

- ``acquire`` — campaign-worktree.md Setup (Autonomous Campaign Loop step 0,
  once, right after the worktree resolves). Fails when a DIFFERENT, still-live
  session already holds it.
- ``touch``   — campaign-mode.md loop steps 3a/3g (every iteration, and again
  before the unbounded ``gh pr checks --watch``), so a genuinely active
  campaign never goes stale mid-loop. Fails on "no lock is held at all" (call
  ``acquire`` first) distinctly from "a different session now holds it" (the
  loop's exclusive claim is genuinely gone) — see
  ``lib/campaign_session_lock.touch`` for why these are never collapsed.
- ``release`` — campaign-mode.md step 4 (Finalize, once, on the way out). A
  no-op if this session doesn't hold the lock; never fails.

See ``lib/campaign_session_lock.py`` for the liveness model (heartbeat +
staleness threshold — there is no single OS process to attach an OS-level
lock to).

Exit codes:
- 0 — lock acquired / renewed / released
- 1 — refused: ``acquire`` found a live different session; ``touch`` found no
  lock at all, or a different session now holding it. The JSON payload's
  ``reason`` field discriminates ``refused`` (a genuine lock-state refusal —
  the cases above) from ``io_error`` (a lock-file read/write itself failed —
  file permissions, a lock-mutex timeout, disk trouble) so an operator is not
  told to delete a state file over a problem deleting it cannot fix.

CLI:
    uv run shared/scripts/checks/check_campaign_session_lock.py acquire \\
        --campaign-worktree "{campaign_wt}" --session-id "{session_id}" \\
        [--stale-after-seconds N] [--json]
    uv run shared/scripts/checks/check_campaign_session_lock.py touch \\
        --campaign-worktree "{campaign_wt}" --session-id "{session_id}" [--json]
    uv run shared/scripts/checks/check_campaign_session_lock.py release \\
        --campaign-worktree "{campaign_wt}" --session-id "{session_id}" [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SHARED_LIB = Path(__file__).resolve().parents[1]
if str(_SHARED_LIB) not in sys.path:
    sys.path.insert(0, str(_SHARED_LIB))

from lib.campaign_session_lock import (  # noqa: E402
    DEFAULT_STALE_AFTER_SECONDS,
    CampaignLockError,
    acquire,
    release,
    touch,
)
from lib.file_lock import LockTimeout  # noqa: E402


def _emit(args: argparse.Namespace, *, decision: str, detail: str, reason: str = "") -> None:
    payload = {
        "decision": decision,
        "campaign_worktree": str(Path(args.campaign_worktree).resolve()),
        "session_id": args.session_id,
        "detail": detail,
    }
    if reason:
        payload["reason"] = reason
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        verdict = "ALLOW" if decision == "allow" else "BLOCK"
        print(f"check_campaign_session_lock {args.command}: {verdict}")
        print(detail, file=sys.stderr if decision == "block" else sys.stdout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Campaign session-liveness guard (cross-session lock).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("acquire", "touch", "release"):
        p = sub.add_parser(name)
        p.add_argument("--campaign-worktree", required=True)
        p.add_argument("--session-id", required=True)
        p.add_argument("--json", action="store_true")
        if name == "acquire":
            p.add_argument("--stale-after-seconds", type=float,
                            default=DEFAULT_STALE_AFTER_SECONDS)

    args = parser.parse_args(argv)
    campaign_wt = Path(args.campaign_worktree).resolve()

    if args.command == "release":
        try:
            release(campaign_wt, session_id=args.session_id)
        except CampaignLockError as exc:
            _emit(args, decision="block", detail=str(exc), reason="io_error")
            return 1
        _emit(args, decision="allow", detail="lock released (or was already absent)")
        return 0

    try:
        if args.command == "acquire":
            status = acquire(campaign_wt, session_id=args.session_id,
                              stale_after_seconds=args.stale_after_seconds)
        else:
            status = touch(campaign_wt, session_id=args.session_id)
    except CampaignLockError as exc:
        _emit(args, decision="block", detail=str(exc), reason="refused")
        return 1
    except (LockTimeout, OSError) as exc:
        _emit(args, decision="block", detail=str(exc), reason="io_error")
        return 1

    _emit(args, decision="allow",
          detail=(f"session {status.owner_session_id} holds the lock "
                   f"(acquired_at={status.acquired_at:.0f}, last_touch={status.last_touch:.0f})"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
