#!/usr/bin/env python3
"""SessionStart hook (SP2): inject the ``using-shipwright`` bootstrap.

When ``shipwright_run_config.json`` is present in the project root, emit
``shared/prompts/using-shipwright.md`` as ``additionalContext`` so a fresh
session knows the lay of the land (route changes to ``/shipwright-iterate``,
compliance questions to ``/shipwright-compliance``, …) WITHOUT the user having
to prime it. In a non-Shipwright project the hook stays silent.

This hook is registered in all 12 hooks-bearing plugin ``hooks.json`` files
(``shipwright-preview`` has none), so it fires up to 12 times per session. An
atomic O_EXCL session sentinel under ``.shipwright/locks/`` ensures exactly ONE
firing emits the context; the rest return empty (no duplicate injection). The
session id comes from the hook **stdin payload** (``session_id``) — the env var
``SHIPWRIGHT_SESSION_ID`` is NOT set in sibling SessionStart hook processes, so
keying the sentinel off it would inject only the first session ever.

Output schema (SessionStart): ``hookSpecificOutput.additionalContext`` —
top-level ``additionalContext`` is silently ignored (Spike F0 finding,
mirrored from phase_session_start.py / check_drift.py).

Adapted from the obra/superpowers ``using-superpowers`` SessionStart bootstrap
pattern (MIT, © Jesse Vincent — https://github.com/obra/superpowers).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CONFIG_NAME = "shipwright_run_config.json"
PROMPT_NAME = "using-shipwright.md"
_SENTINEL_PREFIX = "using_shipwright_bootstrap"


def _resolve_project_root() -> Path:
    """Resolve the project root via the shared resolver, else env/cwd."""
    try:
        scripts_dir = str(Path(__file__).resolve().parent.parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from lib.project_root import resolve_project_root  # noqa: PLC0415

        return resolve_project_root()
    except (ImportError, ValueError):
        env_root = os.environ.get("SHIPWRIGHT_PROJECT_ROOT")
        return Path(env_root) if env_root else Path.cwd()


def _session_id(payload: object = None) -> str:
    """Session id for the dedup sentinel.

    Prefer the hook stdin payload's ``session_id`` (always present, and the
    same value across all 12 plugin firings this session); fall back to the
    ``SHIPWRIGHT_SESSION_ID`` env var, then ``"unknown"``. Sourcing from the
    env alone is wrong here — it is unset in sibling SessionStart processes.
    """
    if isinstance(payload, dict):
        sid = payload.get("session_id")
        if isinstance(sid, str) and sid.strip():
            return sid.strip()
    return (os.environ.get("SHIPWRIGHT_SESSION_ID") or "").strip() or "unknown"


def _default_prompts_dir() -> Path:
    # shared/scripts/hooks/<this> -> shared/prompts/
    return Path(__file__).resolve().parent.parent.parent / "prompts"


def build_payload(text: str) -> dict:
    """The SessionStart additionalContext envelope."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": text,
        }
    }


def _claim_once(project_root: Path, session_id: str) -> bool:
    """Atomically claim the once-per-session slot. ``True`` = we won the race.

    O_CREAT|O_EXCL means the FIRST of the (up to 12) plugin firings creates the
    sentinel and emits; the rest see ``FileExistsError`` and stay silent. On any
    filesystem error we fail OPEN (claim succeeds) so the context still surfaces.
    """
    locks = project_root / ".shipwright" / "locks"
    try:
        locks.mkdir(parents=True, exist_ok=True)
        sentinel = locks / f"{_SENTINEL_PREFIX}.{session_id}"
        # 0o600 (owner-only): per-session sentinel, non-secret + single-user.
        fd = os.open(str(sentinel), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return True  # fail-open — better a (rare) double-inject than silence


def run(*, project_root: Path, session_id: str, prompts_dir: Path) -> str:
    """Return the stdout string to emit (``""`` = stay silent)."""
    if not (project_root / CONFIG_NAME).is_file():
        return ""  # non-Shipwright project — no false trigger
    prompt = prompts_dir / PROMPT_NAME
    try:
        text = prompt.read_text(encoding="utf-8")
    except OSError:
        return ""  # fail-open — never crash a SessionStart
    if not text.strip():
        return ""
    if not _claim_once(project_root, session_id):
        return ""  # another plugin's firing already injected this session
    return json.dumps(build_payload(text))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        payload = None
    out = run(
        project_root=_resolve_project_root(),
        session_id=_session_id(payload),
        prompts_dir=_default_prompts_dir(),
    )
    if out:
        sys.stdout.write(out + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"using_shipwright: unexpected error ({exc!r}) — fail-open", file=sys.stderr)
        sys.exit(0)
