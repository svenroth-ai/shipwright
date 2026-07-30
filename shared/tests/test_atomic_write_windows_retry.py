"""A concurrent READER must not make a WRITER lose its write (Windows).

``os.replace`` is atomic on Windows only when it *succeeds*. Windows refuses to
replace a file that any process holds open without ``FILE_SHARE_DELETE``, and
CPython's ``open()`` does not request it — so a plain reader is enough to make
``durable_atomic_write`` raise ``PermissionError`` (``WinError`` 5
``ACCESS_DENIED`` / 32 ``SHARING_VIOLATION``) and drop the write. Locking does
not close this: the run-config design deliberately permits unlocked readers, and
the WebUI / editors / antivirus are outside our locking discipline entirely.

Split out of ``test_atomic_write.py`` to keep both files inside the 300-line
budget (the retry contract is a self-contained cluster).

Found via F0 race card ``f0-race:shipwright-run``, which was neither inter-unit
pollution nor an unreliable test but this bug, surfaced by CPU contention.

**These tests patch ``aw._is_windows``, NEVER ``os.name``.** ``os.name`` is
process-global and ``pathlib.Path()`` dispatches on it, so forcing it makes
``Path(...)`` build the foreign flavour and raise ``NotImplementedError`` before
the code under test is reached — ``"nt"`` on POSIX CI and ``"posix"`` on a
Windows host alike. Patching the predicate lets Linux CI exercise logic that
only ever misbehaves on Windows.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.atomic_write import durable_atomic_write  # noqa: E402


def _sharing_violation(winerror: int = 5) -> PermissionError:
    """A ``PermissionError`` shaped like the real Windows one (WinError 5/32)."""
    exc = PermissionError(13, "Access is denied")
    exc.winerror = winerror
    return exc


def test_replace_retries_while_a_reader_holds_the_destination(tmp_path, monkeypatch):
    """AC1: a reader that lets go within the budget must not cost us the write."""
    import lib.atomic_write as aw

    monkeypatch.setattr(aw, "_is_windows", lambda: True)
    real_replace = os.replace
    attempts: list[int] = []

    def flaky_replace(src, dst):
        attempts.append(1)
        if len(attempts) < 3:          # held open for the first two attempts
            raise _sharing_violation(5)
        return real_replace(src, dst)

    monkeypatch.setattr(aw.os, "replace", flaky_replace)
    monkeypatch.setattr(aw.time, "sleep", lambda _s: None)

    durable_atomic_write(tmp_path / "f.json", '{"v": 2}')

    assert len(attempts) == 3, "the replace must be retried, not abandoned"
    assert (tmp_path / "f.json").read_text(encoding="utf-8") == '{"v": 2}'


def test_replace_gives_up_loudly_when_the_handle_never_closes(tmp_path, monkeypatch):
    """AC2 + AC3: a write is never silently dropped, and leaves no debris.

    The elapsed-time bound is not decoration: nothing in this repo's pytest
    config sets a per-test timeout, so if the deadline comparison were ever
    inverted this test would spin until the CI job limit instead of failing.
    """
    import time as _time

    import lib.atomic_write as aw

    target = tmp_path / "f.json"
    target.write_text('{"v": 1}', encoding="utf-8")

    monkeypatch.setattr(aw, "_is_windows", lambda: True)
    monkeypatch.setattr(aw, "REPLACE_RETRY_BUDGET_SECONDS", 0.05)
    monkeypatch.setattr(aw.os, "replace",
                        lambda src, dst: (_ for _ in ()).throw(_sharing_violation(32)))

    started = _time.monotonic()
    with pytest.raises(PermissionError):
        durable_atomic_write(target, '{"v": 2}')
    elapsed = _time.monotonic() - started

    assert elapsed < 5.0, (
        f"gave up after {elapsed:.1f}s against a 0.05s budget — the deadline "
        f"must terminate the loop, not merely be checked"
    )
    assert target.read_text(encoding="utf-8") == '{"v": 1}', "prior content intact"
    assert [p.name for p in tmp_path.iterdir() if p.suffix == ".tmp"] == []


def test_retry_never_outlives_the_configured_budget(tmp_path, monkeypatch):
    """The backoff sleep is clamped to the time left, so the last attempt lands
    AT the deadline rather than up to one backoff step past it.

    Real magnitude here: a step can be up to `_RETRY_MAX_SLEEP_SECONDS`, so without
    the clamp a 0.5 s budget can overrun by 20%. The SIBLING clamp — `min(..., budget)`
    against a `deadline` that floating point rounds a hair high — is worth ~2**-31 s
    and is a contract-exactness fix, not a bug fix; the test for it says so, because
    conflating the two would have the next reader trusting the budget for more than
    it promises."""
    import lib.atomic_write as aw

    monkeypatch.setattr(aw, "_is_windows", lambda: True)
    monkeypatch.setattr(aw, "REPLACE_RETRY_BUDGET_SECONDS", 0.05)
    monkeypatch.setattr(aw, "_RETRY_MAX_SLEEP_SECONDS", 30.0)
    monkeypatch.setattr(aw, "_RETRY_INITIAL_SLEEP_SECONDS", 30.0)

    slept: list[float] = []
    monkeypatch.setattr(aw.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(aw.os, "replace",
                        lambda src, dst: (_ for _ in ()).throw(_sharing_violation(5)))

    with pytest.raises(PermissionError):
        durable_atomic_write(tmp_path / "f.txt", "data")

    assert slept, "a retry should have been attempted"
    assert max(slept) <= 0.05, (
        f"slept {max(slept)}s against a 0.05s budget — the sleep must be clamped "
        f"to the remaining time, not to the backoff step"
    )


def test_a_winerror_outside_the_transient_set_is_not_retried(tmp_path, monkeypatch):
    """The filter is a whitelist: an unlisted code is re-raised on attempt one.

    The injected 1337 is synthetic, and deliberately labelled as such rather
    than dressed up as a scenario. Measured on Windows 11, `os.replace` returns
    winerror **5** for every real case on this path — plain reader, memory-map,
    byte-range lock, read-only destination, directory destination alike. So
    this pins the SHAPE of the filter (unlisted -> immediate raise), which is
    what protects a future maintainer who widens the set; it does not claim to
    reproduce a code Windows emits here.
    """
    import lib.atomic_write as aw

    monkeypatch.setattr(aw, "_is_windows", lambda: True)
    attempts: list[int] = []

    def denied(src, dst):
        attempts.append(1)
        raise _sharing_violation(1337)      # synthetic: not a code seen here

    monkeypatch.setattr(aw.os, "replace", denied)
    with pytest.raises(PermissionError):
        durable_atomic_write(tmp_path / "f.txt", "data")

    assert len(attempts) == 1


def test_a_genuine_denial_is_retried_too_because_winerror_5_is_ambiguous(
        tmp_path, monkeypatch):
    """Record the accepted cost rather than implying a discrimination we lack.

    ERROR_ACCESS_DENIED (5) is what a sharing violation returns AND what a
    read-only destination, a deny-ACL or a directory destination return (all
    measured). A genuine denial therefore burns the whole budget before it
    surfaces. That is the deliberate trade — bounded stall, still loud — and it
    is why the budget is short. If someone later shortens the path by
    special-casing 5, this test says what they would be giving up.
    """
    import lib.atomic_write as aw

    monkeypatch.setattr(aw, "_is_windows", lambda: True)
    monkeypatch.setattr(aw, "REPLACE_RETRY_BUDGET_SECONDS", 0.02)
    attempts: list[int] = []

    def always_denied(src, dst):
        attempts.append(1)
        raise _sharing_violation(5)         # indistinguishable from a real denial

    monkeypatch.setattr(aw.os, "replace", always_denied)
    with pytest.raises(PermissionError):
        durable_atomic_write(tmp_path / "f.txt", "data")

    assert len(attempts) > 1, "winerror 5 is retried; we cannot tell the two apart"


def test_posix_never_retries(tmp_path, monkeypatch):
    """AC4: POSIX rename has no sharing-violation failure mode, so behaviour
    there is unchanged — a PermissionError propagates on the first attempt."""
    import lib.atomic_write as aw

    monkeypatch.setattr(aw, "_is_windows", lambda: False)
    attempts: list[int] = []

    def denied(src, dst):
        attempts.append(1)
        raise _sharing_violation(5)

    monkeypatch.setattr(aw.os, "replace", denied)
    with pytest.raises(PermissionError):
        durable_atomic_write(tmp_path / "f.txt", "data")

    assert len(attempts) == 1


@pytest.mark.skipif(sys.platform != "win32",
                    reason="POSIX allows rename over an open file; nothing to prove")
def test_real_windows_reader_does_not_lose_the_write(tmp_path, monkeypatch):
    """Fidelity check against the genuine OS behaviour, not an injected stub.

    This is the deterministic form of the F0 race card `f0-race:shipwright-run`:
    before the fix a single open reader made `durable_atomic_write` raise. The
    budget is widened well past the 0.15s hold so a loaded machine cannot turn
    this into the very kind of contention-flaky test the fix exists to remove.
    """
    import threading

    import lib.atomic_write as aw

    monkeypatch.setattr(aw, "REPLACE_RETRY_BUDGET_SECONDS", 60.0)

    target = tmp_path / "shipwright_run_config.json"
    target.write_text('{"v": 1}', encoding="utf-8")

    reader = open(target, "r", encoding="utf-8")  # held: the destination must be occupied
    closer = threading.Timer(0.15, reader.close)
    closer.start()
    try:
        durable_atomic_write(target, '{"v": 2}')
    finally:
        closer.cancel()
        reader.close()

    assert target.read_text(encoding="utf-8") == '{"v": 2}'


def test_the_clamp_survives_a_deadline_that_rounds_above_the_budget(monkeypatch):
    """The budget cap, proven on ANY platform rather than only where it bites.

    The sibling test above is real but platform-shaped: on Windows `time.monotonic()`
    is GetTickCount64 (~15.6 ms), so both reads land in the same tick and
    `(t0 + budget) - t0` evaluates a few ulps of t0 above `budget`. On Linux time
    genuinely elapses between the reads, so `remaining < budget` strictly and the test
    passes with or without the fix — meaning the gate that guards this change cannot
    tell the two apart.

    Here the clock is stubbed to reproduce the arithmetic exactly: one timestamp, read
    twice. The literal is not decorative — it is a value for which `(t0 + 0.05) - t0`
    returns 0.05000000004656613, the exact number the Windows run reported. Roughly 17
    days of uptime; the error is ulp(t0)/2 at that magnitude.
    """
    import lib.atomic_write as aw

    t0 = 1516983.2475057743
    assert (t0 + 0.05) - t0 > 0.05, "fixture no longer reproduces the rounding error"

    monkeypatch.setattr(aw, "_is_windows", lambda: True)
    monkeypatch.setattr(aw, "_RETRY_INITIAL_SLEEP_SECONDS", 30.0)
    # `aw.time` IS the stdlib module, so this patches `time.monotonic` process-wide
    # rather than a module-local alias — safe under serial pytest, and NOT safe the day
    # this root runs with `-n auto` alongside the `threading.Timer` test in this file.
    # Recorded rather than fixed: giving `monotonic` the `_is_windows` treatment (a
    # module-level seam plus the source-level drift guard above) is a change to the
    # production module for a test's benefit, and that is a decision, not a cleanup.
    monkeypatch.setattr(aw.time, "monotonic", lambda: t0)

    slept: list[float] = []
    monkeypatch.setattr(aw.time, "sleep", lambda s: slept.append(s))

    attempts = {"n": 0}

    def operation():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _sharing_violation(5)
        return "ok"

    assert aw._retry_past_sharing_violations(operation, budget_seconds=0.05) == "ok"
    assert slept == [0.05], f"slept {slept} — the clamp must never exceed the budget"
