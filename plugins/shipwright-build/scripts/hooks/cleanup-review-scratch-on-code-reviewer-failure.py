#!/usr/bin/env python3
"""Failure-path safety net for the Step 6b/6c review-scratch diff file.

Fires on SubagentStop for shipwright-build:code-reviewer, alongside
write-review-payload-on-stop.py. `code-review-protocol.md` Step 6b writes
the diff via `review_scratch.py resolve` and deliberately does NOT clean it
up itself — 6c (the optional external cascade) reuses the exact same file
and is the sole cleanup owner on a NORMAL completion. But if the
code-reviewer subagent crashes or returns no parseable review, 6c is never
reached the way the protocol expects, and the diff (which can contain
source code) would otherwise linger in the private scratch root with no
call site left to remove it (PR #676 external-review finding).

This hook only acts on that FAILURE path: it inspects the subagent's own
transcript exactly like the salvage hook does, and calls `cleanup()` only
when the last reply is NOT a parseable review payload. A successful
completion is a no-op here, since 6c still needs the file. `cleanup()` is
itself a no-op if 6c already removed it, so this is safe to run either way
the race lands.

Deliberately self-contained (no shared import — see
write-review-payload-on-stop.py's docstring for why: ADR-044 lib collision
risk across this plugin's own pytest process). Never blocks: any failure to
resolve a session id or run the cleanup CLI is logged to stderr, exit 0.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)


def _diag(message: str, **detail: Any) -> None:
    sys.stderr.write(f"[shipwright:review-scratch-cleanup] {message}\n")
    if detail:
        sys.stderr.write(
            f"[shipwright:review-scratch-cleanup] detail={json.dumps(detail, ensure_ascii=False)}\n"
        )


def read_transcript_with_retry(transcript_path: str, max_retries: int = 4) -> list[dict]:
    delays = [0.05, 0.1, 0.2, 0.4]
    for attempt in range(max_retries):
        try:
            if not os.path.exists(transcript_path):
                if attempt < max_retries - 1:
                    time.sleep(delays[attempt])
                    continue
                return []
            with open(transcript_path, encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                if attempt < max_retries - 1:
                    time.sleep(delays[attempt])
                    continue
                return []
            entries = []
            for line in content.splitlines():
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            if entries:
                return entries
            if attempt < max_retries - 1:
                time.sleep(delays[attempt])
        except OSError:
            if attempt < max_retries - 1:
                time.sleep(delays[attempt])
    return []


def _entry_text(entry: dict) -> str:
    content = entry.get("content", "")
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return content if isinstance(content, str) else ""


def last_assistant_reply(entries: list[dict]) -> Optional[str]:
    for entry in reversed(entries):
        if entry.get("role") == "assistant":
            text = _entry_text(entry)
            if text.strip():
                return text
    return None


def _is_review_shaped(value: Any) -> bool:
    """Matches `code-review-protocol.md`'s documented reply shape
    (`{"section": ..., "review": [...]}`) — deliberately stricter than the
    salvage hook's `looks_like_review_payload`, which only needs "plausible
    enough to write to a file for a human to re-parse later". Here a false
    "this looks like a review" means cleanup is wrongly skipped, so `null`,
    a bare string, `{}`, or an unrelated object must all read as failure."""
    return isinstance(value, dict) and isinstance(value.get("review"), list)


def looks_like_review_payload(text: str) -> bool:
    for match in _FENCE_RE.finditer(text):
        try:
            if _is_review_shaped(json.loads(match.group(1))):
                return True
        except json.JSONDecodeError:
            continue
    try:
        return _is_review_shaped(json.loads(text))
    except json.JSONDecodeError:
        return False


def resolve_project_root() -> Path:
    env = os.environ.get("SHIPWRIGHT_PROJECT_ROOT", "").strip()
    return Path(env) if env else Path.cwd()


def resolve_shared_root() -> Optional[Path]:
    plugin_root = os.environ.get("SHIPWRIGHT_PLUGIN_ROOT", "").strip()
    if not plugin_root:
        return None
    candidate = Path(plugin_root) / ".." / ".." / "shared"
    return candidate if candidate.exists() else None


def main(argv: Optional[list[str]] = None) -> int:  # noqa: ARG001 — no CLI args needed
    session_id = (os.environ.get("SHIPWRIGHT_SESSION_ID") or "").strip()
    if not session_id:
        _diag("no SHIPWRIGHT_SESSION_ID in hook environment — nothing to clean up")
        return 0

    try:
        payload = json.load(sys.stdin)
    except Exception as exc:  # noqa: BLE001 — a bad payload must not block
        _diag("could not parse SubagentStop stdin payload", exception=str(exc))
        return 0

    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        _diag("no transcript_path in payload")
        return 0

    entries = read_transcript_with_retry(transcript_path)
    reply = last_assistant_reply(entries) if entries else None
    if reply and looks_like_review_payload(reply):
        _diag("code-reviewer returned a parseable review — 6c still owns cleanup, no-op")
        return 0

    shared_root = resolve_shared_root()
    if shared_root is None:
        _diag("could not resolve shared_root from SHIPWRIGHT_PLUGIN_ROOT — cannot clean up")
        return 0

    script = shared_root / "scripts" / "tools" / "review_scratch.py"
    try:
        result = subprocess.run(
            ["uv", "run", str(script), "cleanup", "--run-id", session_id],
            cwd=str(resolve_project_root()),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _diag("cleanup subprocess could not be started — hook must not block on it, "
              "but the scratch diff was NOT confirmed removed",
              run_id=session_id, exception=str(exc))
        return 0
    if result.returncode != 0:
        _diag("cleanup command FAILED — the scratch diff was NOT confirmed removed",
              run_id=session_id, returncode=result.returncode,
              stderr=(result.stderr or "").strip()[-2000:])
        return 0
    _diag("code-reviewer failed to return a parseable review — cleaned up scratch diff",
          run_id=session_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
