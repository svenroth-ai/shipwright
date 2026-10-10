"""Transcript + run-pointer reading for the iterate Stop-guard (split from
``iterate_stop_guard`` to stay under the file-size limit): which iterate invocation
is the latest and is it autonomous, how many tool calls happened, and which run
pointer belongs to this session."""

from __future__ import annotations

import json
import os
import re
import shlex
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

from lib.iterate_stop_guard_background import track as track_background

_ITERATE_CMD = re.compile(
    r"<command-name>/?(?:shipwright-iterate:)?(?:shipwright-)?iterate</command-name>"
)
_ITERATE_SKILLS = frozenset({"iterate", "shipwright-iterate", "shipwright-iterate:iterate",
                             "shipwright-iterate:shipwright-iterate"})
_ARGS_BLOCK = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL)
# Flags that take a value (their arity decides where the free-text description starts).
_VALUE_FLAGS = frozenset({
    "type", "campaign", "sub-iterate-id", "complexity",
    "review-model", "finalization-model", "plan-review-model",
})


class Scan(NamedTuple):
    autonomous: bool
    tools: int
    offset: int
    reset: bool = False
    background: dict | None = None  # {tool_use_id: {"ts", "kind"}} of unfinished background tasks


def parse_flags(args: str) -> tuple[bool, bool]:
    """``(autonomous, campaign)`` from an iterate invocation's arguments.

    Only the leading flags (with their real arity) and a trailing
    ``--autonomous`` count; a flag name inside the free-text description does not.
    """
    try:
        tokens = shlex.split(args, posix=True)
    except ValueError:
        tokens = args.split()
    flags: set[str] = set()
    i = 0
    while i < len(tokens) and tokens[i].startswith("--"):
        name, has_value = tokens[i][2:].split("=", 1)[0], "=" in tokens[i]
        flags.add(name)
        i += 1 if has_value or name not in _VALUE_FLAGS else 2
    if tokens and tokens[-1] == "--autonomous":
        flags.add("autonomous")
    return "autonomous" in flags, "campaign" in flags


MAX_POINTER_AGE_HOURS = 48


def _fresh(pointer: dict) -> bool:
    try:
        created = datetime.fromisoformat(str(pointer.get("created_at")).replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - created < timedelta(hours=MAX_POINTER_AGE_HOURS)
    except ValueError:
        return True  # no usable timestamp: do not guess it stale


def _transcript_mentions(transcript_path: str, needle: str) -> bool:
    try:
        with open(transcript_path, "rb") as fh:
            return any(needle.encode() in line for line in fh)
    except OSError:
        return False


def live_pointer(main_root: Path, session_id: str, transcript_path: str) -> dict | None:
    """This session's run pointer, else a session-less one (written when
    ``$SHIPWRIGHT_SESSION_ID`` did not reach the setup shell) whose run id the
    transcript names. Pointers older than ``MAX_POINTER_AGE_HOURS`` are ignored:
    a merge outside ``deliver_pr.py`` leaves them behind."""
    from lib.worktree_isolation import ACTIVE_POINTER_DIRNAME, read_run_pointer

    own = read_run_pointer(main_root, session_id)
    if own and own.get("run_id"):
        return own if _fresh(own) else None
    for path in sorted((main_root / ".shipwright" / ACTIVE_POINTER_DIRNAME).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (isinstance(data, dict) and not data.get("session_id") and data.get("run_id")
                and _fresh(data) and _transcript_mentions(transcript_path, str(data["run_id"]))):
            return data
    return None


def _entry_text(entry: dict) -> str:
    """The text of a user entry: a plain string or the joined ``text`` blocks."""
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _iterate_invocation(entry: dict) -> bool | None:
    """``True`` = an autonomous standalone iterate was started, ``False`` = an
    interactive or campaign one, ``None`` = this entry starts no iterate."""
    args = None
    if entry.get("type") == "user":
        text = _entry_text(entry)
        block = _ARGS_BLOCK.search(text)
        if _ITERATE_CMD.search(text):
            args = block.group(1) if block else ""
    elif entry.get("type") == "assistant":
        content = (entry.get("message") or {}).get("content")
        for item in content if isinstance(content, list) else []:
            if item.get("type") == "tool_use" and item.get("name") == "Skill":
                inp = item.get("input") or {}
                if str(inp.get("skill", "")) in _ITERATE_SKILLS:
                    args = str(inp.get("args", ""))
    if args is None:
        return None
    autonomous, campaign = parse_flags(args)
    return autonomous and not campaign


def scan_transcript(transcript_path: str, state: dict | None = None) -> Scan:
    """Latest-invocation autonomy, tool_use count and the end offset.

    Incremental: resumes at the stored offset with the stored count and
    autonomy, so a 100 MB transcript is not re-read on every Stop. A different
    transcript file, or one that shrank, is rescanned from the start and flagged
    ``reset`` so the caller does not mistake the lower count for idleness.
    """
    state = state or {}
    autonomous, tools, start = bool(state.get("autonomous")), int(state.get("tools", 0)), int(state.get("offset", 0))
    reset = False
    saved = state.get("bg")
    background = {k: v for k, v in saved.items() if isinstance(v, dict)} if isinstance(saved, dict) else {}
    try:
        if state.get("path") not in (None, transcript_path) or start > os.path.getsize(transcript_path):
            autonomous, tools, start, reset = False, 0, 0, bool(state)
            background = {}
        consumed = start
        with open(transcript_path, "rb") as fh:
            fh.seek(start)
            for raw in fh:
                if not raw.endswith(b"\n"):
                    break  # never count a half-written last line
                consumed += len(raw)
                line = raw.decode("utf-8", errors="replace")
                try:
                    track_background(background, line)
                except Exception:  # noqa: BLE001 - one poison line must not disable the guard for the run
                    pass
                if '"tool_use"' in line:
                    tools += line.count('"type":"tool_use"') or line.count('"type": "tool_use"')
                if "iterate" in line and ("command-name" in line or '"Skill"' in line):
                    try:
                        found = _iterate_invocation(json.loads(line))
                    except ValueError:
                        continue
                    if found is not None:
                        autonomous = found
    except OSError:
        return Scan(False, 0, 0)
    return Scan(autonomous, tools, consumed, reset, background)
