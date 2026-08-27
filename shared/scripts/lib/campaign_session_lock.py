"""Session-liveness lock for the shared campaign worktree.

Closes ``campaign-worktree.md``'s "No cross-session lock" known limitation:
two orchestrator sessions on the SAME campaign slug (two operators, or one
operator resuming a session it believed had died) both reach the same
``campaign_wt`` and can spawn ``sub-iterate-runner`` subagents whose
``git checkout -b`` races the other's in the one shared directory.
``autonomous_loop.py``'s ``file_lock`` only serializes ``loop_state.json``
writes and does not cover this.

There is no single OS process to attach an OS-level lock to: the campaign
loop is driven by a series of independent ``uv run`` subprocess calls issued
across a Claude Code session's tool calls, not one long-lived process (unlike
``lib.host_resource_lease``, which brackets exactly one resource-holding
subprocess). So liveness here is a heartbeat: the lock records who holds it
and when they last touched it, and a DIFFERENT session may only reclaim it
once that touch is older than ``stale_after_seconds`` — presumed abandoned
(crashed / killed session), never blocked forever. The SAME ``session_id``
always succeeds (the legitimate resume path — this relies on the SessionStart
hook payload's ``session_id`` staying stable across a Claude Code resume,
which is the assumption ``capture_session_id.py`` already makes elsewhere; a
resume that ever minted a fresh id would make every resume look like a
different, second session).

Call sites: ``campaign-worktree.md`` Setup (acquire, once), ``campaign-mode.md``
loop step 3a AND step 3g (touch, at the top of every iteration and again
immediately before ``gh pr checks --watch``), and step 4 (release, once, on
the way out — see :func:`release`). Neither touch covers the wait it
precedes: a touch only resets the deadline at that instant, so a `--watch`
(or the merge-poll after it) or a `sub-iterate-runner` Task that itself runs
past ``stale_after_seconds`` can still go stale mid-wait; see
``campaign-worktree.md``'s "touch coverage gap" for the honest accounting.

Deliberately cheap, two documented residual limitations rather than solved:
a corrupted or partially-written state file's CONTENT is treated as "no lock
held" and silently overwritten (``durable_atomic_write`` makes a torn write
from THIS module's own writers impossible, so this only matters for external
tampering) — a failed READ is a different thing and is NOT swallowed here,
since that would fail the guard open exactly where it exists to fail closed;
see :func:`_load`. And a ``last_touch`` timestamp in the future — clock skew,
a clock correction — is not clamped, so it can extend the effective
staleness window beyond ``stale_after_seconds``. Both would need genuine
schema validation and a bounded-skew policy to close, which is more
machinery than a heartbeat lock over a shared, already git-ignored worktree
directory warrants.
"""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.atomic_write import durable_atomic_write, durable_read_text  # noqa: E402
from lib.file_lock import file_lock  # noqa: E402

LOCK_STATE_FILENAME = "campaign_session.lock.json"
LOCK_MUTEX_FILENAME = "campaign_session.lock"

#: Longest a live campaign session can go WITHOUT A TOUCH before a competing
#: session may treat it as dead and reclaim it — not a bound on one
#: iteration's wall-clock time. A touch only resets the deadline at the
#: instant it runs (campaign-mode.md steps 3a/3g); it does not cover the wait
#: that follows. The `sub-iterate-runner` Task (build + reviews + F0-F6 +
#: push) and `gh pr checks --watch` + the merge poll are both unbounded and
#: untouched while they run, so either CAN exceed this window on a slow
#: sub-iterate — that is a documented, known gap (campaign-worktree.md
#: "touch coverage gap"), not something this constant's size rules out. No
#: measured p95 backs this value; it is a round, generous guess. Picked
#: generously rather than tuned for fast reclaim, because the failure mode of
#: too-short is silent split-brain (two sessions racing the same worktree)
#: while too-long only delays recovery from a genuinely dead session.
DEFAULT_STALE_AFTER_SECONDS = 7200.0  # 2h


class CampaignLockError(RuntimeError):
    """Raised when the campaign session lock cannot be acquired or renewed."""


def _now() -> float:
    return time.time()


def _state_path(campaign_wt: Path) -> Path:
    return Path(campaign_wt) / ".shipwright" / LOCK_STATE_FILENAME


def _mutex_path(campaign_wt: Path) -> Path:
    return Path(campaign_wt) / ".shipwright" / LOCK_MUTEX_FILENAME


def _load(state_path: Path) -> dict | None:
    """Return the parsed lock state, or ``None`` if none is held.

    Only a garbage-content file (undecodable bytes, invalid JSON, a wrong
    shape) is treated as "no lock held" — that is external tampering, and
    the module docstring accepts silently overwriting it. A failed READ
    (permissions, a transient sharing violation) is NOT swallowed: it
    propagates, so a competing session blocks rather than treating a lock
    it merely could not read as absent.
    """
    if not state_path.exists():
        return None
    try:
        data = json.loads(durable_read_text(state_path, encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    session_id = data.get("session_id")
    last_touch = data.get("last_touch")
    acquired_at = data.get("acquired_at")
    if not isinstance(session_id, str) or not session_id:
        return None
    if isinstance(last_touch, bool) or not isinstance(last_touch, (int, float)):
        return None
    if isinstance(acquired_at, bool) or not isinstance(acquired_at, (int, float)):
        return None
    return data


def _write(state_path: Path, data: dict) -> None:
    durable_atomic_write(state_path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


@dataclass(frozen=True)
class LockStatus:
    owner_session_id: str
    acquired_at: float
    last_touch: float


def _validated_stale_after_seconds(stale_after_seconds) -> float:
    """A finite, non-negative number of seconds — or ``CampaignLockError``.

    ``NaN`` is the one that matters: every ``age <= stale_after_seconds``
    comparison against it is ``False``, so it would silently disable the
    staleness guard and let every acquire reclaim (split-brain, no
    diagnostic) — mirrors ``lib.file_lock._validated_timeout``.
    """
    if (isinstance(stale_after_seconds, bool)
            or not isinstance(stale_after_seconds, (int, float))):
        raise CampaignLockError(
            f"stale_after_seconds must be a number, got {stale_after_seconds!r}")
    value = float(stale_after_seconds)
    if not math.isfinite(value) or value < 0:
        raise CampaignLockError(
            f"stale_after_seconds must be finite and >= 0, got {stale_after_seconds!r}")
    return value


def acquire(campaign_wt: Path, *, session_id: str,
            stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS) -> LockStatus:
    """Acquire (or renew, for the same session) the campaign session lock.

    Raises :class:`CampaignLockError` when a DIFFERENT session holds the lock
    and last touched it within ``stale_after_seconds`` — the cross-session
    collision this guard exists to reject. A stale different-session lock is
    reclaimed rather than left blocking the campaign forever.
    """
    if not session_id:
        raise CampaignLockError("session_id is required to acquire the campaign lock")
    stale_after_seconds = _validated_stale_after_seconds(stale_after_seconds)
    campaign_wt = Path(campaign_wt)
    state_path = _state_path(campaign_wt)
    with file_lock(_mutex_path(campaign_wt), timeout_seconds=30):
        existing = _load(state_path)
        now = _now()
        if existing is not None and existing["session_id"] != session_id:
            age = now - existing["last_touch"]
            if age <= stale_after_seconds:
                last_touch_wall = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(existing["last_touch"]))
                raise CampaignLockError(
                    f"campaign worktree {campaign_wt} is locked by session "
                    f"{existing['session_id']!r} (last active {age:.0f}s ago, "
                    f"at {last_touch_wall}); refusing to start a second session "
                    "against it. Only if you have confirmed no sub-iterate-runner "
                    f"Task is still running against this worktree, delete "
                    f"{state_path} to reclaim it now — deleting it while that "
                    "session's runner is still live re-opens the exact race this "
                    "lock exists to prevent."
                )
        same_owner = existing is not None and existing["session_id"] == session_id
        acquired_at = existing["acquired_at"] if same_owner else now
        _write(state_path, {
            "session_id": session_id,
            "acquired_at": acquired_at,
            "last_touch": now,
        })
        return LockStatus(owner_session_id=session_id, acquired_at=acquired_at, last_touch=now)


def touch(campaign_wt: Path, *, session_id: str) -> LockStatus:
    """Refresh the lock's last-touch timestamp.

    Raises :class:`CampaignLockError` if this session cannot renew — two
    distinct causes, reported distinctly (never collapsed into one "reclaimed
    as stale" message: that wording is false for the first case, and it is
    exactly the case an operator following the ``acquire`` delete-remedy, or a
    session touching before it ever acquired, lands in):

    - no lock is held at all (never acquired here, or the state file was
      deleted for a manual reclaim) — a caller mid-loop should treat this the
      same as the case below (it never legitimately reaches a running loop),
      but a fresh caller should ``acquire`` first rather than error;
    - a DIFFERENT session now holds it (genuinely reclaimed after going
      stale) — the loop no longer has exclusive claim to the worktree.

    Either way, ``campaign-mode.md`` names the response LOCK-LOST — distinct
    from its more common STRICT-STOP, because STRICT-STOP proceeds to step 4
    (Finalize), which writes ``loop_state.json``, and a lock-loss means a
    second session may already be driving that same file.
    """
    if not session_id:
        raise CampaignLockError("session_id is required to touch the campaign lock")
    campaign_wt = Path(campaign_wt)
    state_path = _state_path(campaign_wt)
    with file_lock(_mutex_path(campaign_wt), timeout_seconds=30):
        existing = _load(state_path)
        if existing is None:
            raise CampaignLockError(
                f"no campaign lock is held at {state_path} — nothing to renew "
                f"for session {session_id!r}. Call acquire first (a fresh "
                "start, or recovery after the state file was deleted)."
            )
        if existing["session_id"] != session_id:
            raise CampaignLockError(
                f"campaign worktree {campaign_wt} is no longer locked by session "
                f"{session_id!r} (currently held by {existing['session_id']!r}); "
                "the lock was reclaimed as stale."
            )
        existing["last_touch"] = _now()
        _write(state_path, existing)
        return LockStatus(owner_session_id=existing["session_id"],
                           acquired_at=existing["acquired_at"], last_touch=existing["last_touch"])


def release(campaign_wt: Path, *, session_id: str) -> None:
    """Remove the lock this session holds, so a NEW session_id (the routine
    case: an operator's Claude Code session died or exhausted context and
    they started a fresh one) is never refused for up to
    ``stale_after_seconds`` after a campaign that already finished cleanly.

    A no-op, not an error, if nothing is held or a different session holds it
    — releasing is a courtesy on the way out (campaign-mode.md step 4), never
    itself worth STRICT-STOPping a campaign that otherwise finalized.
    """
    if not session_id:
        raise CampaignLockError("session_id is required to release the campaign lock")
    campaign_wt = Path(campaign_wt)
    state_path = _state_path(campaign_wt)
    with file_lock(_mutex_path(campaign_wt), timeout_seconds=30):
        existing = _load(state_path)
        if existing is None or existing["session_id"] != session_id:
            return
        state_path.unlink(missing_ok=True)
