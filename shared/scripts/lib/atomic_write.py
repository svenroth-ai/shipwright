"""Durable, atomic single-file writes — the shared ``tmp + fsync + os.replace``
primitive every ``shipwright_*`` config / state / log writer routes through.

``os.replace`` alone prevents a **torn read** (a concurrent reader sees either
the whole old file or the whole new one, never a partial write) but NOT a
**lost write**: a crash or power-loss after ``os.replace`` returns — but before
the OS flushes the page cache — can leave the file empty or stale. Closing that
gap requires two extra steps the bare ``tmp + replace`` pattern omits:

  * ``fsync`` the temp file *before* the rename, so its bytes are on stable
    storage when the rename publishes it, and
  * a best-effort ``fsync`` of the *containing directory* *after* the rename,
    so the directory entry (the rename itself) survives a crash too.

This is orthogonal to ``file_lock`` / ``run_config_store`` — those serialize
*concurrent* writers; this makes a *single* writer's bytes durable. The two
compose.

**Windows: a concurrent READER can defeat the rename.** ``os.replace`` is atomic
on Windows only when it *succeeds*. Windows refuses to replace a file that any
process holds open without ``FILE_SHARE_DELETE``, and CPython's ``open()`` does
not request it — so a plain reader is enough to make the call raise
``PermissionError`` (``WinError`` 5 ``ACCESS_DENIED`` / 32 ``SHARING_VIOLATION``)
and the write is lost. Locking does not close this: the run-config design
deliberately permits unlocked readers (``_read_standalone_flag`` reads on every
``update_step``), and the WebUI, an editor, an indexer or antivirus are outside
our locking discipline entirely. The rename is therefore retried for
:data:`REPLACE_RETRY_BUDGET_SECONDS` while the violation persists, then re-raised
— a held-open destination must fail loudly, never silently drop the write.
Found via F0 race card ``f0-race:shipwright-run``, which was neither inter-unit
pollution nor an unreliable test but this bug, surfaced by CPU contention.

Two limits of this, stated so the retry is not mistaken for closure:

  * It is a **mitigation for holders we do not control**. Our own unlocked
    reader (``orchestrator_pkg.step_planning._read_standalone_flag``, run on
    every ``update_step``) remains a deliberate trade-off recorded there, not
    something this closes — under sustained polling a writer can still burn the
    whole budget and fail.
  * A retry that SUCCEEDS is silent. Nothing counts or reports it, so this
    module cannot tell you that the unlocked-reader assumption is degrading;
    it only stops that degradation from costing a write. Wiring an actual
    signal out of a primitive with 30 call sites is a design decision, tracked
    separately rather than smuggled in here.

``atomic_write`` is a unique top-level module name (like ``file_lock``), so it
imports cleanly both as ``lib.atomic_write`` (when ``shared/scripts`` is on the
path) and as ``atomic_write`` (when ``shared/scripts/lib`` is, e.g. from a
plugin doing the ``parents[4]`` shared-lib insert).
"""
from __future__ import annotations

import contextlib
import os
import tempfile
import time
from pathlib import Path

__all__ = ["durable_atomic_write", "durable_read_bytes", "durable_read_text",
           "REPLACE_RETRY_BUDGET_SECONDS", "READ_RETRY_BUDGET_SECONDS"]

#: Windows codes seen when someone else has the destination open. Measured on
#: Windows 11: a plain reader, a memory-mapped holder (what AV/indexers do) and
#: a byte-range lock ALL surface as ``PermissionError`` winerror 5; 32 is kept
#: because ``ERROR_SHARING_VIOLATION`` is documented for this path.
#:
#: **5 is ambiguous and we cannot fix that.** ``ERROR_ACCESS_DENIED`` is equally
#: what a read-only destination, a deny-ACL, or a destination that is a
#: directory returns (all three measured). Those now stall for the budget below
#: before failing. Accepted knowingly: a bounded stall that still fails loudly
#: beats silently losing a write, and the two are indistinguishable at this
#: layer.
_SHARING_VIOLATION_WINERRORS = frozenset({5, 32})
#: How long a transient holder may keep the destination before the write fails.
#: Deliberately SHORT. A config read is ~1 ms, so this is still ~500x headroom,
#: and every extra millisecond is paid twice: a genuine denial (winerror 5, see
#: above) stalls this long before surfacing, and — more seriously — the window
#: in which an UNLOCKED writer can publish a stale snapshot grows with it.
#: ``orchestrator_pkg.config_io.save_run_config`` documents that the advisory
#: lock is held by its callers and not by the writer, so such writers exist:
#: a longer budget would let a stale write that used to lose the race land on
#: top of a newer one. Bounded-and-loud is the goal, not maximal patience.
REPLACE_RETRY_BUDGET_SECONDS = 0.5
#: The READ budget is deliberately LONGER than the write budget, and the
#: asymmetry is the point. Waiting longer to read cannot publish anything, so it
#: carries none of the stale-write risk that keeps the write budget short — the
#: worst a patient reader costs is latency. It needs to be longer because a
#: reader can be *starved*: measured under 12 concurrent copies, three writer
#: processes doing 40 replaces each keep the entry delete-pending often enough
#: that a 0.5 s reader still gave up (1 failure in 36), while a longer budget
#: did not. Tie the two together and one of the two failure modes always wins.
READ_RETRY_BUDGET_SECONDS = 2.0
_RETRY_INITIAL_SLEEP_SECONDS = 0.005
_RETRY_MAX_SLEEP_SECONDS = 0.1


def durable_atomic_write(path: Path | str, data: str | bytes) -> None:
    """Write ``data`` to ``path`` durably and atomically.

    ``str`` is encoded UTF-8 and written verbatim — no newline translation, no
    invented trailing newline — so callers keep full control of line endings
    and serialization (each keeps its own ``json.dumps(...)`` line).

    Sequence: write to a same-directory temp file → ``fsync`` it → ``os.replace``
    onto ``path`` (atomic on POSIX; on Windows retried past a concurrent reader,
    see the module docstring) → best-effort directory fsync. On any failure the
    temp file is removed and the original error re-raised, so ``path`` is never
    left pointing at a half-written temp.
    """
    path = Path(path)
    raw = data.encode("utf-8") if isinstance(data, str) else data
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())
        _replace_retrying_sharing_violations(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    _fsync_parent_dir(path.parent)


def _is_windows() -> bool:
    """The one platform predicate this module branches on.

    Exists so tests can force either branch WITHOUT monkeypatching ``os.name``.
    That patch looks equivalent and is not: ``os.name`` is process-global and
    ``pathlib.Path()`` dispatches on it, so forcing it makes ``Path(...)``
    build the foreign flavour and raise ``NotImplementedError`` before any code
    here runs — observed in both directions (``"posix"`` on a Windows host,
    ``"nt"`` on POSIX CI).
    """
    return os.name == "nt"


def _retry_past_sharing_violations(operation, budget_seconds: float):
    """Run ``operation`` (zero-arg), retrying while Windows says "file in use".

    POSIX has no such failure mode, so it runs the operation once and its
    behaviour is unchanged — a ``PermissionError`` there is real and propagates
    at once. On Windows only :data:`_SHARING_VIOLATION_WINERRORS` are treated as
    transient; the budget is bounded and exhausting it re-raises the original
    error, so a file that is genuinely locked open fails loudly.

    The sleep is clamped to the time actually left, so the last attempt happens
    at the deadline rather than up to one backoff step past it — the budget a
    caller configures is the budget it gets.
    """
    if not _is_windows():
        return operation()
    deadline = time.monotonic() + budget_seconds
    delay = _RETRY_INITIAL_SLEEP_SECONDS
    while True:
        try:
            return operation()
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in _SHARING_VIOLATION_WINERRORS:
                raise
            # Capped by the budget as well as by the deadline. `deadline` is
            # `t0 + budget`, and floating point makes `(t0 + budget) - t0` slightly
            # LARGER than `budget` once t0 is big — monotonic() counts from boot, so
            # the error lands around 2**-31 s. Both reads also fall in the same clock
            # tick here (Windows granularity is ~15 ms), so the first retry would sleep
            # marginally past the budget the caller configured. Microscopic in effect,
            # but this function's contract is that the budget is exact.
            remaining = min(deadline - time.monotonic(), budget_seconds)
            if remaining <= 0:
                raise
            time.sleep(min(delay, remaining))
            delay = min(delay * 2, _RETRY_MAX_SLEEP_SECONDS)


def _replace_retrying_sharing_violations(tmp: str, path: Path) -> None:
    """``os.replace``, retried while Windows reports the destination as in use."""
    _retry_past_sharing_violations(lambda: os.replace(tmp, path),
                                   REPLACE_RETRY_BUDGET_SECONDS)


def durable_read_text(path: Path | str, *, encoding: str = "utf-8") -> str:
    """Read a file whose publisher may be mid-``os.replace``.

    The mirror image of the write side, and needed for the same reason. When a
    writer replaces a file that someone still has open, Windows leaves the old
    entry *delete-pending*: a reader's ``open()`` then fails with
    ``PermissionError`` until the last handle goes. So hardening only the writer
    moves the failure rather than removing it — measured, the concurrent
    run-config test went from failing in ``os.replace`` to failing in
    ``load_run_config``'s ``read_text``, because a fix that lets more writes
    SUCCEED also creates more of these windows.

    Callers that read a file published by :func:`durable_atomic_write` should
    read it through here. A file that stays unreadable past the budget still
    raises, so a genuine permissions problem is not hidden — it is just no
    longer confused with a neighbour's in-flight publish.
    """
    target = Path(path)
    return _retry_past_sharing_violations(
        lambda: target.read_text(encoding=encoding), READ_RETRY_BUDGET_SECONDS)


def durable_read_bytes(path: Path | str) -> bytes:
    """:func:`durable_read_text` without the decode — for content that must round-trip.

    Same retry, different contract. Reading a file as TEXT applies universal-newline
    translation, so bytes read through :func:`durable_read_text` and written back are
    not the bytes that were there: a CRLF file comes back LF. A caller that carries a
    file across an operation and restores it needs this one.
    """
    target = Path(path)
    # `lambda`, not the bound `target.read_bytes`: it re-resolves `Path.read_bytes` on
    # every attempt, exactly like the text reader one function up. Indistinguishable in
    # production — but the two are meant to be the same shape, and the sibling test that
    # exists to catch one being hardened without the other cannot see a difference it
    # is itself blind to.
    return _retry_past_sharing_violations(
        lambda: target.read_bytes(), READ_RETRY_BUDGET_SECONDS)


def _fsync_parent_dir(directory: Path) -> None:
    """Best-effort ``fsync`` of ``directory`` so the rename survives a crash.

    POSIX-only: Windows cannot open a directory for ``fsync`` (and NTFS makes
    the replace durable on its own). Any error is swallowed — directory fsync is
    a durability nicety, not a correctness requirement, and some filesystems
    legitimately reject it.
    """
    if _is_windows():
        return
    dir_fd = None
    try:
        dir_fd = os.open(str(directory), os.O_RDONLY)
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        if dir_fd is not None:
            with contextlib.suppress(OSError):
                os.close(dir_fd)
