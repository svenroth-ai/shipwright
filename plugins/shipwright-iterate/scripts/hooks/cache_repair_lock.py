"""Stdlib-only cross-process writer lease for the plugin-cache bootstrap."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import stat
import time
from pathlib import Path


_CLAIM_DIRNAME = ".sessionstart-claims"
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
_WINDOWS_LOCK_BYTES = 65
CACHE_LOCK_NAME = ".sessionstart-cache-repair.lock"
CLAIM_TTL_SECONDS = 30.0


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


def observe_completion(done: Path, observer: str) -> bool | None:
    """Return true on this observer's first sight of an immutable generation."""
    identity = f"{done.name}\0{observer}".encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()[:32]
    marker = done.with_name(f"observed-{digest}.seen")
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
        return 0.0 <= age < CLAIM_TTL_SECONDS
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
