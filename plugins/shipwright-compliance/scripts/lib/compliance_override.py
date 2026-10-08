"""A logged, single-use, time-limited override of a compliance soft-block
(``check_rtm_coverage``, ``check_security_scan``).

Both hooks soft-block (exit 2) and tell the agent the user may say "Continue
anyway". One entry in ``.shipwright/agent_docs/compliance_overrides.log`` naming the
hook lets that hook's NEXT blocked command through, if it comes within :data:`WINDOW`
of the entry's timestamp (:func:`try_release`). The hook then appends a ``CONSUMED``
line naming the entry (a command that fails afterwards has still used it; when the line
cannot be written the override is not applied). **The unit is one hook run, i.e. one
Bash command**: a command holding several commits is released whole by one override,
and the next command needs a new one. Read -> check -> append runs under an ``O_EXCL``
lock beside the log (stale after :data:`STALE_LOCK_S`, broken by an atomic rename),
re-reading the log once held. The lock is only an optimisation: the single arbiter is
an ``O_EXCL`` marker file per entry (:func:`override_marker.marker`), created before the CONSUMED line
is written; whoever fails to create it did not win. Every pass-through says so in a
visible WARN. An entry needs a timestamp, the hook name and a non-empty reason; one
dated in the future (beyond :data:`CLOCK_SKEW`) is ignored; a malformed line is skipped.
A matching entry outside its window is named in the block. The log is an INPUT to both
gates, not only an audit trail.

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
``<ts> | <hook> | CONSUMED | <entry timestamp>`` (written here, for attribution). The
marker files under :data:`MARKER_DIR` (untracked) are also read as "consumed": the log
is git-tracked, so a ``git restore`` of it drops the CONSUMED line and would revive the
entry for the rest of its window. A marker that cannot be created blocks (fail closed);
only ``git clean -x`` or a fresh clone loses them.
"""

from __future__ import annotations

import os
import re
import shlex
import time
import uuid
from contextlib import contextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

from override_marker import MARKER_DIR, sweep  # noqa: F401 - MARKER_DIR is part of the API
from override_marker import marker as marker_path
from override_marker import used as marker_used

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
    moment = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    try:
        moment.astimezone(timezone.utc)  # year 1 / 9999 with an offset overflows later
    except (OverflowError, ValueError):
        return None
    return moment


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
    """Every OVERRIDE entry for *hook* with a reason and no CONSUMED line or marker naming it."""
    try:
        lines = (Path(project_root) / LOG_RELPATH).read_text(
            encoding="utf-8-sig", errors="replace").splitlines()  # an editor's BOM
    except OSError:
        return []
    entries = list(_entries(lines, hook))
    used = {_when(text) for kind, _at, text in entries if kind == "CONSUMED"}
    return [Override(at, reason) for kind, at, reason in entries
            if kind == "OVERRIDE" and reason and at not in used
            and not marker_used(project_root, hook, at)]


def _in_window(found: Override, now: datetime) -> bool:
    return -CLOCK_SKEW <= now - found.at <= WINDOW


def active_override(project_root: str | Path, hook: str,
                    now: datetime | None = None) -> Override | None:
    """The newest unconsumed entry for *hook* still inside its window, else ``None``."""
    now = now or datetime.now(timezone.utc)
    live = (found for found in _unconsumed(project_root, hook) if _in_window(found, now))
    return max(live, default=None, key=lambda found: found.at)


def _unapplied(project_root: str | Path, hook: str, now: datetime) -> str | None:
    """Why the newest unconsumed entry for *hook* outside its window was not applied."""
    stale = (found for found in _unconsumed(project_root, hook) if not _in_window(found, now))
    found = max(stale, default=None, key=lambda entry: entry.at)
    if found is None:
        return None
    why = (f"it is dated more than {int(CLOCK_SKEW.total_seconds())} s in the future "
           "(a pre-dated entry is ignored)" if found.at > now else
           f"it is older than the {int(WINDOW.total_seconds() // 60)}-minute window")
    return f"the logged override of {_stamp(found.at)} was NOT applied: {why}"


def _break_stale(lock: Path) -> bool:
    """Remove a stale *lock* by claiming it with an atomic rename, then re-checking it.

    Of several breakers exactly one wins the rename; the others see the file gone. The
    winner re-reads the age of what it actually renamed: a lock another breaker had
    already replaced by a fresh one is put back (``os.link`` refuses to overwrite).
    ``False`` when the lock could not be renamed (the caller then waits like for a live one).
    """
    claimed = lock.with_name(f"{uuid.uuid4().hex}.{lock.name}")  # still matches *.log.lock (ignored)
    try:
        os.rename(lock, claimed)
    except OSError:
        return False
    try:
        if time.time() - claimed.stat().st_mtime <= STALE_LOCK_S:  # we took a live one
            os.link(claimed, lock)  # refuses to overwrite a third party's new lock
    except OSError:
        pass
    with suppress(OSError):
        claimed.unlink()
    return True


@contextmanager
def _locked(log: Path):
    """Hold ``<log>.lock`` (created ``O_EXCL``) for the block; a stale one is broken.

    Raises ``TimeoutError`` after :data:`LOCK_WAIT_S`, ``OSError`` when it cannot be made.
    """
    lock = log.with_name(log.name + ".lock")
    deadline = time.monotonic() + LOCK_WAIT_S
    token = uuid.uuid4().hex  # who owns it: only the owner removes it
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, token.encode())
            finally:
                os.close(fd)
            break
        except (FileExistsError, PermissionError) as exc:  # PermissionError: Windows, delete pending
            try:
                if time.time() - lock.stat().st_mtime > STALE_LOCK_S and _break_stale(lock):
                    continue  # its holder died: broken atomically
            except FileNotFoundError:
                if isinstance(exc, PermissionError):  # gone yet not creatable: delete-pending or read-only
                    if time.monotonic() >= deadline:
                        raise exc from None  # fail closed, after the wait a pending delete needs
                    time.sleep(0.05)
                continue  # released meanwhile: retry
            except OSError:
                pass  # cannot tell its age: wait for it like a live one
            if time.monotonic() >= deadline:
                raise TimeoutError(f"{lock} is held") from None
            time.sleep(0.05)
    try:
        yield
    finally:
        try:  # a lock broken from under us and re-taken is the new owner's, not ours
            if lock.read_text(encoding="utf-8") == token:
                lock.unlink()
        except OSError:
            pass


def consume(project_root: str | Path, hook: str, found: Override,
            now: datetime | None = None) -> str | None:
    """Record that *found* let a command through; a WARN sentence when it cannot be.

    The ``O_EXCL`` marker is the arbiter (losing it means a concurrent command used the
    entry); the CONSUMED log line is the visible record. Either failing keeps the block.
    """
    now = now or datetime.now(timezone.utc)
    marker = marker_path(project_root, hook, found.at)
    try:
        if not marker.parent.is_dir():
            marker.parent.mkdir(parents=True)  # a file in its place: OSError, not "concurrent"
        os.close(os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        sweep(marker.parent, WINDOW + CLOCK_SKEW + timedelta(minutes=10))
    except FileExistsError as exc:
        if exc.filename and Path(exc.filename) == marker.parent:
            return ("the logged override could not be marked used (FileExistsError), so it "
                    "is NOT applied: .shipwright/locks is not a directory")
        return ("the logged override was used by a concurrent command first, so it is "
                "NOT applied here")
    except OSError as exc:
        return (f"the logged override could not be marked used ({type(exc).__name__}), so it "
                "is NOT applied: make .shipwright/locks writable, then re-run")
    line = f"{_stamp(now)} | {hook} | CONSUMED | {found.at.isoformat()}\n"
    try:
        with open(Path(project_root) / LOG_RELPATH, "a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell():
                handle.seek(-1, os.SEEK_END)
                if handle.read(1) not in (b"\n", b"\r"):
                    line = "\n" + line  # an editor left no newline: never glue onto that line
            handle.write(line.encode("utf-8"))
    except OSError as exc:
        marker.unlink(missing_ok=True)  # unused after all: let the block stand, retry possible
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
        return None, (f"the override log could not be locked ({type(exc).__name__}: {exc}), "
                      "so the override is NOT applied: re-run, or delete that lock file")
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
