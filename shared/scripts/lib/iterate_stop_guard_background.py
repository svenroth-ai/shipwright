"""Background tasks a session is waiting on (a reviewer subagent, a background
shell), read from the transcript for the iterate Stop-guard.

An agent that follows the guard's own advice -- "a named background task is still
running: end the turn WITHOUT further tool calls and resume on its notification" --
ends its turn on purpose, and the task's completion notice wakes it again. That
Stop is not a premature give-up, so the guard stays silent while such a task is
pending. A launch is a tool_result entry whose structured ``toolUseResult`` says so
(``isAsync`` for an agent, ``backgroundTaskId`` for a shell -- also one the harness
moved to the background after its timeout, ``taskId`` for a non-persistent monitor);
tool output that merely quotes a launch sentence has none of these fields and does
not count. Its completion is the ``<task-notification>`` carrying the same
``tool-use-id`` and a terminal ``status``. Persistent monitors never finish and are
not tracked. A task whose notice never arrives stops counting after a bound (agent
2 h, shell 30 min), so a crashed session cannot silence the guard for good.
Accepted risk: a background shell that never ends AND whose agent stops early is not
caught for up to 30 min (nothing wakes the agent, so there is no later Stop to block).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

BG_MAX_AGE_SECONDS = {"agent": 2 * 60 * 60, "shell": 30 * 60}
_NOTICE = re.compile(r"<tool-use-id>([^<\s]+)</tool-use-id>.*?<status>([a-z]+)</status>", re.DOTALL)
_TERMINAL = frozenset({"completed", "failed", "killed", "stopped", "cancelled"})
_FUTURE_SLACK_SECONDS = 300


def _launch_kind(result: object) -> str | None:
    """``agent`` | ``shell`` for a structured launch result, else ``None``."""
    if not isinstance(result, dict):
        return None
    if result.get("isAsync") is True:
        return "agent"
    if result.get("backgroundTaskId") or (result.get("taskId") and result.get("persistent") is False):
        return "shell"
    return None


def _notice_text(line: str) -> str:
    """The text a harness notice can arrive in: a queue entry's ``content`` or a user entry's own
    text blocks. Assistant text and tool_result output (a grep or a Read of a transcript) are never
    notices, so quoting one cannot clear a pending task."""
    try:
        entry = json.loads(line)
    except ValueError:
        return ""
    if not isinstance(entry, dict) or entry.get("type") == "assistant":
        return ""
    parts = [entry["content"]] if isinstance(entry.get("content"), str) else []
    attachment = entry.get("attachment")
    if isinstance(attachment, dict):
        parts += [v for v in attachment.values() if isinstance(v, str)]
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        parts.append(content)
    for block in content if isinstance(content, list) else []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return chr(10).join(parts)


def track(pending: dict, line: str, now: datetime | None = None) -> None:
    """Update ``pending`` (``{tool_use_id: {"ts", "kind"}}``) from one transcript line."""
    if '"toolUseResult"' in line:
        try:
            entry = json.loads(line)
        except ValueError:
            entry = None
        kind = _launch_kind(entry.get("toolUseResult")) if isinstance(entry, dict) else None
        message = entry.get("message") if kind else None
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if not (isinstance(block, dict) and block.get("type") == "tool_result" and block.get("tool_use_id")):
                continue
            stamp = str(entry.get("timestamp") or "") or (now or datetime.now(timezone.utc)).isoformat()
            try:
                ref = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                ref = ref if ref.tzinfo else ref.replace(tzinfo=timezone.utc)
            except ValueError:
                ref = now or datetime.now(timezone.utc)
            for key in [k for k, t in pending.items() if not waiting({k: t}, ref)]:
                del pending[key]  # expired / unreadable entries would only bloat the state file
            pending[str(block["tool_use_id"])] = {"ts": stamp, "kind": kind}
    if "<task-notification>" in line:  # AFTER the launches: a notice batched with its own launch must win
        for segment in _notice_text(line).split("<task-notification>")[1:]:
            found = _NOTICE.search(segment)
            if found and found.group(2) in _TERMINAL:
                pending.pop(found.group(1), None)


def waiting(pending: dict, now: datetime | None = None) -> bool:
    """True while a launched task is unfinished and younger than its bound."""
    now = now or datetime.now(timezone.utc)
    for task in pending.values():
        try:
            when = datetime.fromisoformat(str(task.get("ts", "")).replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue  # unreadable launch time: never let it silence the guard
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if (when - now).total_seconds() > _FUTURE_SLACK_SECONDS:
            continue  # a timestamp from the future (clock skew, tampering) must not extend the silence
        if (now - when).total_seconds() < BG_MAX_AGE_SECONDS.get(task.get("kind"), 1800):
            return True
    return False
