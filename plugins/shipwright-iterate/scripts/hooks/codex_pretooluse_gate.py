#!/usr/bin/env python3
"""``PreToolUse`` hook: gates a Codex-driven iterate session's first eligible
tool call against the activation record (R2 — AC1a).

Codex-only; a documented no-op under Claude Code (``is_codex_runtime()`` is
False for an ordinary Claude plugin-cache root — ``lib.codex_runtime``).

Fail-open, matching R0's Contract verbatim: no record, or ``armed: false``
(no grammar match on the session's first prompt) -> allow, always, no
exception. Scope: the local function-tool path only -- Codex's own hosted
tools (e.g. ``WebSearch``) bypass ``PreToolUse`` entirely, a Codex-side fact
this hook cannot change and does not claim to cover.

``armed: true`` -> the session's FIRST eligible ``PreToolUse`` call (any
tool, any class) is the one this hook ever evaluates: ``consume()``
(Step 4) is itself the durable "first-call-settled" flag, via the same
exclusive-create-once primitive the activation record already uses for its
``.consumed`` sidecar. ``consume()`` winning (returns a record) means THIS
call is the first eligible one -- decide allow/deny from the tool payload.
``consume()`` losing (returns ``None``) covers both "already settled by an
earlier call" and every fail-open case ``read()`` already covers (absent/
corrupt/expired/cwd-mismatched) -- deliberately indistinguishable to this
hook, since both mean "never deny this call".

Allow/deny matrix (armed-and-unsettled only): a ``Bash``-class call whose
command invokes ``setup_iterate_worktree.py`` as its ONLY semantically
active step (a single segment, or a ``cd``-prefixed sequential chain ending
in the setup call -- see ``codex_pretooluse_matcher._bash_command_matches_setup``)
-> allow. Anything else -- a non-matching ``Bash`` call, a compound command
that merely CONTAINS a matching segment alongside other commands, any
``||``/``|`` command, or any other/unrecognized tool class -- -> deny.
Unknown classes deny by default while armed-and-unsettled (external review,
openai medium-4): a shell-only matcher would leave every non-``Bash`` local
tool free to bypass the gate entirely. Full per-class fixture coverage
beyond a synthetic "unknown class" case is deferred to this run's end-of-run
live probe (mini-plan Step 2/10) -- Codex's complete locally-hook-visible
tool-name inventory beyond ``Bash``/``Agent`` is not yet captured."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from codex_pretooluse_matcher import decide as _decide


def _find_shared_scripts() -> Path:
    """Locate shared/scripts/ by walking up — robust to plugin-layout depth
    (mirrors ``codex_activation_mint.py``'s identical helper)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "shared" / "scripts"
        if candidate.is_dir():
            return candidate
    return here.parents[4] / "shared" / "scripts"  # historical fallback


_SHARED_SCRIPTS = _find_shared_scripts()
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.codex_activation_record import consume, normalize_cwd  # noqa: E402
from lib.codex_runtime import is_codex_runtime  # noqa: E402
from lib.project_root import is_shipwright_project  # noqa: E402


def _setup_command_hint() -> str:
    """The exact, copy-pasteable setup command (review finding, glm medium:
    tell the model what to run, don't just say no) — built from this hook's
    own resolved ``_SHARED_SCRIPTS`` path, not a ``{shared_root}``-style
    template placeholder the model can't act on directly. ``<slug>``/
    ``<run-id>`` remain genuine placeholders — an operator/session choice
    this hook cannot know."""
    script = _SHARED_SCRIPTS / "tools" / "setup_iterate_worktree.py"
    return f'uv run "{script}" --project-root . --slug <slug> --run-id <run-id>'


def _resolve_project_root(cwd: str) -> str:
    """Anchor on the payload's own per-turn ``cwd`` — never the hook
    subprocess's ambient OS cwd (same HIGH-severity lesson as the mint
    hook's own resolver: recomputing this from ambient state can silently
    disagree with where Codex says this turn actually ran, splitting one
    session's ``consume()`` key across two storage paths). Resolves through
    the SAME git main-repo-root canonicalization
    ``codex_activation_record.normalize_cwd`` already applies, so the two
    can never disagree."""
    return normalize_cwd(cwd)


def _unarmed_visibility_warning() -> dict:
    """R0-named gap 2 (iterate-spec.md's ``Unarmed-launch visibility`` AC):
    the fail-open default must never be silent. This is the "first ungated
    call" alternative the AC names (a ``SessionStart`` hook cannot know the
    armed/unarmed outcome yet -- mint happens on the session's first
    ``UserPromptSubmit``, which runs AFTER ``SessionStart``). Reuses the
    exact ``hookSpecificOutput`` shape already live-confirmed visible for a
    deny (the live probe showed a deny's ``permissionDecisionReason`` text
    rendered to the operator) -- an ``allow`` decision with a reason is the
    most conservative extension of already-proven machinery, not new,
    unverified surface. Codex's exact rendering of an ``allow`` reason is
    unconfirmed by live evidence (unlike the deny path); documented here as
    an assumption, not a proven fact."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": (
                "No Shipwright activation envelope was recognized in this "
                "session's first prompt, so this session is proceeding "
                "unarmed -- Shipwright's mandatory iterate setup step will "
                "NOT be enforced for the rest of this session. If this is "
                "meant to be a Shipwright-driven iterate, start a new "
                "session with the activation envelope as the first message."
            ),
        }
    }


def handle_payload(payload: dict) -> dict | None:
    """Decide this ``PreToolUse`` call from a Codex payload. Returns the
    hook's JSON response dict -- either a denial
    (``hookSpecificOutput.permissionDecision: "deny"``) or a visible,
    non-blocking ``"allow"`` warning for the unarmed case (see
    ``_unarmed_visibility_warning``) -- or ``None`` to allow / take no
    position silently. Never raises. Every OTHER failure path (not Codex,
    no/invalid ``session_id``/``cwd``, fail-open record absent/corrupt/
    expired/cwd-mismatched, already-settled) resolves to silent ``None``
    (allow), the same as the R0 Contract's explicit default -- only the
    genuinely-first call of an unarmed session gets the visible warning,
    exactly once per session (``consume()``'s own exclusivity).

    **Accepted residual risk — same-turn concurrent dispatch (local
    PR-review preflight, block; adjudicated, not fixed).** ``consume()``'s
    exclusive-create decides WHO the "first call" is atomically and
    correctly; what it does not do is evaluate a LOSING call's own
    ``tool_input`` before allowing it, because under this gate's documented
    one-shot design (see the R2 ADR's Goal section) every call after the
    first is unevaluated by construction -- "a denied first call followed
    by a different second call sails through unevaluated" was the explicit,
    externally-reviewed and architecture-reviewed tradeoff, not an
    oversight. If Codex ever dispatches two `PreToolUse` calls for the SAME
    turn concurrently, the race's loser is that "second call" a few
    microseconds early rather than a few seconds late -- the same accepted
    gap wearing a different clock, not a new bypass class. This gate's
    threat model is cooperative enforcement (nudging a cooperative session
    toward the required setup step), not defending against a session
    actively trying to smuggle a second call past it -- consistent with the
    matcher's own accepted basename-only-match residual risk. Serializing
    evaluation across concurrently dispatched calls would need an
    interprocess lock this fail-open-by-design mechanism does not otherwise
    need; not undertaken here on that basis. Whether Codex's own tool-call
    dispatch is ever actually concurrent within one turn is unconfirmed --
    the deferred payload-capture probe (iterate-spec.md's own "Live proof —
    payload capture" AC) is where that would be observed; R2b inherits it."""
    if not is_codex_runtime():
        return None

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        return None

    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd.strip():
        return None

    project_root = _resolve_project_root(cwd)
    if not is_shipwright_project(Path(project_root)):
        return None

    record = consume(project_root, session_id, cwd=cwd)
    if record is None:
        return None  # fail-open, or already settled by an earlier call
    if not record.armed:
        # This IS the session's genuinely-first eligible call (consume()'s
        # own exclusive-create won the claim) but no envelope was recognized
        # on the first prompt -- surface it once, visibly, never deny.
        return _unarmed_visibility_warning()

    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if _decide(tool_name, tool_input):
        return None

    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "This Codex-driven iterate session has not run the required "
                f"worktree setup step yet. Run: {_setup_command_hint()}"
            ),
        }
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return 0

    if not isinstance(payload, dict):
        return 0

    try:
        decision = handle_payload(payload)
    except Exception:  # noqa: BLE001 — a hook must never crash the turn
        return 0

    if decision is not None:
        print(json.dumps(decision))
    return 0


if __name__ == "__main__":
    sys.exit(main())
