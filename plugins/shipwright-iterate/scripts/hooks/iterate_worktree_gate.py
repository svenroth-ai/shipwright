#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Claude Code hook: no iterate work outside a worktree.

The iterate skill's B1a step ("every iterate runs in its own worktree") is
prose, and a model can skip prose -- recent models do, and start editing the
main checkout. This hook turns the step into a gate. It is the Claude-side
counterpart of the Codex pair ``codex_activation_mint.py`` +
``codex_pretooluse_gate.py`` (those are Codex-only; this one is a documented
no-op under Codex, so the two never double-fire).

Two events, one script (``hook_event_name`` picks the branch):

* **Arm** -- ``UserPromptSubmit`` with a ``/shipwright-iterate`` prompt, or
  ``PreToolUse`` on the ``Skill`` tool invoking ``shipwright-iterate``. Writes
  a per-session marker under ``.shipwright/runtime/iterate-worktree-gate/``
  (gitignored by the canon ``/.shipwright/*`` rule). Arming through the Skill
  tool matters: ``suggest_iterate.py`` only *suggests* the skill, so most
  iterates start with the model calling it, not the user typing the command.
* **Enforce** -- ``PreToolUse`` on every call of an armed session that is not
  yet isolated. Denied: ``Write``/``Edit``/``MultiEdit``/``NotebookEdit`` aimed
  at the main checkout, and any shell command outside the allowlist in
  ``iterate_worktree_gate_policy``. Everything else (reads, ``Skill``,
  ``Agent``, MCP tools, writes outside the repo such as memory files) passes.

"Isolated" is checked against live state on every call, not a one-shot flag
(the Codex gate settles after the first call because Codex cannot be asked
again; Claude Code can deny repeatedly): the session's cwd is inside a linked
worktree, or its run pointer (``.shipwright/iterate_active/<session>.json``,
written by ``setup_iterate_worktree.py``) names a genuine one. **The first time
the session is seen isolated the marker is released for good**: after the PR
merges and the worktree is removed, the same session is back in the main
checkout and must be free to ``git pull``, sync the plugin cache or start
other work. A new ``/shipwright-iterate`` re-arms it.

Cost: a tool call of a never-armed session finds no marker by walking up from
its cwd -- no git process, no heavy import -- and returns at once.

Fail-open throughout, as with the Codex gate: any error, a non-Shipwright
project, a stale marker (24 h) or ``SHIPWRIGHT_ITERATE_WORKTREE_GATE=off``
means allow. Threat model: a forgetful cooperative model, not an adversary."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from iterate_worktree_gate_policy import shell_is_preflight_safe
from iterate_worktree_gate_state import (  # noqa: F401 -- _MARKER_TTL_SECONDS/_marker_path are re-exported for tests
    _MARKER_TTL_SECONDS,
    _arm,
    _find_armed_root,
    _is_armed,
    _is_isolated,
    _marker_path,
    _release,
)


def _find_shared_scripts() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "shared" / "scripts"
        if candidate.is_dir():
            return candidate
    return here.parents[4] / "shared" / "scripts"  # historical fallback


_SHARED_SCRIPTS = _find_shared_scripts()
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

_OFF_ENV = "SHIPWRIGHT_ITERATE_WORKTREE_GATE"
_SKILL_NAMES = frozenset({"shipwright-iterate", "shipwright-iterate:iterate"})
_SLASH_RE = re.compile(r"^\s*/shipwright-iterate(?::iterate)?(?:\s|$)")
#: Campaign orchestration keeps its own worktree guard (``check_worktree_location``,
#: the session lock) and its step-0 setup is a multi-line shell block this gate
#: could not judge -- so a ``--campaign`` run is never armed.
_CAMPAIGN_RE = re.compile(r"(?:^|\s)--campaign(?:\s|=|$)")
#: A user-typed release phrase. ``UserPromptSubmit`` carries only prompts, and
#: the match is anchored to the WHOLE prompt, so neither the model's own output
#: nor an agent hand-back (which starts with ``<agent-message``) can trigger it.
_RELEASE_RE = re.compile(r"^\s*iterate gate off\s*$", re.IGNORECASE)
_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
_SHELL_TOOLS = frozenset({"Bash", "PowerShell"})
_WORKTREES_DIRNAME = ".worktrees"


def _setup_hint(session_id: str) -> str:
    """The setup command with THIS session's real id, so the run pointer it
    writes is owned by this session even when ``$SHIPWRIGHT_SESSION_ID`` is
    missing or stale in the shell."""
    script = _SHARED_SCRIPTS / "tools" / "setup_iterate_worktree.py"
    # Only an id that is plain shell-safe is echoed into a command line.
    sid = f" --session-id {session_id}" if re.fullmatch(r"[A-Za-z0-9._-]+", session_id) else ""
    return f'uv run "{script}" --project-root . --slug <slug> --run-id <run-id>{sid}'



_RESUME_NOTE = (
    "Resuming an existing .worktrees/<slug>? cd into it and re-run the same command there "
    "(a no-op that records this session). Never remove an existing worktree to get past this gate."
)


def _inside_main_tree(raw_path: object, cwd: Path, main_root: Path) -> bool:
    """True when ``raw_path`` is a file of the main checkout itself -- inside
    ``main_root`` but not under its ``.worktrees/``. Paths elsewhere (memory
    files, scratch dirs) are none of this gate's business."""
    if not isinstance(raw_path, str) or not raw_path.strip():
        return False
    target = Path(raw_path)
    target = (target if target.is_absolute() else cwd / target).resolve()
    try:
        target.relative_to(main_root.resolve())
    except ValueError:
        return False
    try:
        target.relative_to((main_root / _WORKTREES_DIRNAME).resolve())
    except ValueError:
        return True
    return False


def _blocked(tool_name: object, tool_input: object, cwd: Path, main_root: Path) -> bool:
    if not isinstance(tool_input, dict):
        return False
    if tool_name in _WRITE_TOOLS:
        raw = tool_input.get("file_path") or tool_input.get("notebook_path")
        return _inside_main_tree(raw, cwd, main_root)
    if tool_name in _SHELL_TOOLS:
        return not shell_is_preflight_safe(tool_input, powershell=tool_name == "PowerShell")
    return False


def _nudge(event: str, session_id: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": (
                "[Shipwright] Iterate worktree gate is armed: edits to the main "
                "checkout and non-read-only shell commands are blocked until the "
                f"worktree exists. First action (B1a): {_setup_hint(session_id)} {_RESUME_NOTE}"
            ),
        }
    }


def _deny(session_id: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "This is a /shipwright-iterate session and its worktree does not "
                "exist yet (SKILL.md B1a: every iterate runs in .worktrees/<slug>). "
                f"Run the setup step first, then cd into the project_root it prints: {_setup_hint(session_id)} "
                f"{_RESUME_NOTE} Only the user can lift this gate for the session (they set {_OFF_ENV}=off "
                "or type `iterate gate off`); do not try to work around it."
            ),
        }
    }


def handle_payload(payload: dict) -> dict | None:
    """Decision for one hook payload; ``None`` = take no position (allow)."""
    if os.environ.get(_OFF_ENV, "").strip().lower() in {"off", "0", "false"}:
        return None
    session_id, cwd_raw = payload.get("session_id"), payload.get("cwd")
    if not (isinstance(session_id, str) and session_id.strip() and isinstance(cwd_raw, str) and cwd_raw.strip()):
        return None
    cwd = Path(cwd_raw)
    event, tool_name = payload.get("hook_event_name"), payload.get("tool_name")
    prompt, tool_input = payload.get("prompt"), payload.get("tool_input")
    skill = tool_input.get("skill") if isinstance(tool_input, dict) else None
    arming = (
        (event == "UserPromptSubmit" and isinstance(prompt, str) and bool(_SLASH_RE.match(prompt)))
        or (event == "PreToolUse" and tool_name == "Skill" and skill in _SKILL_NAMES)
    )
    if arming and _is_campaign(prompt, tool_input):
        return None
    if event == "UserPromptSubmit" and isinstance(prompt, str) and _RELEASE_RE.match(prompt):
        return _on_user_release(cwd, session_id)
    if not arming and (event != "PreToolUse" or tool_name == "Skill"):
        return None

    if arming:
        from lib.codex_runtime import is_codex_runtime
        from lib.project_root import is_shipwright_project
        from lib.repo_root import main_repo_root_or

        main_root = main_repo_root_or(cwd)
        if is_codex_runtime() or not is_shipwright_project(main_root) or not _iterate_eligible(main_root):
            return None
        if _is_isolated(cwd, session_id):  # already in a worktree: nothing to enforce, nothing to arm
            return None
        _arm(main_root, session_id, "skill-tool" if event == "PreToolUse" else "slash-command")
        return _nudge(event, session_id)

    # A marker exists only if a non-Codex arm wrote one, so no runtime check here.
    main_root = _find_armed_root(cwd, session_id)
    if main_root is None:
        return None
    if _is_isolated(cwd, session_id):
        _release(main_root, session_id)
        return None
    return _deny(session_id) if _blocked(tool_name, tool_input, cwd, main_root) else None


def _iterate_eligible(main_root: Path) -> bool:
    """SKILL.md step B: iterate only runs on a completed project (run_config
    ``status: complete`` or an ``iterate_history``). Arming a project the skill
    will refuse would block its session for 24 h for nothing."""
    try:
        config = json.loads((main_root / "shipwright_run_config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(config, dict) and (config.get("status") == "complete" or bool(config.get("iterate_history")))


def _is_campaign(prompt: object, tool_input: object) -> bool:
    args = tool_input.get("args") if isinstance(tool_input, dict) else None
    parts = [prompt, *(args if isinstance(args, list) else [args])]
    text = " ".join(x for x in parts if isinstance(x, str))
    return bool(_CAMPAIGN_RE.search(text))


def _on_user_release(cwd: Path, session_id: str) -> dict | None:
    main_root = _find_armed_root(cwd, session_id)
    if main_root is None:
        return None
    _release(main_root, session_id)
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "[Shipwright] Iterate worktree gate released by the user for this session.",
        }
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        decision = handle_payload(payload) if isinstance(payload, dict) else None
    except Exception:  # noqa: BLE001 -- a hook must never crash the turn
        return 0
    if decision is not None:
        print(json.dumps(decision))
    return 0


if __name__ == "__main__":
    sys.exit(main())
