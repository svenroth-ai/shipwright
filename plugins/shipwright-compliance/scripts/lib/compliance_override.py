"""A logged, single-use, time-limited override of a compliance soft-block
(``check_rtm_coverage``, ``check_security_scan``).

Both hooks soft-block (exit 2) and tell the agent the user may say "Continue
anyway". Until 2026-10-08 neither hook read the log it asked for, so a logged
override changed nothing and the next attempt was blocked again. Now one entry in
``.shipwright/agent_docs/compliance_overrides.log`` naming the hook lets that
hook's NEXT blocked command through, if it comes within :data:`WINDOW` of the
entry's timestamp. The hook then appends a ``CONSUMED`` line naming the entry, so
the next block needs a new "Continue anyway" (a command that fails after the hook
let it through has still used the override; when that line cannot be written the
override is not applied, so it can never pass twice). Every pass-through says so in a
visible WARN. An entry needs a timestamp, the hook name and a non-empty reason;
one dated in the future (beyond :data:`CLOCK_SKEW`) is ignored, so an override
cannot be pre-dated; a malformed line is skipped. The log is therefore an INPUT to
both gates, not only an audit trail.

Line shapes read: ``<UTC ISO timestamp> | <hook> | OVERRIDE | <reason>`` (the one
the block message asks for), ``override_logger.log_override``'s
``[<ts>] OVERRIDE hook=<hook> reason="<reason>"``, and
``<ts> | <hook> | CONSUMED | <entry timestamp>`` (written here).
"""

from __future__ import annotations

import re
import shlex
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

LOG_RELPATH = Path(".shipwright/agent_docs/compliance_overrides.log")
WINDOW = timedelta(minutes=30)
CLOCK_SKEW = timedelta(minutes=1)
_PIPE = re.compile(r"^\s*(\S+)\s*\|\s*([\w.-]+)\s*\|\s*(OVERRIDE|CONSUMED)\s*\|(.*)$")
_LOGGER = re.compile(r'^\s*\[([^\]]+)\]\s+(OVERRIDE)\s+hook=([\w.-]+)\s+reason="(.*?)"')
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class Override(NamedTuple):
    at: datetime
    reason: str


def _when(text: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _entries(lines: list[str], hook: str):
    """``(kind, timestamp, text)`` for every well-formed line about *hook*."""
    for line in lines:
        pipe = _PIPE.match(line)
        if pipe:
            ts, name, kind, text = pipe.groups()
        else:
            logger = _LOGGER.match(line)
            if not logger:
                continue
            ts, kind, name, text = logger.groups()
        at = _when(ts)
        if name == hook and at is not None:
            yield kind, at, text.strip()


def active_override(project_root: str | Path, hook: str,
                    now: datetime | None = None) -> Override | None:
    """The newest unconsumed entry for *hook* still inside its window, else ``None``."""
    try:
        lines = (Path(project_root) / LOG_RELPATH).read_text(
            encoding="utf-8-sig", errors="replace").splitlines()  # an editor's BOM
    except OSError:
        return None
    now = now or datetime.now(timezone.utc)
    entries = list(_entries(lines, hook))
    used = {_when(text) for kind, _at, text in entries if kind == "CONSUMED"}
    best: Override | None = None
    for kind, at, reason in entries:
        if kind != "OVERRIDE" or not reason or at in used:
            continue
        if -CLOCK_SKEW <= now - at <= WINDOW and (best is None or at > best.at):
            best = Override(at, reason)
    return best


def consume(project_root: str | Path, hook: str, found: Override,
            now: datetime | None = None) -> str | None:
    """Record that *found* let a command through; a WARN sentence when it cannot be written."""
    now = now or datetime.now(timezone.utc)
    line = f"{_stamp(now)} | {hook} | CONSUMED | {found.at.isoformat()}\n"
    try:
        with open(Path(project_root) / LOG_RELPATH, "a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError as exc:
        return (f"the logged override could not be marked used ({type(exc).__name__}), so it "
                "is NOT applied: make the log writable, then re-run")
    return None


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def instruction(project_root: str | Path, hook: str) -> str:
    """The exact line to log after the user says "Continue anyway"."""
    log = (Path(project_root) / LOG_RELPATH).as_posix()
    target = shlex.quote(log)
    return (
        "The user may say 'Continue anyway' to override this check. If they do, append "
        f"ONE line (UTC timestamp | hook name | OVERRIDE | the user's reason) to {log}; "
        "it lets this hook's next blocked command through within "
        f"{int(WINDOW.total_seconds() // 60)} minutes, once. Then re-run the command:\n"
        f"printf '%s | {hook} | OVERRIDE | %s\\n' \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\" "
        f"'<the reason the user gave>' >> {target}"
    )


def notice(hook: str, found: Override, blocked_reason: str) -> str:
    """The WARN shown when an override lets a blocked command through."""
    reason = _CONTROL.sub(" ", found.reason)[:200]
    return (
        f"WARN ({hook}): OVERRIDDEN once by the logged override of {_stamp(found.at)} "
        f"(\"{reason}\"), now used; the check would have blocked: {blocked_reason}"
    )
