"""Stdlib-only cross-process writer lease for the plugin-cache bootstrap."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import shlex
import stat
import time
from pathlib import Path


_CLAIM_DIRNAME = ".sessionstart-claims"
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
_WINDOWS_LOCK_BYTES = 65
CACHE_LOCK_NAME = ".sessionstart-cache-repair.lock"
CLAIM_TTL_SECONDS = 30.0
COMPLETION_CLOCK_SKEW_SECONDS = 1.0
# Bounded settle sleep on the UN-ENUMERABLE path only (`peers is None` or fewer
# than 2), where there is no peer set to wait on. It no longer probes for a
# fan-out's existence — that was the #543 defect.
_FANOUT_PROBE_SECONDS = 0.1
# How long to wait for the FIRST peer before concluding the configured fan-out
# is not actually running this session. Measured max first-peer arrival under
# 22-core saturation: 0.41s (iterate-2026-08-06-parallel-global-state-tests).
_FANOUT_ARRIVAL_GRACE_SECONDS = 1.0
# How long to keep waiting after the LAST new peer joined. Measured max
# inter-arrival gap under the same saturation: 0.41s.
_FANOUT_IDLE_SECONDS = 1.0
# Hard ceiling, anchored at entry and never reset by a late arrival. Measured
# max full 12-way fan-out: 1.36s.
#
# The BINDING neighbour is ensure_shared_cache's _CLAIM_WAIT_SECONDS (5.0), not
# run_if_cache_ready's _READY_WAIT_SECONDS (10.0): a peer queued inside
# _claim_session gives up after _CLAIM_WAIT_SECONDS and enters the recovering-
# owner path.
#
# What that costs is a STALL, not a duplicate scan — do not restate it as one.
# The recovering peer takes the writer lock, finds session_repair_state already
# True and returns without scanning, so a published generation is still
# honoured; it only scans when the owner genuinely failed to publish, which is
# the designed recovery. So this inequality buys SessionStart latency and lock
# contention (a 5s stall plus a spurious "owner timed out" line), and the
# barrier must not consume the peers' patience for that reason.
# It does not follow that barrier + lock-wait fits inside it — see the
# composition note in the iterate spec; that budget is not proven here and this
# constant is not what would carry it.
_FANOUT_WAIT_SECONDS = 3.0


def _opened_regular_at_path(path: Path, fd: int) -> bool:
    """Validate the opened object and pathname as the same regular file."""
    try:
        opened = os.fstat(fd)
        named = path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISREG(opened.st_mode)
        and stat.S_ISREG(named.st_mode)
        and opened.st_nlink == named.st_nlink == 1
        and (opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino)
    )


def read_claim_token(path: Path) -> str | bool | None:
    """Read a small regular claim through one validated, nonblocking fd."""
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return False
    except OSError:
        return None
    try:
        if not _opened_regular_at_path(path, fd):
            return None
        raw = os.read(fd, 64)
        if os.read(fd, 1):
            return None
    except OSError:
        return None
    finally:
        os.close(fd)
    try:
        return raw.decode("ascii").strip()
    except UnicodeError:
        return None


def read_completion_age(path: Path) -> float | bool | None:
    """Read completion freshness from one validated, nonblocking fd."""
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return False
    except OSError:
        return None
    try:
        if not _opened_regular_at_path(path, fd):
            return None
        mtime = os.fstat(fd).st_mtime
        age = time.time() - mtime
    except OSError:
        return None
    finally:
        os.close(fd)
    return age


def _completion_observer_marker(done: Path, observer: str) -> Path:
    identity = f"{done.name}\0{observer}".encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()[:32]
    return done.with_name(f"observed-{digest}.seen")


def observe_completion(done: Path, observer: str) -> bool | None:
    """Return true on this observer's first sight of an immutable generation."""
    marker = _completion_observer_marker(done, observer)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(marker, flags, 0o600)
    except FileExistsError:
        return False
    except OSError:
        return None
    os.close(fd)
    return True


def has_completion_observation(done: Path, observer: str) -> bool | None:
    """Return whether a safe marker records this observer for the generation."""
    marker = _completion_observer_marker(done, observer)
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(marker, flags)
    except FileNotFoundError:
        return False
    except OSError:
        return None
    try:
        if not _opened_regular_at_path(marker, fd):
            return None
        return os.read(fd, 1) == b""
    except OSError:
        return None
    finally:
        os.close(fd)


def _installed_fanout_participants(
    cache_root: Path, participant: str,
) -> tuple[str, ...] | None:
    """Read active, SessionStart-registered peers from Claude's manifest."""
    if ":" not in participant:
        return ()
    manifest = cache_root.parent.parent / "installed_plugins.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        plugins = data.get("plugins")
        if not isinstance(plugins, dict):
            return None
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    mode = participant.rsplit(":", 1)[1]
    cache_name = os.path.normcase(os.path.abspath(cache_root))
    peers: set[str] = set()
    for key, entries in plugins.items():
        if not isinstance(key, str) or not key.endswith("@shipwright") or \
                not isinstance(entries, list) or not entries:
            continue
        entry = entries[0]
        install = entry.get("installPath") if isinstance(entry, dict) else None
        if not isinstance(install, str) or not install:
            continue
        install_path = Path(install)
        if os.path.normcase(os.path.abspath(install_path.parent.parent)) != \
                cache_name:
            continue
        try:
            hooks = json.loads(
                (install_path / "hooks" / "hooks.json").read_text(
                    encoding="utf-8",
                ),
            )
            session = hooks.get("hooks", {}).get("SessionStart", [])
            command_hooks = [
                hook
                for group in session if isinstance(group, dict)
                for hook in group.get("hooks", []) if isinstance(hook, dict)
                if hook.get("type") == "command"
            ]
        except (AttributeError, OSError, TypeError, UnicodeError,
                json.JSONDecodeError):
            continue
        commands: list[list[str]] = []
        for hook in command_hooks:
            command = hook.get("command")
            if not isinstance(command, str):
                continue
            try:
                commands.append(shlex.split(command, posix=os.name != "nt"))
            except ValueError:
                continue
        if any(
            Path(token.strip("\"'")).name == "run_if_cache_ready.py"
            for command in commands for token in command
        ):
            peers.add(f"{install_path.parent.name}:{mode}")
    return tuple(sorted(peers)) if participant in peers else ()


def await_fanout_observers(cache_root: Path, done: Path,
                           participant: str) -> None:
    """Let an observed active-plugin fan-out join before repair is published."""
    peers = _installed_fanout_participants(cache_root, participant)
    if peers is None or len(peers) < 2:
        time.sleep(_FANOUT_PROBE_SECONDS)
        return
    started = time.monotonic()
    hard_deadline = started + _FANOUT_WAIT_SECONDS
    arrived: set[str] = set()
    last_arrival: float | None = None
    while True:
        # Rescan every pass and evaluate deadlines only AFTER updating state,
        # so a marker that landed during the last sleep cannot be missed by an
        # expiry decision taken on stale state. `present` is rebuilt rather
        # than accumulated: an observation marker is valid only while it stays
        # zero bytes, so a marker that stops validating must stop counting
        # toward completion.
        present: set[str] = set()
        for peer in peers:
            state = has_completion_observation(done, peer)
            # An unreadable marker means "cannot tell yet", NOT "no fan-out".
            # Abandoning here reproduced the very defect this barrier fixes: on
            # Windows a transient sharing violation against one just-created
            # marker — a virus scanner or the indexer touching it — used to
            # publish the generation with 1/12 observed and send eleven peers
            # into their own re-election. Keep polling instead; `hard_deadline`
            # already bounds a marker that never becomes readable.
            if state is True:
                present.add(peer)
        if len(present) == len(peers):
            return
        now = time.monotonic()
        # The ceiling is anchored at entry and is never reset, so a steady
        # trickle of arrivals cannot hold SessionStart open indefinitely.
        if now >= hard_deadline:
            return
        # Progress is a NEW member of the EXPECTED peer set — tracked by
        # identity, not by a count. A duplicate marker, or one written by an
        # identity outside `peers`, must not extend the wait; the caller's own
        # observation is not an arrival, because one participant is not a
        # fan-out. Identity matters over counting: if B's marker stops
        # validating and C then arrives, the count is 1 again and a
        # count-based rule would miss a genuine arrival. `arrived` only grows,
        # so a marker that later stops validating cannot rewind the idle clock
        # and re-open the wait.
        newcomers = (present - {participant}) - arrived
        if newcomers:
            arrived |= newcomers
            last_arrival = now
        # Waiting on whether peers are still ARRIVING, rather than on a fixed
        # window, is the correction: the previous rule read "nobody here
        # within 0.1s" as "there is no fan-out to wait for", while a peer
        # process needs longer than that merely to spawn on a loaded host.
        idle_deadline = (
            started + _FANOUT_ARRIVAL_GRACE_SECONDS if last_arrival is None
            else last_arrival + _FANOUT_IDLE_SECONDS
        )
        if now >= idle_deadline:
            return
        # Clamp the poll to the nearest deadline. A flat 0.01 would step PAST
        # the ceiling and return on the following pass, so the barrier would
        # exceed the bound it advertises by up to one poll interval. Both
        # deltas are strictly positive here — the two checks above already
        # returned on expiry.
        time.sleep(min(0.01, hard_deadline - now, idle_deadline - now))


def session_event_key(payload: object) -> str:
    """Stable fan-out key derived only from immutable stdin payload values."""
    if not isinstance(payload, dict):
        return ""
    session_id = payload.get("session_id")
    if (
        not isinstance(session_id, str)
        or not session_id.strip()
        or session_id == "unknown"
    ):
        return ""
    sid = session_id
    source = payload.get("source") if isinstance(payload.get("source"), str) else ""
    transcript = payload.get("transcript_path")
    transcript = transcript if isinstance(transcript, str) else ""
    return json.dumps(
        [sid, source, transcript], ensure_ascii=True, separators=(",", ":"),
    )


def session_repair_state(cache_root: Path, session_id: object) -> bool | None:
    """Return true/false for a readable chain, None for unsafe/unreadable state."""
    if not isinstance(session_id, str):
        return None
    sid = session_id.strip()
    if not sid or sid == "unknown":
        return None
    directory = cache_root / _CLAIM_DIRNAME
    key = hashlib.sha256(sid.encode("utf-8")).hexdigest()[:32]
    prefix = f"ensure-shared-cache-{key}"
    claim = directory / f"{prefix}.claim"
    for _ in range(1024):
        token = read_claim_token(claim)
        if token is False:
            return False
        if token is None:
            return None
        assert isinstance(token, str)
        if not _TOKEN_RE.fullmatch(token):
            return None
        successor = directory / f"{prefix}-{token}.next"
        try:
            successor_stat = successor.lstat()
        except FileNotFoundError:
            successor_stat = None
        except OSError:
            return None
        if successor_stat is not None:
            if stat.S_ISLNK(successor_stat.st_mode) or not stat.S_ISREG(
                successor_stat.st_mode,
            ):
                return None
            claim = successor
            continue
        age = read_completion_age(directory / f"{prefix}-{token}.done")
        if age is False:
            return False
        if age is None:
            return None
        assert isinstance(age, float)
        return -COMPLETION_CLOCK_SKEW_SECONDS <= age < CLAIM_TTL_SECONDS
    return None


def session_repair_complete(cache_root: Path, session_id: object) -> bool:
    """Return true only for the completed tip of an immutable claim chain."""
    return session_repair_state(cache_root, session_id) is True


def _acquire_cache_lock(
    path: Path, wait_seconds: float, *, exclusive: bool,
) -> int | tuple[int, int] | None:
    """Acquire a bounded writer or concurrent-reader OS lease."""
    fd: int | None = None
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.parent.is_symlink():
            return None
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NONBLOCK", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        if not _opened_regular_at_path(path, fd):
            raise OSError("cache lock is not a stable regular file")
        windows = os.name == "nt"
        if windows:
            import msvcrt

            if os.fstat(fd).st_size < _WINDOWS_LOCK_BYTES:
                os.lseek(fd, _WINDOWS_LOCK_BYTES - 1, os.SEEK_SET)
                os.write(fd, b"\0")
                os.fsync(fd)
        else:
            import fcntl

        deadline = time.monotonic() + max(0.0, wait_seconds)
        while True:
            try:
                if windows:
                    offsets = (0,) if exclusive else range(1, _WINDOWS_LOCK_BYTES)
                    acquired = None
                    for offset in offsets:
                        try:
                            os.lseek(fd, offset, os.SEEK_SET)
                            length = _WINDOWS_LOCK_BYTES if exclusive else 1
                            msvcrt.locking(fd, msvcrt.LK_NBLCK, length)
                            acquired = offset
                            break
                        except OSError as exc:
                            if exc.errno not in (errno.EACCES, errno.EAGAIN):
                                raise
                    if acquired is None:
                        raise BlockingIOError(errno.EACCES, "cache lease busy")
                    return fd if exclusive else (fd, acquired)
                else:
                    kind = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
                    fcntl.flock(fd, kind | fcntl.LOCK_NB)
                return fd
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError("cache writer lease timed out") from exc
                time.sleep(0.01)
    except OSError:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        return None


def acquire_cache_lock(path: Path, wait_seconds: float = 5.0) -> int | None:
    """Acquire the OS writer lease within a bounded monotonic deadline."""
    result = _acquire_cache_lock(path, wait_seconds, exclusive=True)
    return result if isinstance(result, int) else None


def acquire_cache_read_lock(
    path: Path, wait_seconds: float = 5.0,
) -> int | tuple[int, int] | None:
    """Acquire a concurrent reader lease that excludes cache repair writers."""
    return _acquire_cache_lock(path, wait_seconds, exclusive=False)


def unlock_cache_lock(handle: int | tuple[int, int]) -> None:
    """Release the OS lease while leaving descriptor ownership to the caller."""
    fd, offset = handle if isinstance(handle, tuple) else (handle, 0)
    if os.name == "nt":
        import msvcrt

        os.lseek(fd, offset, os.SEEK_SET)
        length = 1 if isinstance(handle, tuple) else _WINDOWS_LOCK_BYTES
        msvcrt.locking(fd, msvcrt.LK_UNLCK, length)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


def release_cache_lock(handle: int | tuple[int, int]) -> None:
    """Release the OS lease and close its descriptor."""
    fd = handle[0] if isinstance(handle, tuple) else handle
    try:
        unlock_cache_lock(handle)
    finally:
        os.close(fd)
