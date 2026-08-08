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
``PermissionError`` (the codes, and why each one, live in ``durable_publish``)
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
  * A retry that succeeds is COUNTED but not reported. :func:`sharing_violation_retries`
    exposes the tally (card ``trg-0a294ef3``); deliberately a counter only, with no
    warning and no log line, because a warning has no consumer while a counter does —
    a test can assert an unobstructed write retries zero times. The residual limit is
    that nothing pushes it at you: a caller has to ask, so this module still will not
    volunteer that the unlocked-reader assumption is degrading.

``atomic_write`` is a unique top-level module name (like ``file_lock``), so it
imports cleanly both as ``lib.atomic_write`` (when ``shared/scripts`` is on the
path) and as ``atomic_write`` (when ``shared/scripts/lib`` is, e.g. from a
plugin doing the ``parents[4]`` shared-lib insert).
"""
from __future__ import annotations

import contextlib
import errno
import os
import tempfile
import threading
import time
from pathlib import Path

try:  # loaded as ``lib.atomic_write``
    from .durable_publish import SHARING_VIOLATION_WINERRORS, carry_destination_mode
except ImportError:  # loaded as top-level ``atomic_write`` (lib/ is on sys.path)
    from durable_publish import SHARING_VIOLATION_WINERRORS, carry_destination_mode

__all__ = ["durable_atomic_write", "durable_read_bytes", "durable_read_text",
           "REPLACE_RETRY_BUDGET_SECONDS", "READ_RETRY_BUDGET_SECONDS",
           "replace_retrying", "sharing_violation_retries", "reset_sharing_violation_retries"]

#: Sharing-violation retries this process has performed. Rationale and the residual
#: limit are in the module docstring's second bullet (card ``trg-0a294ef3``).
_retry_count = 0
_retry_count_lock = threading.Lock()


def sharing_violation_retries() -> int:
    """Retries performed so far by this process (replace + read paths combined).

    One counter, not two: both paths are silent in exactly the same way, and the
    question a caller actually asks is "did this primitive have to retry at all?".
    Also folds in the read path's ``retry_none_winerror`` retries — a different
    cause, same tally, name retained rather than split.
    """
    with _retry_count_lock:
        return _retry_count


def reset_sharing_violation_retries() -> None:
    """Zero the counter — for tests that need a clean baseline."""
    global _retry_count
    with _retry_count_lock:
        _retry_count = 0


def _note_retry() -> None:
    global _retry_count
    with _retry_count_lock:
        _retry_count += 1

#: The historical private name, kept resolvable for existing lookups. It IS the
#: leaf's frozenset, never a copy — ``test_durable_publish`` asserts identity, so
#: a rebind here cannot fork the source of truth. Which codes, and why: the leaf.
_SHARING_VIOLATION_WINERRORS = SHARING_VIOLATION_WINERRORS
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

    The encode is STRICT, and both this and :func:`durable_read_text` stay that way
    on the same reasoning: this primitive has ~35 callers writing git-tracked JSON
    that is read back strictly, and none of them has a repair pass. A lone surrogate
    (a path decoded by the OS with ``surrogateescape``, say) must fail HERE, where
    the caller knows what it was writing — not persist invalid UTF-8 into a tracked
    artifact and relocate the crash to every future reader of it.

    The triage store legitimately DOES round-trip undecodable bytes, because its
    readers decode with ``surrogateescape``. Those callers encode themselves and pass
    ``bytes`` (see ``sweep_outbox``, ``reconcile_triage``, ``sweep_quarantine``,
    ``triage_header``), so the leniency lives with the two modules that need it
    instead of on a primitive shared by thirty-five that do not.

    Sequence: write to a same-directory temp file → carry the destination's
    POSIX mode onto it → ``fsync`` it → ``os.replace`` onto ``path`` (atomic on
    POSIX; on Windows retried past a concurrent reader, see the module
    docstring) → best-effort directory fsync. The mode is applied BEFORE the
    fsync so one fsync covers bytes and metadata together; see
    :func:`durable_publish.carry_destination_mode` for why it is carried at all.
    On any failure the temp file is removed and the original error re-raised, so
    ``path`` is never left pointing at a half-written temp.
    """
    path = Path(path)
    raw = data.encode("utf-8") if isinstance(data, str) else data
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
            fh.flush()
            carry_destination_mode(fh.fileno(), path)
            os.fsync(fh.fileno())
        replace_retrying(tmp, path)
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


def _retry_past_sharing_violations(operation, budget_seconds: float, *,
                                   retry_none_winerror: bool = False):
    """Run ``operation`` (zero-arg), retrying while Windows says "file in use".

    POSIX has no such failure mode, so it runs the operation once and its
    behaviour is unchanged — a ``PermissionError`` there is real and propagates
    at once. On Windows only :data:`_SHARING_VIOLATION_WINERRORS` are treated as
    transient; the budget is bounded and exhausting it re-raises the original
    error, so a file that is genuinely locked open fails loudly.

    ``retry_none_winerror`` is read-path-only, OFF by default, and requires
    ``errno.EACCES`` too — not bare ``winerror is None`` — matching the
    MEASURED byte-range-lock shape while excluding a POSIX-shaped ``EPERM``.
    Not an exact match, though: Windows maps several causes (lock/sharing/
    access-denied) onto ``EACCES``, so a permanently denied read is retried
    too before raising — bounded, so the cost is capped (same trade-off
    ``durable_publish`` accepts on the write side; ``trg-dc013d82`` finding
    10, fixed as ``trg-db1de213``, doubt-reviewer D3). Write path doesn't opt
    in — no measured ``None``-winerror failure on ``os.replace``.

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
            winerror = getattr(exc, "winerror", None)
            transient = winerror in _SHARING_VIOLATION_WINERRORS or (
                retry_none_winerror and winerror is None and exc.errno == errno.EACCES)
            if not transient:
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
            _note_retry()
            time.sleep(min(delay, remaining))
            delay = min(delay * 2, _RETRY_MAX_SLEEP_SECONDS)


def replace_retrying(src: str | Path, dst: str | Path) -> None:
    """``os.replace`` retried while Windows says the destination is in use. Public because ``lib.sweep_drift_restore`` renames the tracked log aside in the same threat model."""
    _retry_past_sharing_violations(lambda: os.replace(src, dst),
                                   REPLACE_RETRY_BUDGET_SECONDS)


def durable_read_text(path: Path | str, *, encoding: str = "utf-8",
                      errors: str = "strict") -> str:
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

    ``errors`` defaults to **strict**, deliberately NOT mirroring the writer's
    ``surrogateescape``: the run-config / phase-history callers ``json.loads`` what
    they read, and lenient is harmful there — ``config_io`` catches
    ``JSONDecodeError`` and returns ``{}`` ("first run, no config yet"), while a
    strict ``UnicodeDecodeError`` is a ``ValueError``, escapes that handler and
    fails loudly. This once added "no triage-store reader goes through here … a
    triage-side caller can pass ``surrogateescape`` the day one exists"; that day
    came — ``jsonl_records.read_jsonl_records`` now reads the append-only triage
    store that way, a strict decode of an interrupted write having raised out of
    every reader (iterate-2026-08-06-p2-19c-corruption-absence).

    Also retries a byte-range-locked read for
    :data:`READ_RETRY_BUDGET_SECONDS` (``trg-db1de213``) — defence in depth
    against an unmeasured third-party holder (AV, indexer), not a closed
    in-repo race: every lock target here is a ``*.lock`` sidecar, never a
    file read through this function (doubt-reviewer D4).
    """
    target = Path(path)
    return _retry_past_sharing_violations(
        lambda: target.read_text(encoding=encoding, errors=errors),
        READ_RETRY_BUDGET_SECONDS, retry_none_winerror=True)


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
    # is itself blind to. Same reasoning for `retry_none_winerror=True`.
    return _retry_past_sharing_violations(
        lambda: target.read_bytes(), READ_RETRY_BUDGET_SECONDS, retry_none_winerror=True)


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
