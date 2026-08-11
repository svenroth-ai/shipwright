#!/usr/bin/env python3
"""PostToolUse hook: best-effort auto-capture of the 'implementation' span.

Root cause (trg-e6d1cc5e, follow-up to TC5.1 / PR #617): SKILL.md's
``start implementation`` / ``end implementation`` calls at the Step 6/7
boundary are agent-prose only — an inline arrow-note with no code-enforced
writer — and in practice almost never fire (measured: the top-level
``implementation`` span was present in only 1 of 32 runs since 2026-08-07,
and that one run was TC5.1's own build). Unlike the durable ``scope`` mark
(now written by ``setup_iterate_worktree.py`` itself), there is no single
deterministic process boundary at "Step 6 begins" / "Step 7 begins" to
relocate the call into. This hook backstops both edges from signals that
ARE deterministic:

- start: the first Write/Edit this run that lands outside ``.shipwright/``
  (source/tests). Every pre-Build artifact — spec, mini-plan, ADR drops,
  reviews.json — lives under ``.shipwright/``, so a write outside it is a
  reliable proxy for "Build has begun".
- end (+ start review/self_review): the first Bash call this run whose
  ``record_review_pass.py record`` invocation names ``--review-type self``
  and ``--status completed`` — self-review is unconditionally mandatory
  (Override Classes: "Never skippable"), so it is the one Step-7-entry
  signal every run reliably makes.

Best-effort, matching ``iterate_timing.py``'s own semantics: never raises,
never blocks the tool call, and first-wins (skips once already recorded) so
a compliant agent's own explicit calls are not duplicated. This hook's
matcher (``Write|Edit|Bash``) fires for the plugin's WHOLE session lifetime,
not merely during an active iterate, so several cheap-cost guards — split
into the sibling ``_mark_implementation_span_state`` module — keep it a
negligible tax on every other tool call (code review round 2 + 3, doubt
review round 3):

- a short lock-acquire timeout so sidecar contention degrades to a skipped
  mark rather than a multi-second stall;
- a git-free negative fast path for the dominant "no active iterate at all"
  case (an ordinary checkout with no run pointer for any session) — skips
  the git-backed resolvers entirely rather than paying their cost forever
  on every Bash call in every non-iterate session;
- a per-session resolved-pointer cache (checked before falling back to
  ``pointer_run_id``/``pointer_worktree_root``) for the "an iterate IS
  active" case, re-validated on every read (session_id equality, worktree
  liveness) rather than trusted blindly — narrows *when* the authoritative,
  ownership-checked resolvers run, never *what* they check;
- a per-run "done" sentinel (checked before any of the above) for the calls
  AFTER both edges are captured — most of a run's remaining Review/Test/
  Finalize phases. Written ONLY once the guard-critical writes (``start
  review``/``start self_review``) are BOTH confirmed to have landed: a
  transient lock timeout on either one alone must still leave the OTHER
  retryable on the next matching Bash call, so a partial success cannot
  silently strand one edge unwritten forever (doubt review round 3).

Both the resolved-pointer cache and the done sentinel are keyed off a
git-free ``repo_root_hint`` (walks up from cwd for a directory owning both
``.git`` and ``.shipwright``) rather than raw ``cwd``, so a cwd drift within
one checkout (e.g. `cd plugins/x` mid-session) still hits the same cache
files instead of missing it and paying full resolution again.
"""
from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))
_SHARED_SCRIPTS = _HOOKS_DIR.parent
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import _mark_implementation_span_state as state  # noqa: E402
from lib.file_lock import LockTimeout  # noqa: E402
from lib.iterate_timings import record_end, record_start  # noqa: E402
from lib.iterate_timings_normalize import read_raw_events  # noqa: E402
from lib.phase_quality._run_id import pointer_run_id, pointer_worktree_root  # noqa: E402

_SKIP_DIR_PREFIXES = (".shipwright", ".git", ".worktrees")
_LOCK_TIMEOUT_SECONDS = 2.0


def _read_payload() -> dict:
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return {}
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _session_id(payload: dict) -> str:
    sid = payload.get("session_id")
    if isinstance(sid, str) and sid.strip():
        return sid.strip()
    return (os.environ.get("SHIPWRIGHT_SESSION_ID") or "").strip() or "unknown"


def _has_event(events: list[dict], *, event: str, name: str) -> bool:
    return any(e.get("event") == event and e.get("name") == name for e in events)


def _matches_self_review_completion(command: str) -> bool:
    """True iff ``command`` is a ``record_review_pass.py record`` call naming
    ``--review-type self`` and ``--status completed`` by VALUE, not by loose
    substring (code review, trg-e6d1cc5e round 2): a prior substring check on
    raw ``"self"``/``"completed"`` false-positived on e.g. ``--status not_run
    --disposition "skipped, completed in prior session"``."""
    if "record_review_pass.py" not in command:
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False

    def _value_after(flag: str) -> str | None:
        # Both `--flag value` and `--flag=value` forms (argparse accepts
        # either; shlex leaves the latter as one token) — code review round 3.
        prefix = flag + "="
        for i, tok in enumerate(tokens):
            if tok == flag and i + 1 < len(tokens):
                return tokens[i + 1]
            if tok.startswith(prefix):
                return tok[len(prefix):]
        return None

    return (_value_after("--review-type") == "self"
            and _value_after("--status") == "completed")


def _start(worktree_root: Path, run_id: str, *, name: str, parent: str | None) -> bool:
    try:
        record_start(worktree_root, run_id, name=name, parent=parent,
                     timeout_seconds=_LOCK_TIMEOUT_SECONDS)
        return True
    except LockTimeout:
        return False


def _end(worktree_root: Path, run_id: str, *, name: str, parent: str | None) -> bool:
    try:
        record_end(worktree_root, run_id, name=name, parent=parent, outcome="completed",
                   timeout_seconds=_LOCK_TIMEOUT_SECONDS)
        return True
    except LockTimeout:
        return False


def _handle_write_edit(worktree_root: Path, run_id: str, file_path: str,
                        events: list[dict]) -> None:
    if _has_event(events, event="start", name="implementation"):
        return
    try:
        rel = Path(file_path).resolve().relative_to(worktree_root.resolve())
    except ValueError:
        return
    if rel.parts and rel.parts[0] in _SKIP_DIR_PREFIXES:
        return
    _start(worktree_root, run_id, name="implementation", parent=None)


def _handle_bash(worktree_root: Path, run_id: str, command: str,
                  events: list[dict]) -> None:
    if not _matches_self_review_completion(command):
        return
    review_started = _has_event(events, event="start", name="review")
    self_review_started = _has_event(events, event="start", name="self_review")
    if review_started and self_review_started:
        # First-wins: both edges already recorded — a retried/repeated
        # matching Bash call (e.g. a resumed run re-invoking
        # record_review_pass.py) must not re-open either.
        return
    if (_has_event(events, event="start", name="implementation")
            and not _has_event(events, event="end", name="implementation")):
        # Best-effort: a failure here does not block marking done below — a
        # missed `end implementation` loses one span boundary, whereas
        # blocking on it would leave `review`/`self_review` unwritten forever
        # once a later retry hits the (still-unset) guard's early return.
        _end(worktree_root, run_id, name="implementation", parent=None)
    # Retry whichever edge is still missing rather than an all-or-nothing
    # pair (doubt-review round 3): gating the guard above on `review` alone
    # meant a LockTimeout that hit `self_review` specifically while `review`
    # itself succeeded left `self_review` permanently unwritten — the guard
    # saw `review` present on the next matching call and returned before
    # ever retrying `self_review`.
    review_ok = review_started or _start(worktree_root, run_id, name="review", parent=None)
    self_review_ok = (self_review_started
                       or _start(worktree_root, run_id, name="self_review", parent="review"))
    # Only durable once both edges the guard above depends on are actually
    # present (code review round 3): marking done after either is still
    # missing would permanently suppress the retry that same guard would
    # otherwise allow on the next matching Bash call.
    if review_ok and self_review_ok:
        state.mark_done(worktree_root, run_id)


def main() -> int:
    payload = _read_payload()
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if tool_name not in ("Write", "Edit", "Bash") or not isinstance(tool_input, dict):
        return 0
    cwd = Path.cwd()
    root_hint = state.repo_root_hint(cwd)
    # Cheap short-circuit (one stat + one glob, no git shellout) for the
    # majority of calls that happen after both edges are already captured.
    if state.has_any_done_marker(root_hint):
        return 0
    # Cheap negative fast path: no active iterate anywhere, so skip the
    # git-backed resolvers entirely rather than paying their cost on every
    # Write/Edit/Bash call for the rest of this non-iterate session.
    if state.no_active_iterate_fast_check(root_hint):
        return 0
    session_id = _session_id(payload)
    cached = state.read_resolved_cache(root_hint, session_id)
    if cached is not None:
        run_id, worktree_root = cached
    else:
        run_id = pointer_run_id(cwd, session_id)
        worktree_root = pointer_worktree_root(cwd, session_id)
        if not run_id or worktree_root is None:
            return 0
        state.write_resolved_cache(root_hint, session_id, run_id, worktree_root)
    if state.has_done_marker(worktree_root, run_id):
        return 0
    events = read_raw_events(worktree_root, run_id)
    if tool_name in ("Write", "Edit"):
        file_path = tool_input.get("file_path")
        if isinstance(file_path, str) and file_path:
            _handle_write_edit(worktree_root, run_id, file_path, events)
    elif tool_name == "Bash":
        command = tool_input.get("command")
        if isinstance(command, str) and command:
            _handle_bash(worktree_root, run_id, command, events)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 -- best-effort: never break the tool flow
        sys.exit(0)
