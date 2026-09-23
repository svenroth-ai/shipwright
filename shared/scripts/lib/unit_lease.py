"""Per-unit lease/heartbeat mechanism on ``loop_state.json`` rows (R2).

Campaign ``campaign-dag-scheduler`` R2
(``.shipwright/planning/iterate/campaigns/campaign-dag-scheduler/sub-iterates/R2-worktree-capability.md``).
Under the wave model (the orchestrator is blocked for the whole
``sub-iterate-runner`` Task — build + reviews + F0-F6 + push — and again
across ``gh pr checks --watch``), the campaign session lock's own touches
(``campaign-mode.md`` steps 3a/3g) do not cover either of those two
unbounded windows — see ``campaign-worktree.md``'s "touch coverage gap".
This module closes the FIRST one: the runner itself heartbeats its own unit
row while it is the process actually occupying the worktree.

Lease fields (``attempt``, ``lease_touched_at``, ``lease_expires_at``,
``worktree``, ``branch``) live on the unit's own row in ``loop_state.json``,
guarded by the SAME ``loop.lock`` / ``file_lock`` ``autonomous_loop.py``
already serializes every other ``loop_state.json`` write through —
deliberately not a second state file, so there is only ever one mutex to
reason about for this file. ``attempt_id`` lives on the same row but is
NEVER touch-created — see below.

**Field-creating upsert for the lease fields; `attempt_id` is read/validated
only, never minted.** R2 is independent of R1 in this campaign's own DAG, so
a row is not guaranteed to already carry the lease fields (`_load_units_from`'s
fixed key set does not mint them) — the first touch for a unit creates them.
`attempt_id` is different: `loop_claim._claim_unit` is its sole minter
(external Tier-3 PR review, round 8) — a touch only ECHOES the row's current
value back, and if the caller supplies a real token, validates it against
that value: a mismatch — including a token supplied for a row that has none
yet — raises :class:`UnitLeaseError` before any lease field is mutated
(round 7 added the mismatch check; round 8 closed the token-less-row minting
gap it still allowed; round 22 closed the complementary gap those two left
open — a `kind == "sub_iterate"` row that already carries a real token now
REQUIRES a matching one on every touch, not just when one happens to be
supplied, so a caller cannot simply omit `--attempt-id` to bypass the
check entirely). No caller today (`check_unit_lease.py`'s CLI,
`sub-iterate-runner.md`'s brief) passes a real `attempt_id`, so round 22's
requirement is fully inert until R5a wires one through — a never-claimed
row (no `attempt_id` yet) is completely unaffected and behaves exactly as
before.

**Warn-and-continue, never fatal.** A touch can fail for reasons that say
nothing about whether the runner's own build is healthy — the lock released
early, the row reclaimed past staleness by a reconcile, or the worktree
recreated out from under it (mid-build). The caller (``sub-iterate-runner``)
must treat any :class:`UnitLeaseError` here as advisory: log and proceed.
The orchestrator's own step-3a/3g campaign-session-lock touches remain the
authoritative lock-lost detector; aborting a near-finished build over a
heartbeat hiccup is strictly worse than the staleness risk this mitigates.

**Ghost-touch marking (external plan review, GLM + OpenAI, medium — a cheap
addition, not fencing).** Pre-R4 there is still no rejection: a touch always
succeeds. But a runner whose row has since moved to a HIGHER `attempt` than
the one it is touching with (a reconcile already reclaimed this unit while
the old runner kept running) is touching a row that used to be its own.
:func:`touch_unit_lease` compares against the row's real `attempt` counter
and returns `stale_attempt_conflict: True` in that case, so a caller CAN
choose to log a distinguishable warning ("touching a row no longer mine")
instead of a silent heartbeat — but (Stage-2 code review, high; fixed) it
never WRITES its own `attempt` value over that counter, since the counter is
`autonomous_loop.py`'s (`_reconcile_in_progress`, `cmd_next`), not this
module's: doing so on every heartbeat (the runner always touches with
`attempt=0`) would have silently reset the real retry counter to zero and
then reported every later touch as a false conflict.

**Known limitation (doubt-reviewer, medium — NOT yet fixed; R4 landed the
fencing primitives this needs, but not this call site — deferred to R5a,
where the runner brief that would carry a real `--attempt` is actually
built; see `iterate-2026-09-22-r4-state-mechanics-review-findings.md`):**
`sub-iterate-runner.md` never passes its own `--attempt` (it has no brief
parameter to pass), so every touch compares the row's real counter against a
hardcoded `attempt=0`. Once a reconcile has ever bumped that counter (any
prior reconcile of THIS unit, for any reason — `lib.loop_state.reconcile_in_progress`
for the new fencing-based claims, `autonomous_loop.cmd_next`'s legacy path
otherwise), every subsequent touch from the unit's sole, legitimate,
still-healthy runner reports `stale_attempt_conflict: True` — this is an
EXPECTED, common false positive today, not evidence of an actual ownership
conflict, and must not be treated as a trustworthy fencing signal until R5a
wires the real attempt through to the runner's touch call.

**Optional campaign-worktree consistency check** (external plan review, GLM
finding 4 + OpenAI finding 3): `campaign_worktree` and `state_path` are two
independently-populated brief parameters by design (R2 spec v6 — both must
survive R5a's `{project_root}` repoint unchanged, so neither is derived from
the other at consumption time). Passing `expected_campaign_worktree` here
cross-checks that `state_path` actually resolves under
`{expected_campaign_worktree}/.shipwright/` and raises
:class:`UnitLeaseError` (still warn-and-continue at the caller) if a caller's
two brief parameters have drifted apart — catching an orchestration bug
(wrong `state_path` for this `campaign_worktree`) rather than silently
touching an unrelated file.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.atomic_write import durable_atomic_write, durable_read_text  # noqa: E402
from lib.campaign_session_lock import DEFAULT_STALE_AFTER_SECONDS  # noqa: E402,F401 (re-exported: single source of truth for the 7200s heartbeat constant)
from lib.file_lock import LockTimeout, file_lock  # noqa: E402

LOOP_LOCK_FILENAME = "loop.lock"


class UnitLeaseError(RuntimeError):
    """Raised when a unit's lease cannot be touched — ALWAYS warn-and-continue
    at the caller (see module docstring); never a reason to abort a build."""


def _lock_path(state_path: Path) -> Path:
    return Path(state_path).parent / LOOP_LOCK_FILENAME


def _find_unit(state: dict, unit_id: str) -> dict | None:
    """Exact match first (``autonomous_loop.cmd_record``'s own convention),
    case-folded fallback (``lib.loop_state.is_unit_ready``'s convention) — a
    lease touch must find the same row either lookup style would."""
    units = state.get("units") or []
    for unit in units:
        if unit.get("id") == unit_id:
            return unit
    folded = str(unit_id).lower()
    for unit in units:
        if str(unit.get("id")).lower() == folded:
            return unit
    return None


def _campaign_worktree_mismatch(state_path: Path, expected_campaign_worktree: str | None) -> str:
    """``""`` if `state_path` resolves under
    `{expected_campaign_worktree}/.shipwright/`, else a message describing
    the mismatch. `expected_campaign_worktree=None` skips the check
    entirely (opt-in — see module docstring)."""
    if expected_campaign_worktree is None:
        return ""
    expected_shipwright_dir = (Path(expected_campaign_worktree) / ".shipwright").resolve()
    try:
        state_path.resolve().relative_to(expected_shipwright_dir)
    except ValueError:
        return (
            f"state path {state_path} does not resolve under "
            f"{expected_shipwright_dir} — campaign_worktree/state_path have drifted apart"
        )
    return ""


def touch_unit_lease(
    state_path: Path | str,
    unit_id: str,
    *,
    worktree: str,
    branch: str | None,
    attempt: int = 0,
    attempt_id: str | None = None,
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
    now: float | None = None,
    expected_campaign_worktree: str | None = None,
) -> dict:
    """Field-creating upsert of this unit's lease fields. Returns the lease
    fields written (a plain ``dict``, not the whole row) — ``attempt_id`` is
    always the row's EXISTING value echoed back, never written by this
    function (`loop_claim._claim_unit` is its sole minter) — plus
    ``stale_attempt_conflict`` (see module docstring's "Ghost-touch
    marking") and ``row_attempt`` (the row's real attempt counter after this
    touch — may differ from the echoed ``attempt`` the caller touched with).

    Raises :class:`UnitLeaseError` when the state file is missing/unreadable,
    a caller-supplied `attempt_id` does not match the row's current value
    (including a row with none yet — see module docstring),
    `expected_campaign_worktree` is given and does not match `state_path`,
    the unit id is not found, or the write itself fails — every case the
    caller must treat as warn-and-continue (module docstring).
    """
    state_path = Path(state_path)
    if not state_path.exists():
        raise UnitLeaseError(f"loop state file not found: {state_path}")

    mismatch = _campaign_worktree_mismatch(state_path, expected_campaign_worktree)
    if mismatch:
        raise UnitLeaseError(mismatch)

    try:
        with file_lock(_lock_path(state_path), timeout_seconds=30):
            try:
                state = json.loads(durable_read_text(state_path, encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise UnitLeaseError(f"could not read {state_path}: {exc}") from exc

            unit = _find_unit(state, unit_id)
            if unit is None:
                raise UnitLeaseError(
                    f"unit {unit_id!r} not found in {state_path} — cannot touch its lease")

            # External Tier-3 PR review (GPT, rounds 7-8): unlike the
            # `attempt` int counter below (a documented false-positive-prone
            # diagnostic — see "Known limitation" above), `attempt_id` is a
            # real fencing TOKEN with no false-positive case, so a caller
            # that supplies one is enforced against the row's CURRENT value —
            # including `None` (round 8: a token-less row has nothing to
            # match, so a supplied token is rejected rather than minted;
            # `loop_claim._claim_unit` is the sole minter, never this touch).
            # A caller that supplies no token (every caller today) is
            # unaffected either way.
            existing_attempt_id = unit.get("attempt_id")
            if attempt_id and attempt_id != existing_attempt_id:
                raise UnitLeaseError(
                    f"attempt token mismatch for {unit_id!r}: touch carries {attempt_id!r}, "
                    f"row's real token is {existing_attempt_id!r} — refusing to mutate lease fields")
            # External Tier-3 PR review (GPT, round 22): rounds 7-8 above
            # only validate a SUPPLIED token — they say nothing about a
            # caller that supplies NONE while the row already carries a
            # real one. That tokenless path let ANY caller (a stale runner
            # whose claim was already reclaimed, in particular) keep
            # mutating a CLAIMED row's lease fields — including extending
            # `lease_expires_at` indefinitely — with no proof of current
            # ownership, undermining the single-writer fencing R4 exists to
            # provide. Scoped to `kind == "sub_iterate"` (the only kind
            # `attempt_id` is ever minted for) and to rows that already
            # carry a token — a never-claimed row has nothing to prove
            # ownership of yet, and is unaffected. This is a no-op against
            # every row in production TODAY (see "Known limitation" above:
            # `loop_claim._claim_unit`, via `cmd_next_batch`, is the sole
            # minter, and nothing dispatches through that path until R5a's
            # flip — `campaign-mode.md`'s own "R4's cmd_next_batch is the
            # first wiring point" note) — it only takes effect once a row
            # actually carries a real token, which is exactly the case this
            # check exists to protect.
            if state.get("kind") == "sub_iterate" and existing_attempt_id and not attempt_id:
                raise UnitLeaseError(
                    f"attempt token required for {unit_id!r}: row is claimed (token "
                    f"{existing_attempt_id!r}), touch supplied none — refusing to mutate "
                    "a claimed row's lease fields without proof of current ownership")

            existing_attempt = unit.get("attempt")
            stale_attempt_conflict = (
                isinstance(existing_attempt, int) and not isinstance(existing_attempt, bool)
                and existing_attempt > attempt
            )

            touched_at = _now() if now is None else now
            lease = {
                "lease_touched_at": touched_at,
                "lease_expires_at": touched_at + stale_after_seconds,
                "worktree": str(worktree),
                "branch": branch,
            }
            unit.update(lease)
            # `attempt_id` is the atomic-claim fencing token
            # (`loop_claim.py`'s sole minter) — this touch never writes it,
            # only echoes the row's existing value back (round 8: any
            # caller-supplied value already matched it or was rejected
            # above, so there is nothing left to write).
            lease["attempt_id"] = existing_attempt_id
            # Stage-2 code review (high): `attempt` is `autonomous_loop`'s own
            # retry counter (`_reconcile_in_progress`, `cmd_next`), not a lease
            # field this module owns — every real row already carries it from
            # `_load_units_from`, so overwriting it here on every heartbeat
            # (the runner always touches with its own `attempt=0`) silently
            # reset the counter and manufactured a false `stale_attempt_conflict`
            # on every subsequent touch. Create it ONLY if truly absent or not a
            # real int (field-creating upsert, unchanged for a hypothetical bare
            # or foreign-schema row); never overwrite a genuine existing value
            # (doubt-reviewer, low: a non-int leftover must not survive either).
            row_attempt = unit.get("attempt")
            if not isinstance(row_attempt, int) or isinstance(row_attempt, bool):
                unit["attempt"] = attempt
                row_attempt = attempt

            try:
                durable_atomic_write(
                    state_path, json.dumps(state, indent=2, ensure_ascii=False) + "\n")
            except OSError as exc:
                raise UnitLeaseError(f"could not write {state_path}: {exc}") from exc

            # `attempt` echoes the CALLER's own value (what it touched with);
            # `row_attempt` is the row's real, possibly-different counter — a
            # caller reporting `stale_attempt_conflict` needs both to explain
            # why (doubt-reviewer, low: the old single value made the warning
            # unexplainable).
            return {"attempt": attempt, **lease, "row_attempt": row_attempt,
                    "stale_attempt_conflict": stale_attempt_conflict}
    except LockTimeout as exc:
        # External code review (GLM, medium): file_lock's own LockTimeout is
        # NOT a UnitLeaseError, and check_unit_lease.py only catches the
        # latter — an uncaught LockTimeout here would surface as a raw
        # traceback instead of the documented "exit 1, JSON block payload"
        # CLI contract on lock contention (plausible: N runners + the
        # orchestrator's own writes serialize on the same loop.lock).
        raise UnitLeaseError(f"could not acquire {_lock_path(state_path)}: {exc}") from exc


def _now() -> float:
    return time.time()


def is_unit_lease_stale(unit: dict, *, now: float | None = None) -> bool:
    """``True`` iff `unit` carries a ``lease_expires_at`` that has passed.

    A unit with NO ``lease_expires_at`` key at all (never touched) is NOT
    considered stale — this predicate answers "has an existing lease gone
    stale", not "does this unit have a live lease"; a caller wanting the
    latter checks for the field's presence first.

    A unit whose ``lease_expires_at`` IS present but not a real number (a
    hand-repaired state file, a foreign schema, a future migration writing an
    ISO string like every OTHER timestamp on this row) is treated as STALE,
    not "not yet expired" (doubt-reviewer, medium: failing open here would
    let a gating caller skip this unit's reconciliation forever instead of
    erroring or recovering — corrupted data must never look like a live
    lease).
    """
    if "lease_expires_at" not in unit:
        return False
    expires_at = unit.get("lease_expires_at")
    if not isinstance(expires_at, (int, float)) or isinstance(expires_at, bool):
        return True
    return (now if now is not None else _now()) > expires_at
