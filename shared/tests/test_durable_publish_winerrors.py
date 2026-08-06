"""The Windows sharing-violation code set — ``lib.durable_publish`` (finding 10).

Split out of ``test_durable_publish.py`` to keep both files inside the 300-line
budget, the same way ``test_atomic_write_windows_retry`` was split out of
``test_atomic_write``: the retry contract is a self-contained cluster and the
mode carrier is a different concern that happens to share a module.

Covers the set itself, the identity of ``atomic_write``'s historical alias, and
the one integration fact that makes the set load-bearing — that a code IN it
really does reach the retry loop rather than being raised on first contact.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib import durable_publish as dp  # noqa: E402
from lib.atomic_write import durable_atomic_write  # noqa: E402


def test_lock_violation_is_a_sharing_violation_code():
    """``ERROR_LOCK_VIOLATION`` (33) is in the set — as defence in depth.

    CPython's ``PC/errmap.h`` maps 33 to ``EACCES``, so a host that REPORTED it
    would raise ``PermissionError`` and fall out of the retry. No measured host
    on this path does: probed twice on Windows 11 local NTFS (during
    iterate-2026-07-27-run-unit-parallel-race, which declined this suggestion on
    that evidence, and again for trg-dc013d82 finding 10), a byte-range-locked
    destination gave **5** both times — holding a byte range also requires
    holding the file open, and the open handle alone already yields 5.

    So this pins membership, not a reproduced defect. The write it protects is
    one on a filesystem or Windows build that does emit 33; the cost is at worst
    the same short stall already accepted for the far more ambiguous 5.
    """
    assert dp.SHARING_VIOLATION_WINERRORS == frozenset({5, 32, 33})


def test_atomic_write_alias_is_the_leaf_frozenset_not_a_fork():
    """The historical name on ``atomic_write`` must BE the leaf's object.

    A later edit that rebinds the alias instead of editing the leaf would fork
    the source of truth silently; identity (not equality) is what catches it
    (external plan review, deepseek).
    """
    import lib.atomic_write as aw  # noqa: PLC0415

    assert aw._SHARING_VIOLATION_WINERRORS is dp.SHARING_VIOLATION_WINERRORS


def test_replace_retries_winerror_33(tmp_path, monkeypatch):
    """End-to-end: membership in the set really does reach the retry loop.

    The 33 injected here is synthetic and deliberately labelled as such rather
    than dressed up as a scenario — see the test above: no measured host on this
    path emits it, and a real byte-range lock gives 5. What this pins is the
    WIRING: a code in ``SHARING_VIOLATION_WINERRORS`` is retried within the
    budget rather than raised on first contact, so adding 33 to the set is not
    an inert edit. The sibling
    ``test_atomic_write_windows_retry::test_a_winerror_outside_the_transient_set_is_not_retried``
    pins the other half of the same filter.

    The Windows branch is forced via ``aw._is_windows`` (never ``os.name`` — see
    that function's docstring), so the Linux CI runner exercises it too.
    """
    import lib.atomic_write as aw  # noqa: PLC0415

    aw.reset_sharing_violation_retries()
    monkeypatch.setattr(aw, "_is_windows", lambda: True)
    real_replace = os.replace
    attempts: list[int] = []

    def flaky_replace(src, dst):
        attempts.append(1)
        if len(attempts) < 3:
            exc = PermissionError(13, "The process cannot access the file")
            exc.winerror = 33
            raise exc
        return real_replace(src, dst)

    monkeypatch.setattr(aw.os, "replace", flaky_replace)
    durable_atomic_write(tmp_path / "f.txt", "kept")

    assert (tmp_path / "f.txt").read_text(encoding="utf-8") == "kept"
    assert len(attempts) == 3, "33 must be retried, not raised on first contact"
    assert aw.sharing_violation_retries() == 2, "each retry must be counted"

