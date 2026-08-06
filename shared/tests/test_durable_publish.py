"""Unit tests for ``lib.durable_publish`` — the platform half of publishing an
atomically-written file.

The leaf answers two questions ``durable_atomic_write`` must not answer inline:
which Windows errors mean *someone else has the destination open*, and what
mode the published file must carry on POSIX. Both are covered here, together
This file covers the MODE CARRIER (trg-dc013d82 finding 20). The winerror
set and its retry wiring (finding 10) live in
``test_durable_publish_winerrors.py`` — split to keep both inside the
300-line budget.
"""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib import durable_publish as dp  # noqa: E402
from lib.atomic_write import durable_atomic_write  # noqa: E402

_POSIX_ONLY = pytest.mark.skipif(
    os.name == "nt",
    reason="real POSIX mode bits; CI is ubuntu-latest so this leg always runs there",
)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


class _OsShim:
    """Stand-in for the ``os`` module with selected attributes overridden.

    Patched over ``dp.os`` rather than over ``os.stat`` itself. ``dp.os`` IS the
    real module, so stubbing an attribute on it is process-global for the whole
    test body — and ``os.stat`` in particular is called by pytest's own
    reporting, so a failing assertion would surface as a confusing unrelated
    error instead of the real one. Overriding the module reference confines the
    stub to this module's own lookups, which is the discipline the fchmod tests
    below already state in prose.

    An override also CREATES the attribute where the host lacks it (``fchmod`` on
    Windows), so both platform branches stay reachable from either host.

    ``name`` defaults to ``"posix"`` because the carrier gates on ``os.name !=
    "nt"`` as well as on the capability — a Windows host would otherwise
    short-circuit before reaching the behaviour under test. A test that wants the
    Windows branch says ``name="nt"`` explicitly.
    """

    def __init__(self, **overrides):
        self.__dict__.setdefault("name", "posix")
        self.__dict__.update(overrides)

    def __getattr__(self, name):  # only reached for non-overridden names
        return getattr(os, name)



# --- the mode carrier (finding 20) ---------------------------------------

@_POSIX_ONLY
def test_carries_an_existing_destinations_mode(tmp_path):
    """The published file keeps the mode the destination already had."""
    dest = tmp_path / "cfg.json"
    dest.write_text("old", encoding="utf-8")
    os.chmod(dest, 0o644)

    tmp = tmp_path / "scratch"
    fd = os.open(tmp, os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        assert dp.carry_destination_mode(fd, dest) is True
    finally:
        os.close(fd)

    assert _mode(tmp) == 0o644


@_POSIX_ONLY
def test_missing_destination_has_no_mode_to_carry(tmp_path):
    """A first-ever write is not a failure — there is simply nothing to carry.

    The temp file keeps ``mkstemp``'s 0600 rather than having a "natural" mode
    invented for it: deriving one needs the process umask, and ``os.umask`` can
    only be READ by temporarily SETTING it — a process-global mutation a shared
    primitive must not make on a caller's behalf.
    """
    dp.reset_mode_carry_failures()
    tmp = tmp_path / "scratch"
    fd = os.open(tmp, os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        assert dp.carry_destination_mode(fd, tmp_path / "absent.json") is False
    finally:
        os.close(fd)

    assert _mode(tmp) == 0o600
    assert dp.mode_carry_failures() == 0, "an absent destination is not a failure"


def test_a_failed_carry_is_counted_not_raised(tmp_path, monkeypatch):
    """A refused ``fchmod`` must not fail the write — but must not vanish either.

    Silently narrowing a published file's permissions is a security-posture
    change, so it is surfaced the way this subsystem already surfaces the
    sharing-violation retries: a counter a test can assert on, not a
    ``warnings.warn`` that any caller can globally suppress.
    """
    dp.reset_mode_carry_failures()
    dest = tmp_path / "cfg.json"
    dest.write_text("old", encoding="utf-8")

    def boom(*a, **k):
        raise OSError("chmod refused")

    monkeypatch.setattr(dp, "os", _OsShim(fchmod=boom))
    fd = os.open(tmp_path / "scratch", os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        assert dp.carry_destination_mode(fd, dest) is False
    finally:
        os.close(fd)

    assert dp.mode_carry_failures() == 1


def test_carries_the_destinations_exact_mode_bits(tmp_path, monkeypatch):
    """Which mode gets carried — asserted on EVERY host, not only POSIX.

    The two end-to-end mode tests above need real ``chmod`` semantics and so skip
    on Windows, which would leave the selection logic (mask, and reading the
    DESTINATION rather than the temp file) proven only by the Linux CI leg. This
    stubs the syscalls instead, so the choice of mode is pinned everywhere.
    """
    dest = tmp_path / "cfg.json"
    dest.write_text("old", encoding="utf-8")
    seen: list[int] = []

    class _Stat:
        # 0o100644: S_IFREG | rw-r--r--. The file-type bits MUST be masked off —
        # passing them to fchmod is what the 0o7777 mask exists to prevent.
        st_mode = 0o100644

    monkeypatch.setattr(dp, "os", _OsShim(
        stat=lambda p: _Stat(),
        fchmod=lambda fd, mode: seen.append(mode),
    ))

    assert dp.carry_destination_mode(123, dest) is True
    assert seen == [0o644]


def test_an_unstattable_destination_is_counted_too(tmp_path, monkeypatch):
    """AC-3's other half: the failure can come from ``stat``, not just ``fchmod``.

    An ``OSError`` that is NOT ``FileNotFoundError`` — a deny-ACL on the
    directory, say — means the mode is unknowable rather than absent, so it is a
    counted failure and not the silent "nothing to carry" case.
    """
    dp.reset_mode_carry_failures()
    dest = tmp_path / "cfg.json"
    dest.write_text("old", encoding="utf-8")

    def boom(*a, **k):
        raise PermissionError("stat refused")

    monkeypatch.setattr(dp, "os", _OsShim(stat=boom, fchmod=lambda fd, mode: None))

    assert dp.carry_destination_mode(123, dest) is False
    assert dp.mode_carry_failures() == 1


def test_write_survives_a_refused_mode_carry(tmp_path, monkeypatch):
    """AC-3: a destination whose mode cannot be SET still gets written.

    End-to-end through ``durable_atomic_write``, driving the real failure mode —
    a refused syscall, which the carrier swallows — rather than a carrier that
    raises, which the implementation makes impossible (that shape is pinned by
    ``test_atomic_write::test_a_raising_carrier_still_unlinks_the_temp``). The
    bytes must land, the call must return normally, and the refusal must be
    COUNTED, so a silently narrowed mode is never invisible.

    Discriminates: delete the ``except OSError`` around ``fchmod`` and this fails
    with an OSError out of ``durable_atomic_write``.
    """
    dp.reset_mode_carry_failures()
    target = tmp_path / "cfg.json"
    durable_atomic_write(target, "first")  # exists → there IS a mode to carry

    def boom(*a, **k):
        raise OSError("fchmod refused")

    monkeypatch.setattr(dp, "os", _OsShim(fchmod=boom))
    durable_atomic_write(target, "second")

    assert target.read_text(encoding="utf-8") == "second"
    assert dp.mode_carry_failures() == 1


def test_write_survives_an_unstattable_destination(tmp_path, monkeypatch):
    """AC-3's other half, end-to-end this time.

    The refused-``stat`` branch was only exercised by calling the carrier
    directly, so an integration regression specific to it — the swallow being
    removed from the ``stat`` arm but not the ``fchmod`` one, say — would not
    have been caught (external code review).
    """
    dp.reset_mode_carry_failures()
    target = tmp_path / "cfg.json"
    durable_atomic_write(target, "first")

    def boom(*a, **k):
        raise PermissionError("stat refused")

    monkeypatch.setattr(dp, "os", _OsShim(stat=boom, fchmod=lambda fd, mode: None))
    durable_atomic_write(target, "second")

    assert target.read_text(encoding="utf-8") == "second"
    assert dp.mode_carry_failures() == 1


def test_windows_never_carries_even_if_fchmod_appears(tmp_path, monkeypatch):
    """``os.name == "nt"`` disables the carry on its own, capability or not.

    Windows ``st_mode`` is a read-only-attribute proxy, not a POSIX mode, so
    carrying it would publish read-only files — and the next ``os.replace`` onto
    one raises winerror 5, which the sharing-violation set treats as transient
    contention and retries for the whole budget before failing. Gating on the
    capability ALONE would arm all of that the day a CPython release grows
    ``os.fchmod`` on Windows (doubt review).
    """
    dp.reset_mode_carry_failures()
    dest = tmp_path / "cfg.json"
    dest.write_text("old", encoding="utf-8")
    called: list[int] = []

    monkeypatch.setattr(dp, "os", _OsShim(
        name="nt", fchmod=lambda fd, mode: called.append(mode)))

    assert dp.carry_destination_mode(123, dest) is False
    assert called == [], "the carry must not fire on nt even with fchmod present"
    assert dp.mode_carry_failures() == 0


def test_no_op_where_fchmod_does_not_exist(tmp_path, monkeypatch):
    """Windows has no ``os.fchmod``; the carrier keys on the capability itself.

    Deleting the attribute lets the POSIX CI runner exercise the Windows branch
    too, so neither platform ships an untested half.
    """
    dp.reset_mode_carry_failures()

    class _NoFchmod(_OsShim):
        def __getattr__(self, name):
            if name == "fchmod":
                raise AttributeError(name)  # the Windows shape, on any host
            return getattr(os, name)

    monkeypatch.setattr(dp, "os", _NoFchmod())  # name="posix", but no fchmod
    dest = tmp_path / "cfg.json"
    dest.write_text("old", encoding="utf-8")

    fd = os.open(tmp_path / "scratch", os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        assert dp.carry_destination_mode(fd, dest) is False
    finally:
        os.close(fd)

    assert dp.mode_carry_failures() == 0, "an absent capability is not a failure"
