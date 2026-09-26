"""STRICT-STOP / draining for ``kind == "sub_iterate"`` campaigns
(campaign-dag-scheduler R5b,
``.shipwright/planning/iterate/2026-09-20-campaign-dag-scheduler-plan.md``
§ "R5b — serial merge lane").

Before R5b, a STRICT-STOP inside the merge lane (3f/3f-bis/3g) went straight
to ``campaign-mode.md`` step 4 (Finalize), leaving every unit that was not
already ``merged``/``failed`` sitting in whatever state it happened to be in
— a still-``claimed`` unit never promoted, a ``running`` unit whose Task was
mid-build, a ``merging`` unit whose PR was mid-``gh pr checks --watch``. R4's
own ``cmd_finalize`` (``lib.loop_state.sub_iterate_finalize_summary``)
already refuses while any unit sits outside :data:`lib.loop_state.TERMINAL`
(``{merged, failed, held}``), so a campaign that hit this path could never
cleanly finalize at all.

This module makes draining an explicit, BOUNDED two-phase procedure that
:func:`run_drain` performs once STRICT-STOP fires, before step 4 ever calls
``cmd_finalize``:

1. :func:`sweep_never_started` — every ``pending``/``claimed`` unit moves to
   ``held`` immediately, ``reason_code: "swept_never_started"`` (R4's own
   edges; also reused by ``cmd_next_batch``'s exit-4 stalled case, per
   ``references/campaign-dependency-graphs.md``'s exit-code table).
2. :func:`drain_once`, polled until nothing remains in
   ``{claimed, running, merging}`` — a ``pending``/``claimed`` unit found on
   ANY poll (not only bullet 1's one-shot pass — see round 7 below) is swept
   the same way; a ``running`` unit that finishes its
   build (reaches ``built``) is swept on to ``held``
   (``reason_code: "swept_after_build"``: its PR stays open, unmerged, for a
   resumed session); a ``running`` unit whose lease has gone stale is
   force-failed (``reason_code: "lease_expired_during_drain"``, NEVER
   reclaimed/relaunched); a ``running``/``merging`` unit still live once
   ``max_drain_seconds`` elapses is force-transitioned
   (``running -> failed`` / ``merging -> held``, ``reason_code:
   "drain_timeout"``) so draining is GUARANTEED to terminate even against a
   live-but-stuck runner. A unit already sitting at ``built``/``reviewed``
   when draining starts (queued behind the unit that was mid-flight when
   STRICT-STOP fired) is swept the same way as a running unit that just
   finished — its build succeeded; only the merge was deferred.

Every mutation here is audited the same shape ``lib.loop_mark.cmd_mark``
writes (``mark_audit`` entries, ``operator: "campaign-drain:strict-stop"``)
so a transcript reads identically whether a human or this drain sequence
produced a given ``held``/``failed`` row. Deliberately NOT built on top of
``cmd_mark`` itself: that CLI mutates one unit per invocation under its own
``--force``/``--confirm-no-task-running`` gate, and a STRICT-STOP sweep must
move an unbounded number of rows atomically under ONE ``loop.lock``
acquisition — looping N separate ``cmd_mark`` subprocess calls would not be
atomic across them (a concurrent ``next-batch`` could claim a
still-``pending`` row between two of those calls).

**Known, accepted limitation (Tier-3 review, R5b round 2): a forced
transition changes the RECORD, never the WORKER.** ``max_drain_seconds``
guarantees the STATE MACHINE reaches a terminal status; it does not, and
cannot, stop the spawned ``Task`` itself — the framework has no
cancellation primitive for an already-running ``Task``
(``2026-09-20-campaign-dag-scheduler.md``, Finding 5, documented before any
R-round of this campaign was built, not a gap this module introduced). A
``merging`` unit whose own in-flight ``gh pr checks --watch`` /
``gh pr merge`` was already running when the bound elapsed can therefore
still complete its merge genuinely, after its row has already been
force-transitioned to ``held``. The two remedies an external reviewer
originally proposed here — cancel/fence the worker, or never finalize until
it is confirmed stopped — are still not implementable with today's tooling:
the first has no primitive to call, and the second would reintroduce the
exact unbounded hang this module exists to close (a stuck-but-heartbeating
runner would wedge the campaign forever).

**R5b round 3-4: the live-reconciliation pass named above as a follow-up is
now built** — ``campaign-mode.md`` step 4 (Finalize) re-checks every
`held` unit whose `reason_code` is `drain_timeout` OR
`merge_confirmation_timeout` (round 4: the latter's PR is already KNOWN
merged — only its SHA confirmation timed out — so it needs the identical
correction, not a separate mechanism) against GitHub's own state, between
``campaign_drain.py run`` and ``cmd_finalize``, and corrects the record to
`merged` (via `loop_claim.py mark`'s audited operator-override path, which
re-verifies the SHA's ancestry itself) when the worker's own merge landed
after the forced transition. This closes the specific silent-corruption
case (a unit recorded `held` while its PR is actually merged on
`origin/{default}`) without needing to cancel or fence anything — it acts
on the RECORD after the fact, exactly like this module's own forced
transitions do, rather than attempting to control the WORKER. What remains
a genuine, accepted limitation is narrower now: the state machine can be
transiently inconsistent with GitHub between the forced `held` transition
and step 4's next reconciliation pass — never permanently, and never
silently past the next finalize.

**R5b round 7: `drain_once` itself now also sweeps `pending`/`claimed`
(Tier-3 review).** `sweep_never_started` runs exactly once, before polling
begins, and `loop.lock` is held only per mutation, not for the whole drain —
so a unit claimed by a concurrent `cmd_next_batch` in the window after that
one-shot sweep releases the lock previously had no code path back to a
terminal status at all: `drain_once` had no branch for `claimed`, so
`remaining_active` counted it forever and `run_drain`'s poll loop never
terminated, breaking this module's own "GUARANTEED to terminate" claim.
`drain_once` now re-sweeps `_NEVER_STARTED` on every poll, closing the gap;
the top-level one-shot sweep stays as-is, since it still resolves the common
case one `poll_interval_seconds` sooner.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from file_lock import LockTimeout, file_lock  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.loop_state import is_legal_transition, now_iso  # noqa: E402
from lib.unit_lease import is_unit_lease_stale  # noqa: E402

#: A round, documented guess (mirrors `lib.campaign_session_lock
#: .DEFAULT_STALE_AFTER_SECONDS`'s own rationale style) — no measured p95
#: behind it. Long enough that a genuinely still-building unit is not force-
#: failed out from under a merely-slow-but-healthy runner; short enough that
#: an operator watching a STRICT-STOP is not left waiting indefinitely.
DEFAULT_MAX_DRAIN_SECONDS = 1800.0

#: How long `run_drain`'s own poll loop sleeps between reload attempts.
DEFAULT_POLL_INTERVAL_SECONDS = 5.0

#: Units this module's sweep considers "never started".
_NEVER_STARTED = ("pending", "claimed")

#: Units a `built`/`reviewed` row (queued behind the unit that was mid-flight
#: when STRICT-STOP fired, or a `running` unit that just finished) sweeps to.
_BUILT_NOT_MERGED = ("built", "reviewed")


def _load_state(state_path: Path) -> dict:
    return json.loads(state_path.read_text(encoding="utf-8"))


def _save_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(state_path)


def _audit(unit: dict, *, frm: str, to: str, reason: str, ts: str) -> None:
    unit.setdefault("mark_audit", []).append(
        {"at": ts, "from": frm, "to": to, "reason": reason, "operator": "campaign-drain:strict-stop"})


def sweep_never_started(state: dict, *, now: str | None = None) -> list[dict]:
    """Pure mutation of `state["units"]` in place: every ``pending``/
    ``claimed`` unit -> ``held``, ``reason_code: "swept_never_started"``.
    Returns the list of ``{id, from}`` rows actually swept — empty when
    nothing was pending/claimed (idempotent: a second call finds nothing
    left to sweep)."""
    ts = now or now_iso()
    swept = []
    for unit in state.get("units", []):
        frm = unit.get("status")
        if frm not in _NEVER_STARTED:
            continue
        if not is_legal_transition(frm, "held"):
            continue  # defensive; every real _NEVER_STARTED state has this edge
        unit["status"] = "held"
        unit["reason_code"] = "swept_never_started"
        unit["held_at"] = ts
        _audit(unit, frm=frm, to="held", reason="STRICT-STOP sweep: unit never started", ts=ts)
        swept.append({"id": unit.get("id"), "from": frm})
    return swept


def drain_once(state: dict, *, elapsed_seconds: float, max_drain_seconds: float) -> list[dict]:
    """One polling pass over `state["units"]` (mutated in place). Returns the
    list of forced transitions this pass performed — empty means "nothing to
    do yet, keep waiting" (there may still be a live `running`/`merging` row
    within its own budget)."""
    ts = now_iso()
    actions: list[dict] = []
    for unit in state.get("units", []):
        status = unit.get("status")
        if status in _NEVER_STARTED:
            # A concurrent `cmd_next_batch` can claim a unit AFTER
            # `sweep_never_started()`'s one-shot pass at the top of
            # `run_drain()` (Tier-3 review, R5b round 7) -- `loop.lock` is
            # held only for the duration of each individual mutation, not
            # for the whole drain, so the window between the sweep's lock
            # release and this poll's own lock acquisition is real. Without
            # this branch `remaining_active()` would count that unit forever
            # (drain_once had no case for "claimed" at all), breaking the
            # "draining is GUARANTEED to terminate" invariant. Re-sweeping
            # here on every poll closes it; the top-level one-shot sweep
            # stays too, since it resolves the common case a full
            # `poll_interval_seconds` sooner.
            _force(unit, to="held", reason_code="swept_never_started", ts=ts, actions=actions)
        elif status == "running":
            if is_unit_lease_stale(unit):
                _force(unit, to="failed", reason_code="lease_expired_during_drain", ts=ts, actions=actions)
            elif elapsed_seconds >= max_drain_seconds:
                _force(unit, to="failed", reason_code="drain_timeout", ts=ts, actions=actions)
            # else: still within budget and lease-live — keep waiting.
        elif status in _BUILT_NOT_MERGED:
            _force(unit, to="held", reason_code="swept_after_build", ts=ts, actions=actions)
        elif status == "merging":
            if elapsed_seconds >= max_drain_seconds:
                _force(unit, to="held", reason_code="drain_timeout", ts=ts, actions=actions)
            # else: the merge lane is mid-flight (gh pr checks --watch, an
            # unbounded wait of its OWN) — no lease covers this state
            # (lib.loop_state._reconcile_leases excludes it for the same
            # reason), so only the deadline can force it.
    return actions


def _force(unit: dict, *, to: str, reason_code: str, ts: str, actions: list[dict]) -> None:
    frm = unit.get("status")
    if not is_legal_transition(frm, to):
        return  # defensive; every real caller of drain_once passes a legal pair
    unit["status"] = to
    unit["reason_code"] = reason_code
    unit[f"{to}_at"] = ts
    _audit(unit, frm=frm, to=to, reason=f"drain: {reason_code}", ts=ts)
    actions.append({"id": unit.get("id"), "from": frm, "to": to, "reason_code": reason_code})


def remaining_active(state: dict) -> list[str]:
    """Ids still outside :data:`lib.loop_state.TERMINAL`'s complement of
    "someone still owns this" — the guaranteed-to-shrink set `run_drain`
    polls against. Named separately from `lib.loop_state.ACTIVE` (which
    lists `{claimed, running, merging}` too) so this module has no import
    cycle back onto a value that would need re-exporting for a one-line
    reuse."""
    return [u["id"] for u in state.get("units", []) if u.get("status") in ("claimed", "running", "merging")]


def _with_lock(state_path: Path, fn):
    try:
        with file_lock(state_path.parent / "loop.lock", timeout_seconds=30):
            state = _load_state(state_path)
            if state.get("kind") != "sub_iterate":
                raise ValueError("campaign_drain is only valid for kind == 'sub_iterate'")
            result = fn(state)
            _save_state(state_path, state)
            return result
    except LockTimeout as exc:
        raise TimeoutError(f"loop.lock timeout: {exc}") from exc


def run_drain(state_path: Path | str, *, max_drain_seconds: float = DEFAULT_MAX_DRAIN_SECONDS,
              poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
              sleep_fn=time.sleep, time_fn=time.time) -> dict:
    """The full STRICT-STOP drain: sweep once, then poll :func:`drain_once`
    until nothing remains in ``{claimed, running, merging}``. GUARANTEED to
    terminate: the sweep clears `pending`/`claimed` immediately, and every
    `running`/`merging` row still live past `max_drain_seconds` is forced to
    a terminal state by `drain_once` itself. `sleep_fn`/`time_fn` are
    injectable (tests never sleep for real)."""
    state_path = Path(state_path)
    swept = _with_lock(state_path, sweep_never_started)
    drain_actions: list[dict] = []
    started = time_fn()
    while True:
        elapsed = time_fn() - started

        def _step(state, elapsed_seconds=elapsed):
            actions = drain_once(state, elapsed_seconds=elapsed_seconds, max_drain_seconds=max_drain_seconds)
            return actions, remaining_active(state)

        actions, remaining = _with_lock(state_path, _step)
        drain_actions.extend(actions)
        if not remaining:
            break
        sleep_fn(poll_interval_seconds)
    return {"swept": swept, "drain_actions": drain_actions, "drained": True}


def cmd_sweep(args: argparse.Namespace) -> int:
    try:
        swept = _with_lock(Path(args.state), sweep_never_started)
    except Exception as exc:  # noqa: BLE001 - CLI boundary: never an uncaught
        # traceback here (code-review round 1, low) — step 4's caller chains
        # this exit code with `|| STRICT-STOP`, exactly like every other
        # command in campaign-mode.md; an uncaught traceback would instead
        # skip that chain's own STOP and fall through with the loop's lock
        # never released, which "release on every path" (step 4) forbids.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"swept": swept}, ensure_ascii=False))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    try:
        result = run_drain(
            args.state, max_drain_seconds=args.max_drain_seconds,
            poll_interval_seconds=args.poll_interval_seconds)
    except Exception as exc:  # noqa: BLE001 - see cmd_sweep's own comment
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="STRICT-STOP draining for kind == 'sub_iterate' campaigns")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sweep = sub.add_parser("sweep", help="pending/claimed -> held (swept_never_started), once")
    p_sweep.add_argument("--state", required=True)

    p_run = sub.add_parser("run", help="sweep, then poll-drain {claimed,running,merging} to TERMINAL")
    p_run.add_argument("--state", required=True)
    p_run.add_argument("--max-drain-seconds", type=float, default=DEFAULT_MAX_DRAIN_SECONDS)
    p_run.add_argument("--poll-interval-seconds", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)

    args = parser.parse_args()
    cmd_map = {"sweep": cmd_sweep, "run": cmd_run}
    return cmd_map[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
