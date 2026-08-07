"""A byte-range-locked READ must retry, not fail through instantly (trg-db1de213).

Companion to ``test_atomic_write_windows_read_retry.py`` (winerror-coded sharing
violations); split out because this cluster pins a DIFFERENT shape of failure.
Reading a range that another handle holds locked fails inside the read syscall
itself, not ``CreateFile``, so CPython raises an errno-only ``PermissionError``
with ``winerror`` **None** -- a value no code set can ever contain. Measured
twice on Windows 11 local NTFS (``trg-dc013d82`` finding 10, corrected by this
card): a byte-range lock on the destination does NOT yield WinError 33 as
originally assumed -- it yields 5, because holding a byte range requires
holding the file open, and the open handle alone already yields 5. What the
same probe DID surface is this None-winerror read failure, deliberately left
unfixed by that run and fixed here.

The write side is NOT part of this fix and stays that way on purpose: on
``os.replace`` a ``None`` winerror is a different, non-transient failure, and
retrying it would trade a loud failure for a silent stall. See
``test_write_side_does_not_retry_a_none_winerror`` below.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.atomic_write import (  # noqa: E402
    durable_atomic_write,
    durable_read_bytes,
    durable_read_text,
)


def _none_winerror_denial() -> PermissionError:
    """Shaped like the real errno-only denial: no ``winerror`` attribute set."""
    exc = PermissionError(13, "Access is denied")
    assert exc.winerror is None, "fixture no longer reproduces the errno-only shape"
    return exc


def test_read_text_retries_a_none_winerror_then_succeeds(tmp_path, monkeypatch):
    """The predicate must treat None as transient on the READ path."""
    import lib.atomic_write as aw

    target = tmp_path / "f.json"
    target.write_text('{"v": 1}', encoding="utf-8")

    monkeypatch.setattr(aw, "_is_windows", lambda: True)
    monkeypatch.setattr(aw.time, "sleep", lambda _s: None)

    real_read = Path.read_text
    attempts: list[int] = []

    def flaky_read(self, *a, **k):
        attempts.append(1)
        if len(attempts) < 3:
            raise _none_winerror_denial()
        return real_read(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", flaky_read)

    assert durable_read_text(target) == '{"v": 1}'
    assert len(attempts) == 3, "a None-winerror read must be retried, not abandoned"


def test_read_bytes_retries_a_none_winerror_then_succeeds(tmp_path, monkeypatch):
    """Same predicate, the bytes-reading twin — pinned separately per the
    existing sibling-asymmetry rule in test_atomic_write_windows_read_retry.py."""
    import lib.atomic_write as aw

    target = tmp_path / "f.bin"
    target.write_bytes(b"\x00\x01")

    monkeypatch.setattr(aw, "_is_windows", lambda: True)
    monkeypatch.setattr(aw.time, "sleep", lambda _s: None)

    real_read = Path.read_bytes
    attempts: list[int] = []

    def flaky_read(self, *a, **k):
        attempts.append(1)
        if len(attempts) < 3:
            raise _none_winerror_denial()
        return real_read(self, *a, **k)

    monkeypatch.setattr(Path, "read_bytes", flaky_read)

    assert durable_read_bytes(target) == b"\x00\x01"
    assert len(attempts) == 3


def test_read_text_still_gives_up_loudly_past_the_budget(tmp_path, monkeypatch):
    """Retried, not swallowed: a permanently locked range still raises.

    Counts attempts, not just the final exception type -- code-reviewer
    (MEDIUM): a predicate that never retries at all also raises
    `PermissionError` here, so an assertion on the exception alone would
    stay green even if `retry_none_winerror` were dropped entirely.

    Drives a FAKE clock rather than a tight real budget -- doubt-reviewer
    (D5, LOW): a real 0.02s budget with no `time.sleep` patch can lose its
    only retry to scheduler jitter (GC pause, a loaded box, another root's
    suite running) and fail on a message that says "must RETRY" when it did
    retry, just not enough times before the wall clock moved. `sleep`
    advances the same fake clock `monotonic` reads, so elapsed time is
    exact and deterministic -- and the real, unshortened
    `READ_RETRY_BUDGET_SECONDS` can be used instead of an arbitrary test-only
    value, since nothing here actually waits.
    """
    import lib.atomic_write as aw

    target = tmp_path / "f.json"
    target.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(aw, "_is_windows", lambda: True)

    fake_now = [0.0]
    monkeypatch.setattr(aw.time, "monotonic", lambda: fake_now[0])
    monkeypatch.setattr(aw.time, "sleep", lambda seconds: fake_now.__setitem__(0, fake_now[0] + seconds))

    attempts: list[int] = []

    def denied(self, *a, **k):
        attempts.append(1)
        raise _none_winerror_denial()

    monkeypatch.setattr(Path, "read_text", denied)

    with pytest.raises(PermissionError):
        durable_read_text(target)

    assert len(attempts) > 1, "it must RETRY past the budget, not fail on the first attempt"


def test_read_does_not_retry_a_none_winerror_with_a_different_errno(tmp_path, monkeypatch):
    """The opt-in matches the MEASURED shape (errno EACCES), not bare `winerror
    is None` -- a `PermissionError` shaped like a POSIX EPERM must still raise
    on the first attempt rather than being swept in by the wider check."""
    import lib.atomic_write as aw

    target = tmp_path / "f.json"
    target.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(aw, "_is_windows", lambda: True)
    attempts: list[int] = []

    def denied(self, *a, **k):
        attempts.append(1)
        exc = PermissionError(1, "Operation not permitted")   # errno.EPERM, not EACCES
        assert exc.winerror is None
        raise exc

    monkeypatch.setattr(Path, "read_text", denied)
    with pytest.raises(PermissionError):
        durable_read_text(target)

    assert len(attempts) == 1, "an EPERM-shaped None winerror must not be retried"


def test_write_side_does_not_retry_a_none_winerror(tmp_path, monkeypatch):
    """The asymmetry is deliberate: the write path opts out (see module docstring)."""
    import lib.atomic_write as aw

    monkeypatch.setattr(aw, "_is_windows", lambda: True)
    attempts: list[int] = []

    def denied(src, dst):
        attempts.append(1)
        raise _none_winerror_denial()

    monkeypatch.setattr(aw.os, "replace", denied)
    with pytest.raises(PermissionError):
        durable_atomic_write(tmp_path / "f.txt", "data")

    assert len(attempts) == 1, "the write path must not retry a None winerror"


@pytest.mark.skipif(sys.platform != "win32",
                    reason="msvcrt byte-range locking only exists on Windows")
def test_real_byte_range_lock_is_retried_past(tmp_path, monkeypatch):
    """Fidelity check against genuine OS behaviour, not an injected stub.

    Reproduces the exact measurement behind trg-db1de213: locking a byte range
    on the target from a second handle in this process makes a bare
    ``Path.read_text()`` raise ``PermissionError`` with ``winerror`` None: this
    asserts that too, so the fixture cannot silently stop reproducing the
    failure it exists to prove was retried past.

    Skips on non-Windows (``msvcrt`` byte-range locking doesn't exist there)
    but DOES run as part of the ordinary local `shared/tests` gate on
    Windows -- this project's primary dev platform, per F0. Code-reviewer
    (LOW) flagged an earlier "local-only, cannot run in CI" framing here as
    inaccurate for that reason; the deterministic stub tests above remain
    the platform-portable regression gate, but this one is real coverage,
    not merely a manual check. Timing-dependent (a 0.15s release against a
    widened 10s budget, so a loaded box delays the release rather than
    turning this red with a confusing bare ``PermissionError``).
    """
    import msvcrt

    import lib.atomic_write as aw
    monkeypatch.setattr(aw, "READ_RETRY_BUDGET_SECONDS", 10.0)

    target = tmp_path / "shipwright_run_config.json"
    target.write_text('{"v": 1}' + " " * 16, encoding="utf-8")

    locker = open(target, "r+b")
    locker.seek(0)
    msvcrt.locking(locker.fileno(), msvcrt.LK_NBLCK, 10)
    try:
        with pytest.raises(PermissionError) as excinfo:
            target.read_text(encoding="utf-8")
        assert excinfo.value.winerror is None, "fixture no longer reproduces the errno-only shape"

        releaser = threading.Timer(0.15, lambda: (
            locker.seek(0), msvcrt.locking(locker.fileno(), msvcrt.LK_UNLCK, 10)))
        releaser.start()
        try:
            started = time.monotonic()
            text = durable_read_text(target)
            waited = time.monotonic() - started
        finally:
            releaser.cancel()
    finally:
        try:
            locker.seek(0)
            msvcrt.locking(locker.fileno(), msvcrt.LK_UNLCK, 10)
        except OSError:
            pass
        locker.close()

    assert text == '{"v": 1}' + " " * 16
    assert waited >= 0.1, "must have actually waited for the holder, not raced it"
