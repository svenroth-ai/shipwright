"""Stop-guard for an ``--autonomous`` iterate run.

An autonomous iterate is only done when its PR is MERGED and the checks are
green (F11 delivery, then F12). ``deliver_pr.py`` retires the run pointer at
exactly that moment, so *a live run pointer for this session* is the code-level
"run is still open" signal. A PR merged out of band (auto-merge, by hand) leaves
the pointer live, so one rate-limited ``gh pr list`` check on a would-be block
covers that case.

The guard blocks a Stop (``{"decision": "block", "reason": ...}``) while that
pointer is live, unless one of the legitimate exits holds:

* the latest iterate invocation in the session is not ``--autonomous`` (or is a
  ``--campaign`` parent, whose sub-runs never open a PR of their own),
* a hard blocker was recorded (``record_hard_blocker.py``),
* the operator set ``SHIPWRIGHT_ITERATE_STOP_GUARD=0``,
* a background task the session launched (reviewer, shell) is unfinished: its
  completion notice wakes the agent again, so waiting is the job (nothing is counted),
* the run's PR was merged after the run started (``delivered``;
  ``SHIPWRIGHT_ITERATE_STOP_GUARD_GH=0`` skips the ``gh`` call),
* the bounded counters ran out: ``MAX_FUTILE_BLOCKS`` consecutive blocks with no
  tool call in between (the agent answered the block with prose again, e.g.
  while it waits for a background task), or ``MAX_TOTAL_BLOCKS`` per run. These
  replace ``stop_hook_active``, which is true on every Stop after the first
  block and would allow a premature stop after a single nudge.

Autonomy is read from the transcript (the latest iterate invocation) rather
than from a flag in the run pointer: the flag would depend on the agent passing
it to ``setup_iterate_worktree.py`` -- the agent-followed step whose omission is
the failure being fixed. Everything here is best-effort and fail-open: a guard
that crashes must never trap a session in a Stop loop.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from lib.events_log import resolve_events_path
from lib.iterate_stop_guard_background import waiting as background_waiting
from lib.iterate_stop_guard_transcript import (  # noqa: F401 - re-exported API
    MAX_POINTER_AGE_HOURS,
    Scan,
    live_pointer,
    parse_flags,
    scan_transcript,
)

MAX_FUTILE_BLOCKS = 3
MAX_TOTAL_BLOCKS = 40
MERGED_RECHECK_SECONDS = 120
HARD_BLOCKER_CODES = (
    "non-converging-delivery",
    "admin-merge-required",
    "operator-only-decision",
    "external-outage",
    "credential-missing",
    "abandoned-by-operator",
)
_STATE_SUBDIR = (".shipwright", "runtime", "iterate-stop-guard")
def _safe(text: str, limit: int = 64) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", text)[:limit]


def _state_path(main_root: Path, run_id: str) -> Path:
    return main_root.joinpath(*_STATE_SUBDIR) / f"{_safe(run_id, 120) or 'unknown'}.json"


def read_state(main_root: Path, run_id: str, strict: bool = False) -> dict:
    """The run's guard state. Missing file = initial state. Unreadable or
    malformed content is an internal error: ``strict`` propagates it so the hook
    fails open instead of blocking on (and silently resetting) corrupt state."""
    try:
        data = json.loads(_state_path(main_root, run_id).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        if strict:
            raise
        return {}
    return data if isinstance(data, dict) else {}


def write_state(main_root: Path, run_id: str, state: dict) -> None:
    path = _state_path(main_root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}-{uuid.uuid4().hex[:8]}.tmp")
    try:
        tmp.write_text(json.dumps(state), encoding="utf-8")
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def record_hard_blocker(main_root: Path, run_id: str, reason_code: str, detail: str) -> dict:
    """Persist the one legitimate reason an autonomous run may stop early."""
    if reason_code not in HARD_BLOCKER_CODES:
        raise ValueError(f"reason_code must be one of {HARD_BLOCKER_CODES}")
    state = read_state(main_root, run_id)
    state["blocker"] = {"reason_code": reason_code, "detail": detail.strip()[:500]}
    write_state(main_root, run_id, state)
    return state


def clear_hard_blocker(main_root: Path, run_id: str) -> bool:
    """Re-arm the guard once a recorded blocker is resolved. True if one was set."""
    state = read_state(main_root, run_id)
    had = state.pop("blocker", None) is not None
    if had:
        write_state(main_root, run_id, state)
    return had


def _git(worktree: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", str(worktree), *args], capture_output=True,
                             text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def next_phase_hint(worktree: Path, run_id: str, branch: str) -> str:
    """Name the first unfinished phase from local artifacts only (never raises)."""
    try:
        reviews = {}
        try:
            rec = json.loads((worktree / ".shipwright" / "planning" / "iterate" / run_id
                              / "reviews.json").read_text(encoding="utf-8"))
            reviews = rec.get("reviews") or {}
        except (OSError, ValueError):
            pass
        if (reviews.get("self") or {}).get("status") != "completed":
            return "Build and Step 7 self-review are not recorded yet: finish the TDD build, then Step 7."
        pending = sorted(_safe(k, 24) for k, v in reviews.items()
                         if (v or {}).get("status") == "pending")
        if pending:
            return ("Review cascade (Step 8) is open, pending rows: " + ", ".join(pending)
                    + ". Spawn what is missing (spec-reviewer -> code-reviewer -> doubt-reviewer, external "
                    "review); a reviewer already running in the background is waited for, not re-spawned.")
        try:
            events = resolve_events_path(worktree).read_text(encoding="utf-8", errors="replace")
        except OSError:
            events = ""
        if not any(run_id in ln and "work_completed" in ln for ln in events.splitlines()):
            return "Finalization F0 -> F5c has not recorded work_completed yet: run F0, F0.5, F1-F5c."
        base = _git(worktree, "rev-parse", "--abbrev-ref", "origin/HEAD") or "origin/main"
        if _git(worktree, "rev-parse", "--verify", "--quiet", base) and not _git(
                worktree, "log", f"{base}..HEAD", "--oneline", "--fixed-strings", f"--grep={run_id}"):
            return "F6 commit is missing: stage the explicit path list and commit."
        if branch and not _git(worktree, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}"):
            return "F11 push + gh pr create looks missing: run `gh pr list --head <branch> --state all` first and never open a second PR for a merged branch."
        return ("F11 delivery: run deliver_pr.py until the PR is MERGED with green checks, then F12 "
                "(a delivery or CI watch already running in the background is waited for).")
    except Exception:  # noqa: BLE001 - a hint must never break the guard
        return "Continue with the next unfinished phase of the iterate lifecycle."


def _gh_prs(worktree: Path, branch: str) -> list[dict]:
    """Every PR headed by ``branch`` as ``{"state", "mergedAt"}`` (``[]`` on any
    failure, which counts as not merged). ``SHIPWRIGHT_ITERATE_STOP_GUARD_GH=0`` skips the call."""
    if os.environ.get("SHIPWRIGHT_ITERATE_STOP_GUARD_GH") == "0":
        return []
    try:
        out = subprocess.run(["gh", "pr", "list", "--head", branch, "--state", "all",
                              "--json", "state,mergedAt"], cwd=str(worktree),
                             capture_output=True, text=True, timeout=8, check=False)
        data = json.loads(out.stdout) if out.returncode == 0 else []
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    return [p for p in data if isinstance(p, dict)] if isinstance(data, list) else []


def _utc(text: object) -> datetime | None:
    try:
        when = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _merged_out_of_band(worktree: Path, branch: str, run_started: str, state: dict) -> bool:
    """True when THIS run's PR is already MERGED although its pointer is still live
    (merged by auto-merge or by hand, so ``deliver_pr.py`` never retired it). One
    ``gh`` call, re-asked at most every ``MERGED_RECHECK_SECONDS`` and only on a Stop
    that would otherwise block. "This run's": a branch name is reused by later runs
    with the same slug, so a PR counts only when it merged after the run started; an
    unknown start, a ``gh`` failure or an OPEN sibling PR all count as "not merged"
    (never a premature release)."""
    started = _utc(run_started)
    if not branch or started is None:
        return False
    now = time.time()
    if now - float(state.get("merged_checked_at", 0)) < MERGED_RECHECK_SECONDS:
        return False
    state["merged_checked_at"] = now
    prs = _gh_prs(worktree, branch)
    if any(p.get("state") == "OPEN" for p in prs):
        return False
    return any(p.get("state") == "MERGED" and (_utc(p.get("mergedAt")) or started) > started
               for p in prs)


def _write_keeping_blocker(main_root: Path, run_id: str, state: dict) -> None:
    """Persist ``state``; a blocker recorded since it was read (``gh`` can take 8 s) survives."""
    fresh = read_state(main_root, run_id).get("blocker")
    write_state(main_root, run_id, {**state, **({"blocker": fresh} if fresh else {})})


def decide(*, main_root: Path, run_id: str, worktree: Path, branch: str,
           autonomous: bool, tool_count: int, scan: dict | None = None,
           run_started: str = "") -> str | None:
    """Return the block reason, or ``None`` to let the Stop through. Mutates state."""
    if os.environ.get("SHIPWRIGHT_ITERATE_STOP_GUARD") == "0":
        return None
    state = read_state(main_root, run_id, strict=True)  # corrupt state -> hook fails open
    state = {**state, **(scan or {})}  # persist the scan on EVERY Stop with a live pointer
    last_tools = -1 if (scan or {}).get("reset") else int(state.get("tool_count", -1))
    state.pop("reset", None)
    if not autonomous:
        _write_keeping_blocker(main_root, run_id, state)
        return None
    if state.get("blocker"):
        write_state(main_root, run_id, state)
        return None
    bg = state.get("bg")
    if isinstance(bg, dict) and background_waiting(bg):
        _write_keeping_blocker(main_root, run_id, state)  # its notice wakes the agent: waiting is the job
        print(f"[iterate_stop_guard] stop allowed for {_safe(run_id)}: waiting on {len(bg)} background task(s)",
              file=sys.stderr)
        return None
    if state.get("delivered") or _merged_out_of_band(worktree, branch, run_started, state):
        _write_keeping_blocker(main_root, run_id, {**state, "delivered": True})
        print(f"[iterate_stop_guard] stop allowed for {_safe(run_id)}: its PR is already MERGED",
              file=sys.stderr)
        return None
    total, futile = int(state.get("blocks", 0)), int(state.get("futile", 0))
    release = None
    if total >= MAX_TOTAL_BLOCKS:
        release = f"{MAX_TOTAL_BLOCKS} blocks used up"
    elif tool_count > last_tools:
        futile = 0  # the agent did real work since the last block
    else:
        futile += 1
        if futile >= MAX_FUTILE_BLOCKS:
            release = f"{MAX_FUTILE_BLOCKS} consecutive blocks without a tool call"
    if release:
        _write_keeping_blocker(main_root, run_id, {**state, "futile": futile})
        print(f"[iterate_stop_guard] stop allowed for {_safe(run_id)}: {release}", file=sys.stderr)
        return None
    _write_keeping_blocker(main_root, run_id, {**state, "blocks": total + 1, "futile": futile,
                                               "tool_count": tool_count})
    hint = next_phase_hint(worktree, run_id, branch)
    return (
        f"Autonomous iterate {_safe(run_id)} is not finished: its PR is not MERGED with green checks "
        f"(F11 delivery + F12). A summary or a question now is a contract violation. Next: {hint} "
        "Continue without asking. If a named background task (F0 suite, reviewer, delivery watch) is still running, end the turn WITHOUT further tool calls and resume on its notification. If the operator's latest message explicitly told you to stop or "
        "pause, or you are truly blocked (delivery exit 8, admin merge needed, operator-only decision, "
        "run abandoned), first run "
        f'`uv run "{{shared_root}}/scripts/tools/record_hard_blocker.py" --run-id {_safe(run_id)} '
        f'--reason-code <{"|".join(HARD_BLOCKER_CODES)}> --detail "<why>"`, then stop; the F12 '
        "summary names the blocker. Operator kill switch: SHIPWRIGHT_ITERATE_STOP_GUARD=0."
    )
