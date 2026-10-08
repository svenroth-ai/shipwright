"""A logged, single-use, time-limited override of a compliance soft-block
(``check_rtm_coverage``, ``check_security_scan``).

Both hooks soft-block (exit 2) and tell the agent the user may say "Continue
anyway". Until 2026-10-08 neither hook read the log it asked for, so a logged
override changed nothing and the next attempt was blocked again. Now one entry in
``.shipwright/agent_docs/compliance_overrides.log`` naming the hook lets that
hook's NEXT blocked command through, if it comes within :data:`WINDOW` of the
entry's timestamp (:func:`try_release`). The hook then appends a ``CONSUMED`` line
naming the entry, so the next block needs a new "Continue anyway" (a command that
fails after the hook let it through has still used the override; when that line
cannot be written the override is not applied, so it can never pass twice). The
read -> check -> append runs under an exclusive lock file next to the log
(``O_EXCL``; one older than :data:`STALE_LOCK_S` is broken), re-reading the log
once the lock is held, so two hooks racing on one entry release one command. Every
pass-through says so in a visible WARN. An entry needs a timestamp, the hook name
and a non-empty reason; one dated in the future (beyond :data:`CLOCK_SKEW`) is
ignored, so an override cannot be pre-dated; a malformed line is skipped. A
matching entry that is outside its window or skewed is named in the block, so the
agent knows why it did not apply. The log is therefore an INPUT to both gates, not
only an audit trail.

**Attribution, not a human gate.** The operator chose "approval in the log": the
model itself can write the OVERRIDE line (the block prints it). The log gives
after-the-fact attribution of who released what and why; it does not prove a human
said "Continue anyway". **Tracked file.** The log is git-tracked, so the OVERRIDE and
CONSUMED lines ride along with ``git commit -a`` (or any commit that stages it).
``.shipwright/compliance/compliance_overrides.log`` (the Sec2 verifier's input) is a
different path, not read here.

Line shapes read: ``<UTC ISO timestamp> | <hook> | OVERRIDE | <reason>`` (the one
the block message asks for), ``override_logger.log_override``'s
``[<ts>] OVERRIDE hook=<hook> reason="<reason>"``, and
``<ts> | <hook> | CONSUMED | <entry timestamp>`` (written here).
"""

from __future__ import annotations

import os
import re
import shlex
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

LOG_RELPATH = Path(".shipwright/agent_docs/compliance_overrides.log")
WINDOW = timedelta(minutes=30)
CLOCK_SKEW = timedelta(minutes=1)
LOCK_WAIT_S = 5.0
STALE_LOCK_S = 30.0
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


def _unconsumed(project_root: str | Path, hook: str) -> list[Override]:
    """Every OVERRIDE entry for *hook* with a reason and no CONSUMED line naming it."""
    try:
        lines = (Path(project_root) / LOG_RELPATH).read_text(
            encoding="utf-8-sig", errors="replace").splitlines()  # an editor's BOM
    except OSError:
        return []
    entries = list(_entries(lines, hook))
    used = {_when(text) for kind, _at, text in entries if kind == "CONSUMED"}
    return [Override(at, reason) for kind, at, reason in entries
            if kind == "OVERRIDE" and reason and at not in used]


def _in_window(found: Override, now: datetime) -> bool:
    return -CLOCK_SKEW <= now - found.at <= WINDOW


def active_override(project_root: str | Path, hook: str,
                    now: datetime | None = None) -> Override | None:
    """The newest unconsumed entry for *hook* still inside its window, else ``None``."""
    now = now or datetime.now(timezone.utc)
    live = [found for found in _unconsumed(project_root, hook) if _in_window(found, now)]
    return max(live, default=None, key=lambda found: found.at)


def _unapplied(project_root: str | Path, hook: str, now: datetime) -> str | None:
    """Why the newest unconsumed entry for *hook* outside its window was not applied."""
    stale = [found for found in _unconsumed(project_root, hook) if not _in_window(found, now)]
    if not stale:
        return None
    found = max(stale, key=lambda entry: entry.at)
    why = (f"it is dated more than {int(CLOCK_SKEW.total_seconds())} s in the future "
           "(a pre-dated entry is ignored)" if found.at > now else
           f"it is older than the {int(WINDOW.total_seconds() // 60)}-minute window")
    return f"the logged override of {_stamp(found.at)} was NOT applied: {why}"


@contextmanager
def _locked(log: Path):
    """Hold ``<log>.lock`` (created ``O_EXCL``) for the block; a stale one is broken.

    Raises ``TimeoutError`` after :data:`LOCK_WAIT_S`, ``OSError`` when it cannot be made.
    """
    lock = log.with_name(log.name + ".lock")
    deadline = time.monotonic() + LOCK_WAIT_S
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > STALE_LOCK_S:
                    lock.unlink(missing_ok=True)  # its holder died: break it
                    continue
            except FileNotFoundError:
                continue  # released meanwhile: retry at once
            except OSError:
                pass  # cannot tell its age: wait for it like a live one
            if time.monotonic() >= deadline:
                raise TimeoutError(f"{lock} is held") from None
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


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


def try_release(project_root: str | Path, hook: str,
                now: datetime | None = None) -> tuple[Override | None, str | None]:
    """``(override, None)`` when a logged override releases this block (now consumed),
    else ``(None, why-not)``; *why-not* is ``None`` when there simply is none."""
    now = now or datetime.now(timezone.utc)
    if active_override(project_root, hook, now) is None:  # the common case: no lock taken
        return None, _unapplied(project_root, hook, now)
    try:
        with _locked(Path(project_root) / LOG_RELPATH):
            found = active_override(project_root, hook, now)  # re-read under the lock
            if found is None:
                return None, ("the logged override was used by a concurrent command "
                              "meanwhile, so it is NOT applied here")
            failure = consume(project_root, hook, found, now)
    except (OSError, TimeoutError) as exc:
        return None, (f"the override log could not be locked ({type(exc).__name__}), so the "
                      "override is NOT applied: re-run")
    return (None, failure) if failure else (found, None)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def instruction(project_root: str | Path, hook: str) -> str:
    """The exact line to log after the user says "Continue anyway"."""
    log = (Path(project_root) / LOG_RELPATH).as_posix()
    reason = shlex.quote("<the reason the user gave>")
    return (
        "The user may say 'Continue anyway' to override this check. If they do, append "
        f"ONE line (UTC timestamp | hook name | OVERRIDE | the user's reason) to {log}; "
        "it lets this hook's next blocked command through within "
        f"{int(WINDOW.total_seconds() // 60)} minutes, once. Keep the reason in single "
        "quotes and replace any single quote inside it (or write it as '\\''). "
        "Then re-run the command:\n"
        f"printf '%s | {hook} | OVERRIDE | %s\\n' \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\" "
        f"{reason} >> {shlex.quote(log)}"
    )


def notice(hook: str, found: Override, blocked_reason: str) -> str:
    """The WARN shown when an override lets a blocked command through."""
    reason = _CONTROL.sub(" ", found.reason)[:200]
    return (
        f"WARN ({hook}): OVERRIDDEN once by the logged override of {_stamp(found.at)} "
        f"(\"{reason}\"), now used; the check would have blocked: {blocked_reason}"
    )
