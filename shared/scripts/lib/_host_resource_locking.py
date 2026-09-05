"""Private OS-lock and namespace-hardening primitives for host leases."""

from __future__ import annotations

import errno
import os
import stat as statmod
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class HostLeaseError(RuntimeError):
    """The shared lease namespace cannot be trusted or updated."""


_OWNER_REGISTRY_LOCK = threading.Lock()
_OWNER_REGISTRY_PID = os.getpid()
_LIVE_OWNER_TICKETS: set[str] = set()
_MUTEX_REGISTRY_PID = os.getpid()
_PROCESS_MUTEXES: dict[str, threading.Lock] = {}


def _ticket_key(path: Path) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def _register_owner_ticket(path: Path) -> None:
    global _OWNER_REGISTRY_PID
    with _OWNER_REGISTRY_LOCK:
        current_pid = os.getpid()
        if _OWNER_REGISTRY_PID != current_pid:
            _LIVE_OWNER_TICKETS.clear()
            _OWNER_REGISTRY_PID = current_pid
        _LIVE_OWNER_TICKETS.add(_ticket_key(path))


def _forget_owner_ticket(path: Path) -> None:
    with _OWNER_REGISTRY_LOCK:
        if _OWNER_REGISTRY_PID == os.getpid():
            _LIVE_OWNER_TICKETS.discard(_ticket_key(path))


def _owned_by_this_process(path: Path) -> bool:
    with _OWNER_REGISTRY_LOCK:
        return (_OWNER_REGISTRY_PID == os.getpid()
                and _ticket_key(path) in _LIVE_OWNER_TICKETS)


def _process_mutex(path: Path) -> threading.Lock:
    global _MUTEX_REGISTRY_PID
    key = _ticket_key(path)
    with _OWNER_REGISTRY_LOCK:
        current_pid = os.getpid()
        if _MUTEX_REGISTRY_PID != current_pid:
            _PROCESS_MUTEXES.clear()
            _MUTEX_REGISTRY_PID = current_pid
        return _PROCESS_MUTEXES.setdefault(key, threading.Lock())


def _is_reparse(path: Path) -> bool:
    try:
        stat = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise HostLeaseError(f"could not inspect host lease path {path}: {exc}") from exc
    flag = getattr(stat, "st_file_attributes", 0)
    reparse = getattr(statmod, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return path.is_symlink() or bool(flag & reparse)


def _windows_private(path: Path) -> tuple[bool, str]:
    from scripts.lib._windows_acl import path_acl_is_private
    return path_acl_is_private(path)


def _tighten(path: Path, mode: int, *, kind: str) -> None:
    """POSIX only: owned by us but loosened by something outside our control
    (a bash `>` redirect honors the process umask) — tighten rather than
    reject. Ownership, checked by the caller, is the trust boundary, not the
    mode bits, once _is_reparse has ruled out a planted link."""
    try:
        path.chmod(mode)
    except OSError as exc:
        raise HostLeaseError(f"could not tighten host lease {kind} permissions {path}: {exc}") from exc


def _reject_linked_components(path: Path) -> None:
    target = path.absolute()
    current = Path(target.anchor)
    for part in target.parts[1:]:
        current /= part
        if _is_reparse(current):
            raise HostLeaseError(f"unsafe host lease path component: {current}")


def _safe_file(path: Path, *, allow_missing: bool = False) -> None:
    if _is_reparse(path):
        raise HostLeaseError(f"unsafe host lease file: {path}")
    if not path.exists():
        if allow_missing:
            return
        raise HostLeaseError(f"host lease file is missing: {path}")
    if not path.is_file():
        raise HostLeaseError(f"unsafe host lease file: {path}")
    if os.name == "nt":
        private, reason = _windows_private(path)
        if not private:
            raise HostLeaseError(f"host lease file is not private: {path}: {reason}")
    else:
        try:
            stat = path.stat()
        except OSError as exc:
            raise HostLeaseError(f"could not inspect host lease file {path}: {exc}") from exc
        if hasattr(os, "getuid") and stat.st_uid != os.getuid():
            raise HostLeaseError(f"host lease file is owned by another user: {path}")
        if stat.st_mode & 0o077:
            _tighten(path, 0o600, kind="file")


def _safe_runtime_root(path: Path, *, allow_sticky_shared: bool) -> None:
    _reject_linked_components(path)
    if not path.is_dir():
        raise HostLeaseError(f"unsafe host lease runtime root: {path}")
    if os.name == "nt":
        private, reason = _windows_private(path)
        if not private:
            raise HostLeaseError(f"host lease runtime root is not private: {path}: {reason}")
        return
    try:
        info = path.stat()
    except OSError as exc:
        raise HostLeaseError(f"could not inspect host lease runtime root {path}: {exc}") from exc
    current_uid = os.getuid() if hasattr(os, "getuid") else info.st_uid
    if info.st_uid not in {0, current_uid}:
        raise HostLeaseError(f"host lease runtime root has an untrusted owner: {path}")
    sticky_shared = (allow_sticky_shared and bool(info.st_mode & statmod.S_ISVTX)
                     and info.st_uid in {0, current_uid})
    exposed = info.st_mode & 0o077
    if allow_sticky_shared and not sticky_shared:
        raise HostLeaseError(f"host lease runtime root lacks sticky rename protection: {path}")
    if not allow_sticky_shared and exposed:
        raise HostLeaseError(f"host lease runtime root is not private or sticky: {path}")


def _posix_shared_temp_root() -> Path:
    """Select only a fixed platform temp root; never trust an env-selected path."""
    for candidate in (Path("/tmp"), Path("/var/tmp"), Path("/usr/tmp")):
        try:
            if candidate.is_dir():
                return candidate.resolve(strict=True)
        except OSError:
            continue
    raise HostLeaseError("no approved POSIX shared temporary root is available")


def _safe_dir(path: Path, *, trusted_parent: Path) -> None:
    """Create *path* without traversing an untrusted link below a trusted root."""
    target = path.absolute()
    anchor = trusted_parent.absolute()
    try:
        relative = target.relative_to(anchor)
    except ValueError as exc:
        raise HostLeaseError(
            f"host lease directory escapes trusted root {anchor}: {target}") from exc
    if not relative.parts:
        raise HostLeaseError(f"host lease directory must be below trusted root: {target}")

    current = anchor
    for part in relative.parts:
        current /= part
        created = False
        try:
            current.mkdir(mode=0o700)
            created = True
        except FileExistsError:
            pass
        except OSError as exc:
            raise HostLeaseError(
                f"could not prepare host lease directory {current}: {exc}") from exc
        if _is_reparse(current) or not current.is_dir():
            raise HostLeaseError(f"unsafe host lease directory: {current}")
        if os.name == "nt":
            private, reason = _windows_private(current)
            if not private:
                raise HostLeaseError(
                    f"host lease directory is not private: {current}: {reason}")
        else:
            try:
                if created:
                    current.chmod(0o700)
                stat = current.stat()
            except OSError as exc:
                raise HostLeaseError(
                    f"could not inspect host lease directory {current}: {exc}") from exc
            if hasattr(os, "getuid") and stat.st_uid != os.getuid():
                raise HostLeaseError(
                    f"host lease directory is owned by another user: {current}")
            if stat.st_mode & 0o077:
                _tighten(current, 0o700, kind="directory")


def _lock_byte(handle, *, blocking: bool) -> bool:
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
            msvcrt.locking(handle.fileno(), mode, 1)
        else:
            import fcntl
            mode = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
            fcntl.lockf(handle.fileno(), mode, 1, 0, os.SEEK_SET)
        return True
    except OSError as exc:
        if not blocking and exc.errno in {errno.EACCES, errno.EAGAIN}:
            return False
        raise HostLeaseError(f"host lease OS lock failed: {exc}") from exc


def _unlock_byte(handle) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.lockf(handle.fileno(), fcntl.LOCK_UN, 1, 0, os.SEEK_SET)


@contextmanager
def _mutex(path: Path) -> Iterator[None]:
    process_lock = _process_mutex(path)
    with process_lock:
        if not path.parent.is_dir():
            raise HostLeaseError(f"host lease mutex parent is missing: {path.parent}")
        _safe_file(path, allow_missing=True)
        try:
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
            handle = os.fdopen(fd, "r+b", buffering=0)
        except OSError as exc:
            raise HostLeaseError(f"could not open host lease mutex {path}: {exc}") from exc
        try:
            _safe_file(path)
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            while not _lock_byte(handle, blocking=False):
                time.sleep(0.01)
            try:
                yield
            finally:
                _unlock_byte(handle)
        finally:
            handle.close()


def _new_owner_lock(tickets: Path, ticket: str):
    path = tickets / f"{ticket}.owner.lock"
    handle = None
    fd = None
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        os.write(fd, b"0")
        handle = os.fdopen(fd, "r+b", buffering=0)
        fd = None  # ownership transferred to handle
        _safe_file(path)
        if not _lock_byte(handle, blocking=True):
            raise HostLeaseError(f"could not lock new ticket {ticket}")
        # POSIX record locks are process-scoped: a second descriptor in this
        # process can otherwise "acquire" and unlock a still-live owner lock.
        _register_owner_ticket(path)
        return path, handle
    except (OSError, HostLeaseError) as exc:
        if handle is not None:
            handle.close()
        elif fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        raise HostLeaseError(f"could not create owner ticket {ticket}: {exc}") from exc


def _probe_dead(ticket_path: Path) -> bool:
    # Missing must fail closed: on POSIX a live, locked inode can be unlinked.
    # Treating a missing pathname as dead could over-grant host capacity.
    try:
        _safe_file(ticket_path)
    except HostLeaseError as exc:
        raise HostLeaseError(f"owner ticket is missing or unsafe: {ticket_path}") from exc
    if _owned_by_this_process(ticket_path):
        return False
    try:
        handle = ticket_path.open("r+b")
    except OSError as exc:
        raise HostLeaseError(f"could not open owner ticket {ticket_path}: {exc}") from exc
    try:
        if not _lock_byte(handle, blocking=False):
            return False
        _unlock_byte(handle)
        return True
    finally:
        handle.close()
