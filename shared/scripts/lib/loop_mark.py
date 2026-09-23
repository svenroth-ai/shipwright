"""Identity/token-checked state mutators for ``kind == "sub_iterate"``
campaigns — the "mark" half of R4's claim mechanics.

Campaign ``campaign-dag-scheduler`` R4
(``.shipwright/planning/iterate/2026-09-20-campaign-dag-scheduler-plan.md``
§ "R4 — concurrent state mechanics").
Split out of ``loop_claim.py`` (the "claim" half — ready-set computation and
atomic claim/release) rather than folded in: the sub-iterate spec's own AC
requires ``loop_claim.py`` to split before filing a bloat exception "purely
from feature count, not genuine cohesion" — five substantial CLI commands in
one file is exactly that. The split is genuinely cohesive, not arbitrary:
this module owns every mutation gated on an IDENTITY check (a fencing token,
or an audited operator override) rather than a SCHEDULING decision (which
unit is ready, how many to claim). ``loop_claim.py``'s ``main()`` still
dispatches all five commands from one CLI entry point — this is an internal
module boundary, not a second command surface.

Two commands:

- ``mark-running`` — the runner's own Step 1.0.5 ``claimed -> running``
  promotion (R5a).
- ``mark-merged`` — the ``merging -> merged`` write R5b's step 3g point 5
  calls with a verified merge-commit SHA.
- ``mark`` — the one audited operator override; may cross any edge.

Import convention: ``lib.``-qualified for ``loop_state``; ``branch_base``/
``file_lock`` stay bare-sibling-imported, matching every other module in
this package (never two module identities for one file).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:  # bare-sibling — see module docstring's import-convention note
    from branch_base import fresh_remote_default_ref
except ImportError:  # pragma: no cover - defensive, mirrors lib.loop_state
    fresh_remote_default_ref = None  # type: ignore[assignment]
from file_lock import LockTimeout, file_lock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.loop_state import (  # noqa: E402
    STATES,
    find_unit_row,
    is_legal_transition,
    is_valid_sha,
    now_iso,
    validate_attempt_token,
)

_MAX_TEXT_LEN = 500
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")


def _load_state(state_path: Path) -> dict:
    return json.loads(state_path.read_text(encoding="utf-8"))


def _save_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(state_path)


def _sanitize_text(name: str, value: str | None) -> str | None:
    """Length-capped, control-character-rejecting — the real surface is a
    markdown-table/shell-`export` rendering downstream, not the JSON file
    itself. Returns ``None`` unchanged (absent is legal for some fields)."""
    if value is None:
        return None
    if _CONTROL_CHAR_RE.search(value):
        raise ValueError(f"{name} contains a control character — rejected")
    if len(value) > _MAX_TEXT_LEN:
        raise ValueError(f"{name} exceeds {_MAX_TEXT_LEN} characters — rejected")
    return value


def _is_ancestor(commit: str, base: str, *, cwd: str | None = None) -> bool:
    try:
        r = subprocess.run(["git", "merge-base", "--is-ancestor", commit, base],
                            capture_output=True, text=True, timeout=15, cwd=cwd)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return r.returncode == 0


def _fencing_mutate(args: argparse.Namespace, *, from_states: tuple[str, ...], to_state: str,
                     extra: dict | None = None) -> int:
    """Shared body for `mark-running`/`mark-merged`: fencing-token-checked,
    edge-table-checked (never `forced`), single-writer, atomic. `extra` is
    merged into the unit row on success (e.g. `merged_commit`)."""
    state_path = Path(args.state)
    try:
        with file_lock(state_path.parent / "loop.lock", timeout_seconds=30):
            state = _load_state(state_path)
            unit = find_unit_row(state, args.unit)
            if unit is None:
                print(f"ERROR: unit {args.unit!r} not found", file=sys.stderr)
                return 1
            if not validate_attempt_token(unit, args.attempt_id):
                print(json.dumps({"marked": False, "status": "stale_attempt", "unit": args.unit}))
                return 5
            if unit["status"] not in from_states or not is_legal_transition(unit["status"], to_state):
                print(f"ERROR: illegal transition {unit['status']!r} -> {to_state!r} for unit {args.unit!r}",
                      file=sys.stderr)
                return 1
            unit["status"] = to_state
            unit[f"{to_state}_at"] = now_iso()
            if extra:
                unit.update(extra)
            _save_state(state_path, state)
            print(json.dumps({"marked": True, "unit": args.unit, "status": to_state}))
            return 0
    except LockTimeout as exc:
        print(json.dumps({"error": "lock_timeout", "detail": str(exc)}), file=sys.stderr)
        return 6


def cmd_mark_running(args: argparse.Namespace) -> int:
    """`claimed -> running` — the runner's own Step 1.0.5 promotion (R5a)."""
    return _fencing_mutate(args, from_states=("claimed",), to_state="running")


def cmd_mark_merged(args: argparse.Namespace) -> int:
    """`merging -> merged` — R5b's step 3g point 5, with a verified
    merge-commit SHA. Format-validated (strict 40-char hex) BEFORE any
    write, same as the fencing-token check; not re-verified as an ancestor
    of `origin/<default>` here — this command IS the authoritative producer
    of a real, trustworthy `merged_commit`, so re-verifying it against
    itself would be circular (`lib.loop_state.verify_merged_commit_ancestry`
    exists for the READER side: a migrated/historical row of uncertain
    provenance, which this fresh write is not).

    **What this command attests, precisely (external plan review, GLM +
    OpenAI, low/medium):** a well-formed 40-hex SHA, written under a valid
    fencing token, for a unit legally in `merging`. It does NOT itself
    attest that the SHA is the merge of THIS unit's own PR — that identity
    check is R5b's step 3g caller's job, performed once, before it ever
    calls this command with the SHA GitHub's own merge API just returned.
    A future caller must not reuse this command as an identity proof.
    """
    if not is_valid_sha(args.merged_commit):
        print(f"ERROR: --merged-commit {args.merged_commit!r} is not a 40-char hex SHA", file=sys.stderr)
        return 1
    return _fencing_mutate(args, from_states=("merging",), to_state="merged",
                            extra={"merged_commit": args.merged_commit})


def cmd_mark(args: argparse.Namespace) -> int:
    """The one audited operator override — may cross ANY edge (`forced`)."""
    if args.status not in STATES:
        print(f"ERROR: unknown status {args.status!r}", file=sys.stderr)
        return 1
    try:
        reason = _sanitize_text("--reason", args.reason)
        operator = _sanitize_text("--operator", args.operator)
        reason_code = _sanitize_text("--reason-code", args.reason_code)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.status == "merged" and (not args.merged_commit or not is_valid_sha(args.merged_commit)):
        print("ERROR: --status merged requires a valid --merged-commit (40-char hex SHA)", file=sys.stderr)
        return 1

    state_path = Path(args.state)
    try:
        with file_lock(state_path.parent / "loop.lock", timeout_seconds=30):
            state = _load_state(state_path)
            unit = find_unit_row(state, args.unit)
            if unit is None:
                print(f"ERROR: unit {args.unit!r} not found", file=sys.stderr)
                return 1
            current = unit["status"]
            if current in ("running", "merging") and not (args.force and args.confirm_no_task_running):
                print(f"ERROR: unit {args.unit!r} is {current!r} — mark requires --force and "
                      "--confirm-no-task-running to confirm no Task is running against its worktree",
                      file=sys.stderr)
                return 1
            if not is_legal_transition(current, args.status, forced=True):
                print(f"ERROR: {current!r} / {args.status!r} is not a real state pair", file=sys.stderr)
                return 1

            if args.status == "merged":
                # `cmd_mark`'s own operator path re-verifies ancestry with a
                # FRESH fetch — unlike `cmd_mark_merged`'s routine call, an
                # operator override may be acting on stale/hand-typed
                # information, so it must never trust the SHA blindly.
                # `--campaign-worktree` is REQUIRED here (external code
                # review, GLM, medium): this is the one command most likely
                # invoked by a human from an arbitrary directory, and a
                # `git fetch`/ancestry check against the wrong repo's origin
                # is silently meaningless — it must never fall back to
                # whatever the process cwd happens to be.
                if not args.campaign_worktree:
                    print("ERROR: --status merged requires --campaign-worktree (the repo the fresh "
                          "fetch + ancestry check must run against) — refusing to guess the process cwd",
                          file=sys.stderr)
                    return 1
                try:
                    subprocess.run(["git", "fetch", "origin"], capture_output=True, text=True,
                                    timeout=60, cwd=args.campaign_worktree)
                    default_ref = fresh_remote_default_ref(cwd=args.campaign_worktree) \
                        if fresh_remote_default_ref else None
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    default_ref = None
                if not default_ref or not _is_ancestor(args.merged_commit, default_ref, cwd=args.campaign_worktree):
                    print(f"ERROR: --merged-commit {args.merged_commit!r} is not a verified ancestor "
                          "of the current default branch", file=sys.stderr)
                    return 1
                unit["merged_commit"] = args.merged_commit

            unit["status"] = args.status
            if args.status == "held" and not reason_code:
                reason_code = "operator_mark"
            if reason_code:
                unit["reason_code"] = reason_code
            audit = {"at": now_iso(), "from": current, "to": args.status, "reason": reason, "operator": operator}
            unit.setdefault("mark_audit", []).append(audit)
            _save_state(state_path, state)
            print(json.dumps({"marked": True, "unit": args.unit, "status": args.status, "audit": audit}))
            return 0
    except LockTimeout as exc:
        print(json.dumps({"error": "lock_timeout", "detail": str(exc)}), file=sys.stderr)
        return 6
