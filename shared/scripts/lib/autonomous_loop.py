"""Autonomous loop state-machine for shipwright-build and shipwright-iterate.

CLI-based state engine called from SKILL.md (Claude-driven loop).
Claude handles Task-tool spawning; this script handles state, locking,
reconciliation, contract validation, and handoff aggregation.

Commands:
    init     — initialize loop_state.json from a units file
    next     — pick the next pending unit (stdout JSON, exit 0/2/1)
    record   — record a subagent result for a unit
    finalize — aggregate handoffs and print summary

Campaign-dag-scheduler R4: the 9-state ``sub_iterate`` machine lives in
``lib.loop_state``/``lib.loop_claim``; this module is the thinner dispatcher
for the four commands above, shared by both `kind`s. `kind == "section"`
sees ZERO behavior change anywhere in this file.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from branch_base import resolve_base_branch
from file_lock import LockTimeout, file_lock

# shared/scripts (the `lib.` package root) — needed ALONGSIDE the sibling
# insert above so `lib.loop_state` resolves per this campaign's import
# convention (never a bare `loop_state`, which would be the ADR-045
# lib-collision class the new modules exist to avoid). `branch_base`/
# `file_lock` stay bare-imported above, unchanged — loop_state.py imports
# `branch_base` the same bare way, so it is never loaded under two names.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.loop_state import (  # noqa: E402
    STATES,
    _load_units_from,
    cmd_init_sub_iterate_payload,
    describe_blocker,
    enforce_record_fencing,
    find_unit_row,
    handoff_dir_for,
    is_unit_ready,
    now_iso,
    reconcile_in_progress,
    resolve_record_status,
    runs_dir_for,
    sub_iterate_finalize_summary,
)


VALID_STATUSES = {"pending", "in_progress", "complete", "failed", "escalated", "merged"}
VALID_KINDS = {"section", "sub_iterate"}
# "serial" (interleaved-campaign default) joins the legacy strategies; base-ref
# resolution per strategy lives in branch_base.resolve_base_branch.
VALID_STRATEGIES = {"single-branch", "stacked", "independent", "serial"}

def _load_state(state_path: Path) -> dict:
    if not state_path.exists():
        print(f"ERROR: State file not found: {state_path}", file=sys.stderr)
        sys.exit(1)
    return json.loads(state_path.read_text(encoding="utf-8"))


def _save_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(state_path)


def cmd_init(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    stdin = args.units_from == "-"
    units_path = None if stdin else Path(args.units_from)
    stdin_text = (sys.stdin.read() if not sys.stdin.isatty() else "") if stdin else None
    if not stdin and not units_path.exists():
        print(f"ERROR: Units file not found: {units_path}", file=sys.stderr)
        return 1
    if stdin and not stdin_text.strip():
        print("ERROR: No units JSON received on stdin", file=sys.stderr)
        return 1

    if state_path.exists():
        # This read-modify-write shares `loop.lock` with every other
        # loop_state.json writer (cmd_next/cmd_record/touch_unit_lease), so a
        # concurrent lease heartbeat is serialized rather than clobbered.
        with file_lock(state_path.parent / "loop.lock", timeout_seconds=30):
            existing = _load_state(state_path)

            # kind == "sub_iterate" (R4 work item 7) resumes mid-wave state
            # (built/reviewed/merging) in place instead of reinitializing.
            if existing.get("kind") == "sub_iterate":
                payload, mutated = cmd_init_sub_iterate_payload(state_path, existing)
                if payload:
                    if mutated:
                        for w in payload.get("warnings", []):
                            print(f"RECONCILE: {w}", file=sys.stderr)
                        _save_state(state_path, existing)
                    print(json.dumps(payload))
                    return 0
                # else: unit list genuinely empty -> fall through to reinit,
                # exactly like kind == "section" always has.
            else:
                in_progress = [u for u in existing.get("units", []) if u["status"] == "in_progress"]
                if in_progress:
                    warnings = reconcile_in_progress(existing, existing.get("kind"), state_path)
                    for w in warnings:
                        print(f"RECONCILE: {w}", file=sys.stderr)
                    _save_state(state_path, existing)
                    print(json.dumps({"action": "reconciled", "warnings": warnings}))
                    return 0

                pending = [u for u in existing.get("units", []) if u["status"] == "pending"]
                if pending:
                    print(json.dumps({"action": "resumed", "pending": len(pending)}))
                    return 0

    loop_id = f"{args.kind}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    try:
        units = _load_units_from(units_path, args.kind, text=stdin_text)
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid units JSON{' on stdin' if stdin else ''}: {exc}", file=sys.stderr)
        return 1

    if not units:
        print(json.dumps({"action": "empty", "reason": "No pending units found"}))
        return 2

    state = {
        "version": 2,  # additive superset of v1's row shape (R4) — harmless
        # for kind == "section", whose row shape never used a schema version
        # at all; a v1 reader degrades to cmd_next's plain serial-FIFO.
        "loop_id": loop_id,
        "kind": args.kind,
        "root_session_id": args.root_session_id or os.environ.get("SHIPWRIGHT_ROOT_SESSION_ID", ""),
        "branch_strategy": args.branch_strategy,
        "created_at": now_iso(),
        "units": units,
    }

    _save_state(state_path, state)
    print(json.dumps({
        "action": "initialized",
        "loop_id": loop_id,
        "total_units": len(units),
    }))
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    lock_path = state_path.parent / "loop.lock"

    with file_lock(lock_path, timeout_seconds=30):
        state = _load_state(state_path)
        units = state.get("units", [])
        kind = state.get("kind")

        for unit in units:
            if unit["status"] == "pending":
                # sub_iterate-gated: a pending unit blocked on an unmerged
                # `depends_on` edge is skipped as if it weren't there (R1);
                # `section` is untouched. `loop_claim.cmd_next_batch` is this
                # command's batch-parallel sibling, with its own exit codes.
                if kind == "sub_iterate" and not is_unit_ready(unit, units):
                    continue
                unit["status"] = "in_progress"
                unit["started_at"] = now_iso()
                head_sha = None
                try:
                    r = subprocess.run(
                        ["git", "rev-parse", "HEAD"],
                        capture_output=True, text=True, timeout=10,
                    )
                    if r.returncode == 0:
                        head_sha = r.stdout.strip()
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass
                unit["head_sha"] = head_sha

                base_branch = resolve_base_branch(state["branch_strategy"], units, unit)

                _save_state(state_path, state)

                output = {
                    "id": unit["id"],
                    "spec_path": unit.get("spec_path", ""),
                    "base_branch": base_branch,
                    "attempt": unit.get("attempt", 0),
                    "loop_id": state["loop_id"],
                    "kind": state["kind"],
                    "root_session_id": state.get("root_session_id", ""),
                }
                print(json.dumps(output))
                return 0

        # A `pending` unit still here is BLOCKED, not finished (R1) — every
        # `pending` unit reaching this line failed the ready-check above, by
        # construction. Exit code stays 2 (unchanged), but the body is now
        # OBSERVABLE so a blocked-but-not-finished campaign is distinguishable
        # from genuine completion, and never reads as "All units processed".
        blocked_pending = [u for u in units if u["status"] == "pending"] if kind == "sub_iterate" else []
        if blocked_pending:
            print(json.dumps({
                "done": True, "reason": "Campaign stalled: pending units blocked on unmerged dependencies",
                "blocked_pending_ids": [u["id"] for u in blocked_pending],
                "blockers": [describe_blocker(u, units) for u in blocked_pending],
            }))
        else:
            print(json.dumps({"done": True, "reason": "All units processed"}))
        return 2


def _validate_result(result: dict, kind: str) -> list[str]:
    """Validate result JSON against the contract. Returns list of errors."""
    errors = []
    if "status" not in result:
        errors.append("Missing 'status' field")
    elif result["status"] not in ("complete", "failed", "escalated"):
        errors.append(f"Invalid status: {result['status']}")

    if result.get("status") == "complete":
        for field in ("commit", "tests_passed", "tests_total"):
            if field not in result:
                errors.append(f"Missing required field for complete: {field}")

    return errors


def cmd_record(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    lock_path = state_path.parent / "loop.lock"

    result_str = args.result
    result: dict[str, Any] = {}
    attempt_id = getattr(args, "attempt_id", None)

    # Fencing FAST-FAIL only (R4 work items 4/5, gated kind == "sub_iterate"
    # only): a separate, short-lived lock acquisition that never touches
    # `kind == "section"` state, and — deliberately — is NOT the check this
    # command relies on for correctness. `target_status` is unknown yet
    # (parsing hasn't happened), so no legality check runs here either. The
    # REAL check re-runs, with a target, inside each write block below,
    # against state loaded fresh in that SAME lock acquisition (external
    # code review, OpenAI, high — see `enforce_record_fencing`'s docstring
    # for why a single early check is a TOCTOU race a reclaim can win).
    with file_lock(lock_path, timeout_seconds=30):
        state_peek = _load_state(state_path)
        if state_peek.get("kind") == "sub_iterate":
            rejection = enforce_record_fencing(state_path, state_peek, args.unit, attempt_id, result_str)
            if rejection is not None:
                return rejection

    try:
        result = json.loads(result_str)
    except json.JSONDecodeError:
        state_peek = _load_state(state_path)
        loop_id = state_peek.get("loop_id", "")
        # External Tier-3 PR review (GPT, PR #790 round 21): `args.unit` is
        # raw, unvalidated CLI input reaching `runs_dir_for`'s charset gate
        # (round 9) here — unlike every other call site in this function,
        # which passes an already state-matched unit's canonical `id`. A
        # malformed `--unit` must fall through to the existing "no fallback
        # available" structured-failure path below, not crash uncaught.
        try:
            fallback_path = runs_dir_for(state_path, loop_id, args.unit) / "result.json"
        except ValueError:
            fallback_path = None
        if fallback_path is not None and fallback_path.exists():
            try:
                result = json.loads(fallback_path.read_text(encoding="utf-8"))
                print(f"WARN: Task returned non-JSON, using fallback {fallback_path}", file=sys.stderr)
            except (json.JSONDecodeError, OSError):
                pass

        if not result:
            with file_lock(lock_path, timeout_seconds=30):
                state = _load_state(state_path)
                is_sub_iterate = state.get("kind") == "sub_iterate"
                if is_sub_iterate:
                    rejection = enforce_record_fencing(state_path, state, args.unit, attempt_id,
                                                         result_str, target_status="failed")
                    if rejection is not None:
                        return rejection
                # Scoped-review fix (low, finding I): same case-fold lookup
                # as the success path below (Stage-3 doubt review LOW #1) —
                # a case-mismatched `--unit` that passes the fencing check
                # above must not then silently no-op against an exact-match
                # write loop that finds nothing.
                target_unit = find_unit_row(state, args.unit) if is_sub_iterate else None
                for unit in state["units"]:
                    if unit is target_unit or (target_unit is None and unit["id"] == args.unit):
                        unit["status"] = "failed"
                        unit["finished_at"] = now_iso()
                        unit["failure_reason"] = f"Non-JSON result: {result_str[:500]}"
                        break
                _save_state(state_path, state)
            print(f"ERROR: Non-JSON result and no fallback for {args.unit}", file=sys.stderr)
            return 3

    errors = _validate_result(result, "")
    if errors:
        with file_lock(lock_path, timeout_seconds=30):
            state = _load_state(state_path)
            is_sub_iterate = state.get("kind") == "sub_iterate"
            if is_sub_iterate:
                rejection = enforce_record_fencing(state_path, state, args.unit, attempt_id,
                                                     result_str, target_status="failed")
                if rejection is not None:
                    return rejection
            target_unit = find_unit_row(state, args.unit) if is_sub_iterate else None
            for unit in state["units"]:
                if unit is target_unit or (target_unit is None and unit["id"] == args.unit):
                    unit["status"] = "failed"
                    unit["finished_at"] = now_iso()
                    unit["failure_reason"] = f"Contract violation: {'; '.join(errors)}"
                    break
            _save_state(state_path, state)
        print(f"ERROR: Contract violation: {errors}", file=sys.stderr)
        return 3

    with file_lock(lock_path, timeout_seconds=30):
        state = _load_state(state_path)
        is_sub_iterate = state.get("kind") == "sub_iterate"
        # Stage-3 doubt review (LOW #1): a `kind == "sub_iterate"` state uses
        # the SAME case-fold-aware lookup (`find_unit_row`) the fencing
        # pre-check above already uses — a case-mismatched `--unit` that
        # passes the fence via case-fold must not then be silently dropped
        # by an exact-match write loop that finds nothing (which used to
        # still print `{"recorded": true}` / exit 0). `kind == "section"`
        # keeps its original exact-match lookup unchanged.
        target_unit = find_unit_row(state, args.unit) if is_sub_iterate else next(
            (u for u in state["units"] if u["id"] == args.unit), None)
        if is_sub_iterate and target_unit is not None:
            target_status = resolve_record_status(state.get("kind"), target_unit, result.get("status", "failed"))
            rejection = enforce_record_fencing(state_path, state, args.unit, attempt_id,
                                                 result_str, target_status=target_status)
            if rejection is not None:
                return rejection
        if is_sub_iterate and target_unit is None:
            print(json.dumps({"recorded": False, "error": f"no unit matching {args.unit!r}"}), file=sys.stderr)
            return 3
        for unit in state["units"]:
            if unit is target_unit or (target_unit is None and unit["id"] == args.unit):
                unit["status"] = resolve_record_status(state.get("kind"), unit, result.get("status", "failed"))
                unit["finished_at"] = now_iso()
                unit["commit"] = result.get("commit")
                unit["branch"] = result.get("branch", unit.get("branch"))
                unit["failure_reason"] = result.get("error") or (result.get("reason") if result.get("status") != "complete" else None)  # escalated carries `reason`, not `error`; scoped so a complete unit never gains one

                # External Tier-3 PR review (GPT, PR #790 round 21): `unit["id"]`
                # here is the CANONICAL id of an already-matched row, not raw
                # CLI input — but a hand-edited or corrupted `loop_state.json`
                # could still carry one outside `runs_dir_for`'s charset gate
                # (round 9's threat model, the same one round 19 already fixed
                # for `_reconcile_legacy`). Fail closed with this function's
                # own structured-failure shape instead of an uncaught
                # traceback, and — per the reviewer's own fix suggestion —
                # WITHOUT persisting any of this block's in-memory mutations:
                # `_save_state` below is never reached on this path.
                try:
                    runs_dir = runs_dir_for(state_path, state["loop_id"], unit["id"])
                except ValueError as exc:
                    print(json.dumps({"recorded": False, "error": str(exc)}), file=sys.stderr)
                    return 3
                runs_dir.mkdir(parents=True, exist_ok=True)
                (runs_dir / "result.json").write_text(
                    json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                unit["result_path"] = str(runs_dir / "result.json")

                # External Tier-3 PR review (GPT, PR #790 round 23): defense
                # in depth only — `state["loop_id"]` here is the exact same
                # value `runs_dir_for` just validated two lines above (it
                # charset-checks `loop_id` itself, not just `unit_id` — see
                # its own docstring), so this call cannot actually raise on
                # this path today. Wrapped anyway to match this file's own
                # established fail-closed style at every other
                # runs_dir_for/handoff_dir_for call site (rounds 9, 19, 21)
                # and to stay safe if the two calls are ever reordered or
                # decoupled. No new regression test: one would only re-prove
                # the existing runs_dir_for coverage two lines above.
                try:
                    handoff_dir = handoff_dir_for(state_path, state["loop_id"])
                except ValueError as exc:
                    print(json.dumps({"recorded": False, "error": str(exc)}), file=sys.stderr)
                    return 3
                handoff_path = handoff_dir / f"{unit['id']}.md"
                if handoff_path.exists():
                    unit["handoff_path"] = str(handoff_path)

                break
        _save_state(state_path, state)

    if result.get("status") != "complete":
        print(json.dumps({"recorded": True, "status": result.get("status"), "unit": args.unit}))
        return 3

    print(json.dumps({"recorded": True, "status": "complete", "unit": args.unit}))
    return 0


def _cmd_finalize_strict_sub_iterate_applies(state: dict) -> bool:
    """Whether `cmd_finalize` should dispatch into the strict
    `sub_iterate_finalize_summary` gate rather than the legacy summary below.

    Stage-3 doubt review (HIGH #1): `sub_iterate_finalize_summary` refuses
    ANY non-TERMINAL unit with no compatibility path for a row still
    carrying pre-R4 legacy vocabulary (`"complete"`, `"escalated"`,
    `"in_progress"`) — a never-claimed row's own documented pass-through
    (`resolve_record_status`, `enforce_record_fencing`). Gate the NEW,
    strict finalize on the SAME compatibility boundary those two functions
    already use: only dispatch into it once this campaign has actually
    been touched by the new atomic-claim flow (some unit carries a real
    `attempt_id` — the only thing that ever mints one is
    `loop_claim.cmd_next_batch`). A campaign with none falls through
    UNCHANGED to the legacy branch below, exactly as it did before this
    `kind == "sub_iterate"` branch existed — this campaign never refused
    finalize outright even on a genuinely incomplete run; it only reported
    `terminal_reason` as informational text.

    Scoped-review fix (medium, finding C): `any(...)` alone would trap a
    campaign straddling the R5a flip — some units finished under the old
    serial cmd_next/cmd_record path (legacy "complete", no attempt_id),
    others claimed by the new cmd_next_batch flow — in the strict branch
    forever, since nothing promotes a legacy "complete" row into the
    9-state vocabulary post-hoc. Require the WHOLE vocabulary to be
    9-state before trusting the strict branch; a mixed campaign falls
    through to the legacy branch below, exactly the pre-R4 behaviour and
    therefore never worse than today."""
    all_new_vocabulary = all(u["status"] in STATES for u in state["units"])
    return (
        state.get("kind") == "sub_iterate" and all_new_vocabulary
        and any(u.get("attempt_id") for u in state["units"])
    )


def cmd_finalize(args: argparse.Namespace) -> int:
    state_path = Path(args.state)

    # campaign-dag-scheduler R5b round 8 (Tier-3 review): the "every unit is
    # TERMINAL" decision below used to read `loop_state.json` unlocked --
    # `campaign_drain.run_drain`'s own last poll releases `loop.lock` once it
    # sees nothing left in {claimed, running, merging}, and this read could
    # then land after ANY other loop.lock-respecting writer (cmd_next_batch,
    # cmd_release, an operator's `loop_claim.py mark`) has landed a fresh
    # non-terminal transition in between -- exactly the window
    # campaign-mode.md step 4 relies on NOT existing ("draining is GUARANTEED
    # to terminate ... so cmd_finalize can no longer legitimately refuse").
    # Loading state and deciding the strict sub_iterate branch under the SAME
    # lock every other writer already respects makes this atomic against all
    # of them, not just the ones a manual audit could rule out today.
    try:
        with file_lock(state_path.parent / "loop.lock", timeout_seconds=30):
            state = _load_state(state_path)
            if _cmd_finalize_strict_sub_iterate_applies(state):
                error, summary = sub_iterate_finalize_summary(state)
                if error:
                    print(json.dumps(error), file=sys.stderr)
                    return 1
                print(json.dumps(summary, indent=2))
                return 0
    except LockTimeout as exc:
        print(json.dumps({"error": "lock_timeout", "detail": str(exc)}), file=sys.stderr)
        return 1

    completed = [u for u in state["units"] if u["status"] == "complete"]
    failed = [u for u in state["units"] if u["status"] == "failed"]
    escalated = [u for u in state["units"] if u["status"] == "escalated"]
    pending = [u for u in state["units"] if u["status"] == "pending"]

    # External Tier-3 PR review (GPT, PR #790 round 23): unlike cmd_record's
    # call sites (rounds 9/19/21), nothing in this function validates
    # `state["loop_id"]` before this point — a hand-edited or corrupted
    # `loop_state.json` crashed `cmd_finalize` with an uncaught traceback
    # instead of this function's own structured-failure shape.
    try:
        handoff_dir = handoff_dir_for(state_path, state["loop_id"])
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    aggregated_parts = []
    if handoff_dir.exists():
        for md_file in sorted(handoff_dir.glob("*.md")):
            if md_file.name == "campaign.md":
                continue
            aggregated_parts.append(f"## {md_file.stem}\n\n{md_file.read_text(encoding='utf-8')}")

    terminal_reason = "all_complete"
    if failed:
        terminal_reason = f"failed: {', '.join(u['id'] for u in failed)}"
    elif escalated:
        terminal_reason = f"escalated: {', '.join(u['id'] for u in escalated)}"
    elif pending:
        terminal_reason = f"incomplete: {len(pending)} pending"

    if aggregated_parts:
        handoff_dir.mkdir(parents=True, exist_ok=True)
        campaign_handoff = handoff_dir / "campaign.md"
        header = f"# Loop Handoff — {state['loop_id']}\n\n"
        header += f"**Status:** {terminal_reason}\n"
        header += f"**Completed:** {len(completed)}/{len(state['units'])}\n\n"
        campaign_handoff.write_text(header + "\n---\n\n".join(aggregated_parts), encoding="utf-8")

    summary = {
        "loop_id": state["loop_id"],
        "kind": state["kind"],
        "completed": len(completed),
        "failed": len(failed),
        "escalated": len(escalated),
        "pending": len(pending),
        "total": len(state["units"]),
        "terminal_reason": terminal_reason,
        "commits": [u["commit"] for u in completed if u.get("commit")],
    }
    print(json.dumps(summary, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Autonomous loop state-machine for Shipwright"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize loop state")
    p_init.add_argument("--state", required=True, help="Path to loop_state.json")
    p_init.add_argument("--units-from", required=True, help="Units source file, or - to read JSON from stdin")
    p_init.add_argument("--kind", required=True, choices=sorted(VALID_KINDS))
    p_init.add_argument("--branch-strategy", default="single-branch", choices=sorted(VALID_STRATEGIES))
    p_init.add_argument("--root-session-id", default="")

    p_next = sub.add_parser("next", help="Pick next pending unit")
    p_next.add_argument("--state", required=True, help="Path to loop_state.json")

    p_record = sub.add_parser("record", help="Record subagent result")
    p_record.add_argument("--state", required=True, help="Path to loop_state.json")
    p_record.add_argument("--unit", required=True, help="Unit ID")
    p_record.add_argument("--result", required=True, help="Result JSON string")
    p_record.add_argument("--attempt-id", default=None,
                           help="Fencing token (required when kind == 'sub_iterate', campaign-dag-scheduler R4)")

    p_finalize = sub.add_parser("finalize", help="Aggregate handoffs and print summary")
    p_finalize.add_argument("--state", required=True, help="Path to loop_state.json")

    args = parser.parse_args()

    cmd_map = {
        "init": cmd_init,
        "next": cmd_next,
        "record": cmd_record,
        "finalize": cmd_finalize,
    }
    return cmd_map[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
