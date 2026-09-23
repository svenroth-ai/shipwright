#!/usr/bin/env python3
"""``UserPromptSubmit`` hook: mints the Codex activation record (R2 — AC1a).

Codex-only; a documented no-op under Claude Code (``is_codex_runtime()`` is
False for an ordinary Claude plugin-cache root — ``lib.codex_runtime``).
Parses the incoming prompt via the envelope grammar
(``lib.codex_envelope_grammar``) and mints an activation record
(``lib.codex_activation_record``) recording whether this session is armed.

Mint is exclusive-create-only, so only the FIRST ``UserPromptSubmit`` in a
session actually decides the armed state — every later prompt in the same
session finds the record already exists, ``mint()`` returns ``None``, and
this hook does nothing further. That is Step 4's own guarantee; this hook
adds no extra "already minted" check of its own.

Writes nothing to ``additionalContext`` — this hook is a silent side-effect
producer for the ``PreToolUse`` gate (Step 6) to read later, not a
model-facing one."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _find_shared_scripts() -> Path:
    """Locate shared/scripts/ by walking up — robust to plugin-layout depth
    (mirrors ``iterate_stop_finalize.py``'s identical helper)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "shared" / "scripts"
        if candidate.is_dir():
            return candidate
    return here.parents[4] / "shared" / "scripts"  # historical fallback


_SHARED_SCRIPTS = _find_shared_scripts()
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.codex_activation_record import mint, normalize_cwd  # noqa: E402
from lib.codex_envelope_grammar import parse  # noqa: E402
from lib.codex_runtime import is_codex_runtime  # noqa: E402
from lib.project_root import is_shipwright_project  # noqa: E402

#: This gate is iterate-only (branch/run scope), so a syntactically valid
#: envelope for a DIFFERENT skill must not arm it (external review, openai
#: medium: any valid envelope armed the gate regardless of skill_id, letting
#: an unrelated future Codex skill be forced through the iterate setup step).
_ACCEPTED_SKILL_IDS = frozenset({"shipwright-iterate:iterate"})


def _resolve_project_root(cwd: str) -> str:
    """Anchor on the payload's own per-turn ``cwd`` — never the hook
    subprocess's ambient OS cwd (code review, HIGH: ``resolve_project_root()``
    reads ``Path.cwd()``, not the payload, so it can silently disagree with
    where Codex says this turn actually ran). Resolves through the SAME
    git main-repo-root canonicalization ``codex_activation_record.normalize_cwd``
    already applies to the record's ``cwd`` field, so ``project_root``
    (mint()'s exclusive-create KEY, per session_id) is stable across a
    session's calls even if the raw invocation cwd varies between turns
    (subdirectory, worktree) — without this, two different project_root
    values for the same session silently split one session's state across
    two unrelated storage paths, defeating "only the first prompt decides"
    entirely (code review, HIGH)."""
    return normalize_cwd(cwd)


def handle_payload(payload: dict) -> None:
    """Mint this session's activation record from a ``UserPromptSubmit``
    payload, or do nothing. Never raises — every failure path (not Codex, no
    ``session_id``, already-minted, grammar mismatch, an unaccepted
    ``skill_id``, or a malformed payload shape) is a legitimate no-op, not an
    error — an unaccepted ``skill_id`` still mints an explicit unarmed
    record, same as no grammar match at all. ``session_id``/``cwd`` are
    validated as non-empty strings up front (code review, MEDIUM: a
    non-string value previously reached ``mint()``/``normalize_cwd()``
    directly and raised, silently masked only by ``main()``'s unrelated
    blanket ``except`` — this function's own docstring claim of never
    raising was not actually true)."""
    if not is_codex_runtime():
        return

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        return

    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd.strip():
        return

    turn_id = payload.get("turn_id")
    turn_id = turn_id if isinstance(turn_id, str) else ""
    prompt = payload.get("prompt")
    prompt = prompt if isinstance(prompt, str) else ""
    project_root = _resolve_project_root(cwd)

    if not is_shipwright_project(Path(project_root)):
        return

    envelope = parse(prompt)
    if envelope is not None and envelope.skill_id in _ACCEPTED_SKILL_IDS:
        mint(
            project_root,
            session_id=session_id,
            turn_id=turn_id,
            cwd=cwd,
            armed=True,
            skill_id=envelope.skill_id,
            args=envelope.args,
        )
    else:
        mint(
            project_root,
            session_id=session_id,
            turn_id=turn_id,
            cwd=cwd,
            armed=False,
        )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return 0

    if not isinstance(payload, dict):
        return 0

    try:
        handle_payload(payload)
    except Exception:  # noqa: BLE001 — a hook must never crash the turn
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
