"""Autonomous loop state-machine for shipwright-build and shipwright-iterate.

CLI-based state engine called from SKILL.md (Claude-driven loop).
Claude handles Task-tool spawning; this script handles state, locking,
reconciliation, contract validation, and handoff aggregation.

Commands:
    init     — initialize loop_state.json from a units file
    next     — pick the next pending unit (stdout JSON, exit 0/2/1)
    record   — record a subagent result for a unit
    finalize — aggregate handoffs and print summary
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
from file_lock import file_lock

# shared/scripts (the `lib.` package root) — needed ALONGSIDE the sibling
# insert above so `lib.loop_state` resolves per this campaign's import
# convention (never a bare `loop_state`, which would be the ADR-045
# lib-collision class the new modules exist to avoid). `branch_base`/
# `file_lock` stay bare-imported above, unchanged — loop_state.py imports
# `branch_base` the same bare way, so it is never loaded under two names.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.loop_state import _load_units_from, describe_blocker, is_unit_ready  # noqa: E402


VALID_STATUSES = {"pending", "in_progress", "complete", "failed", "escalated", "merged"}
VALID_KINDS = {"section", "sub_iterate"}
# "serial" (interleaved-campaign default) joins the legacy strategies; base-ref
# resolution per strategy lives in branch_base.resolve_base_branch.
VALID_STRATEGIES = {"single-branch", "stacked", "independent", "serial"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _reconcile_in_progress(state: dict) -> list[str]:
    """Check in_progress units and reconcile against filesystem/git."""
    warnings = []
    runs_dir = Path(".shipwright/runs") / state["loop_id"]

    for unit in state["units"]:
        if unit["status"] != "in_progress":
            continue

        result_path = runs_dir / unit["id"] / "result.json"
        if result_path.exists():
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
                if result.get("status") == "complete":
                    unit["status"] = "complete"
                    unit["commit"] = result.get("commit")
                    unit["finished_at"] = _now_iso()
                    unit["result_path"] = str(result_path)
                    warnings.append(f"Reconciled {unit['id']}: found result.json with status=complete")
                    continue
            except (json.JSONDecodeError, OSError):
                pass

        # R2's lease heartbeat (lib.unit_lease) can populate `branch` on this
        # row from Step 1, well before any commit exists — once a row has
        # EVER been lease-touched, `branch`'s presence no longer implies
        # `cmd_record` reported back (the only pre-R2 writer of this field),
        # so the branch-has-commits guess below can never safely apply to it
        # again, live lease or since-expired: gating on staleness alone only
        # re-triggers the exact same false-complete bug once the lease
        # expires (doubt-reviewer, high — a resume happening AFTER the lease
        # window is the common case, not the exotic one). A never-touched row
        # (no lease fields at all — the only way `branch` could be set
        # pre-R2) still takes the original evidence-based path unchanged.
        if unit.get("lease_touched_at") is None and unit.get("branch"):
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--verify", f"refs/heads/{unit['branch']}"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0 and unit.get("head_sha"):
                    log_result = subprocess.run(
                        ["git", "log", "--oneline", f"{unit['head_sha']}..{unit['branch']}"],
                        capture_output=True, text=True, timeout=10,
                    )
                    if log_result.returncode == 0 and log_result.stdout.strip():
                        unit["status"] = "complete"
                        unit["finished_at"] = _now_iso()
                        warnings.append(f"Reconciled {unit['id']}: branch has commits since head_sha")
                        continue
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        unit["status"] = "pending"
        unit["attempt"] = unit.get("attempt", 0) + 1
        warnings.append(f"Reconciled {unit['id']}: reset to pending (attempt {unit['attempt']})")

    return warnings


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
        # Doubt-reviewer, medium: this read-modify-write previously took no
        # lock, unlike every other loop_state.json writer (cmd_next/
        # cmd_record/touch_unit_lease) — harmless while nothing else could be
        # writing concurrently, but R2's lease heartbeat now legitimately can
        # be (a live runner touching its own row while a resumed orchestrator
        # session inits). Same `loop.lock` as everyone else, so a concurrent
        # heartbeat is serialized rather than clobbered.
        with file_lock(state_path.parent / "loop.lock", timeout_seconds=30):
            existing = _load_state(state_path)
            in_progress = [u for u in existing.get("units", []) if u["status"] == "in_progress"]
            if in_progress:
                warnings = _reconcile_in_progress(existing)
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
        "loop_id": loop_id,
        "kind": args.kind,
        "root_session_id": args.root_session_id or os.environ.get("SHIPWRIGHT_ROOT_SESSION_ID", ""),
        "branch_strategy": args.branch_strategy,
        "created_at": _now_iso(),
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
                # kind == "sub_iterate"-gated guard (campaign-dag-scheduler R1):
                # a pending unit blocked on an unmerged `depends_on` edge is
                # skipped in favor of the next candidate, exactly as if it
                # weren't there — no new flag, no new exit code; `kind ==
                # "section"`'s contract (shipwright-build, no depends_on
                # concept) is untouched. R4's `cmd_next_batch` (loop_claim.py)
                # is the only place `--campaign-dir` and exit code 4 land.
                if kind == "sub_iterate" and not is_unit_ready(unit, units):
                    continue
                unit["status"] = "in_progress"
                unit["started_at"] = _now_iso()
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

        # External plan review (campaign-dag-scheduler R1, GLM finding 1):
        # a `pending` unit that is only BLOCKED (not actually finished) must
        # not read identically to genuine completion in the printed JSON —
        # exit code stays 2 unchanged (R1 adds no new exit code on `cmd_next`;
        # that is R4's `cmd_next_batch` job), but a blocked-pending unit is
        # now OBSERVABLE via additive fields, so a log reader — or a future
        # orchestrator step — is not blind to "campaign silently stalled".
        #
        # Every remaining `pending` unit here IS blocked, by construction —
        # not just "incidentally correct" (external code review, low): we
        # only reach this line after the FIFO loop above has already
        # returned for the first `pending` unit where `is_unit_ready` was
        # true, so any `pending` unit still in `units` failed that check.
        # If a future change adds an early-exit/cap to that loop, THIS
        # invariant is exactly what breaks — recompute from the guard's own
        # skip set at that point rather than re-deriving it here.
        blocked_pending = [u for u in units if u["status"] == "pending"] if kind == "sub_iterate" else []
        if blocked_pending:
            # Stage-2 code review, campaign-dag-scheduler R1 (high): the loop
            # is NOT actually finished here — one or more units are still
            # `pending`, blocked on an unmerged `depends_on` edge. Printing
            # "All units processed" was a factual lie the orchestrator's own
            # exit-2 -> Finalize branch (campaign-mode.md step 3) would act
            # on, finalizing a campaign that never built the blocked units.
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

    try:
        result = json.loads(result_str)
    except json.JSONDecodeError:
        runs_dir = Path(".shipwright/runs")
        state_peek = _load_state(state_path)
        loop_id = state_peek.get("loop_id", "")
        fallback_path = runs_dir / loop_id / args.unit / "result.json"
        if fallback_path.exists():
            try:
                result = json.loads(fallback_path.read_text(encoding="utf-8"))
                print(f"WARN: Task returned non-JSON, using fallback {fallback_path}", file=sys.stderr)
            except (json.JSONDecodeError, OSError):
                pass

        if not result:
            with file_lock(lock_path, timeout_seconds=30):
                state = _load_state(state_path)
                for unit in state["units"]:
                    if unit["id"] == args.unit:
                        unit["status"] = "failed"
                        unit["finished_at"] = _now_iso()
                        unit["failure_reason"] = f"Non-JSON result: {result_str[:500]}"
                        break
                _save_state(state_path, state)
            print(f"ERROR: Non-JSON result and no fallback for {args.unit}", file=sys.stderr)
            return 3

    errors = _validate_result(result, "")
    if errors:
        with file_lock(lock_path, timeout_seconds=30):
            state = _load_state(state_path)
            for unit in state["units"]:
                if unit["id"] == args.unit:
                    unit["status"] = "failed"
                    unit["finished_at"] = _now_iso()
                    unit["failure_reason"] = f"Contract violation: {'; '.join(errors)}"
                    break
            _save_state(state_path, state)
        print(f"ERROR: Contract violation: {errors}", file=sys.stderr)
        return 3

    with file_lock(lock_path, timeout_seconds=30):
        state = _load_state(state_path)
        for unit in state["units"]:
            if unit["id"] == args.unit:
                unit["status"] = result.get("status", "failed")
                unit["finished_at"] = _now_iso()
                unit["commit"] = result.get("commit")
                unit["branch"] = result.get("branch", unit.get("branch"))
                unit["failure_reason"] = result.get("error") or (result.get("reason") if result.get("status") != "complete" else None)  # escalated carries `reason`, not `error`; scoped so a complete unit never gains one

                runs_dir = Path(".shipwright/runs") / state["loop_id"] / unit["id"]
                runs_dir.mkdir(parents=True, exist_ok=True)
                (runs_dir / "result.json").write_text(
                    json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                unit["result_path"] = str(runs_dir / "result.json")

                handoff_dir = Path(".shipwright/planning/handoffs") / state["loop_id"]
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


def cmd_finalize(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    state = _load_state(state_path)

    completed = [u for u in state["units"] if u["status"] == "complete"]
    failed = [u for u in state["units"] if u["status"] == "failed"]
    escalated = [u for u in state["units"] if u["status"] == "escalated"]
    pending = [u for u in state["units"] if u["status"] == "pending"]

    handoff_dir = Path(".shipwright/planning/handoffs") / state["loop_id"]
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
