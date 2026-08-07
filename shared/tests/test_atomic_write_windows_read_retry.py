"""A concurrent WRITER must not break a READER (Windows) — the mirror image.

Hardening only the write side MOVES the failure rather than removing it. When a
writer replaces a file someone still has open, Windows leaves the old entry
*delete-pending* and a reader's ``open()`` fails with ``PermissionError`` until
the last handle goes. Measured: once the write side was fixed, the concurrent
run-config test stopped failing in ``os.replace`` and started failing in
``load_run_config``'s ``read_text`` — because a fix that lets more writes SUCCEED
also creates more of these windows.

Companion to ``test_atomic_write_windows_retry.py`` (the write side); split so
both stay inside the 300-line budget. Same rule applies here: patch
``aw._is_windows``, NEVER ``os.name`` — see the drift guard below.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.atomic_write import durable_read_bytes, durable_read_text  # noqa: E402


def _sharing_violation(winerror: int = 5) -> PermissionError:
    """A ``PermissionError`` shaped like the real Windows one (WinError 5/32)."""
    exc = PermissionError(13, "Access is denied")
    exc.winerror = winerror
    return exc


def test_no_test_here_forces_the_platform_by_patching_os_name():
    """Drift guard for AC8 — the hazard is invisible on the host that passes.

    Patching `os.name` to reach the Windows branch is green on Windows and red
    on Linux CI (and vice versa), so nothing local catches a reintroduction.
    Assert on the source instead: the predicate is the only supported lever.
    """
    here = Path(__file__)
    for path in (here,
                 here.with_name("test_atomic_write.py"),
                 here.with_name("test_atomic_write_windows_retry.py"),
                 here.with_name("test_gate_policy_read_retry.py")):
        src = path.read_text(encoding="utf-8")
        # Built from parts so this guard does not match its own source.
        needle = 'setattr(aw.os, ' + '"name"'
        assert needle not in src, (
            f"{path.name} forces the platform via the process-global os.name; "
            f"pathlib dispatches on it, so this passes here and fails on the "
            f"other platform's CI - patch aw._is_windows instead"
        )



# --- the mirror image: a concurrent WRITER must not break a READER ----------
#
# Hardening only the write side MOVES the failure rather than removing it. When
# a writer replaces a file someone still has open, Windows leaves the old entry
# delete-pending and a reader's open() fails with PermissionError. Measured: the
# concurrent run-config test went from failing in `os.replace` to failing in
# `load_run_config`'s `read_text` once the write side was fixed.

def test_read_retries_while_a_writer_is_mid_replace(tmp_path, monkeypatch):
    """A reader must survive a publisher's in-flight replace."""
    import lib.atomic_write as aw

    target = tmp_path / "shipwright_run_config.json"
    target.write_text('{"v": 1}', encoding="utf-8")

    monkeypatch.setattr(aw, "_is_windows", lambda: True)
    monkeypatch.setattr(aw.time, "sleep", lambda _s: None)

    real_read = Path.read_text
    attempts: list[int] = []

    def flaky_read(self, *a, **k):
        attempts.append(1)
        if len(attempts) < 3:          # delete-pending for the first two tries
            raise _sharing_violation(5)
        return real_read(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", flaky_read)

    assert durable_read_text(target) == '{"v": 1}'
    assert len(attempts) == 3, "the read must be retried, not abandoned"


def test_the_read_budget_is_longer_than_the_write_budget():
    """The asymmetry is load-bearing, so pin it rather than leave it to taste.

    A patient READER only costs latency — waiting cannot publish anything. A
    patient WRITER widens the window in which an unlocked writer can publish a
    stale snapshot. Collapsing the two to one constant makes one of the two
    measured failure modes reappear: at 0.5 s for both, a starved reader failed
    1 in 36 under 12-way contention.
    """
    import lib.atomic_write as aw

    assert aw.READ_RETRY_BUDGET_SECONDS > aw.REPLACE_RETRY_BUDGET_SECONDS


def test_read_gives_up_loudly_rather_than_inventing_an_empty_config(
        tmp_path, monkeypatch):
    """An unreadable file must raise, never degrade to ''.

    Silently returning empty would be worse than the crash it replaces: callers
    `json.loads` this, and an empty/parse-failed config is treated as "first
    run, no config yet" — which would bootstrap over a live pipeline.
    """
    import lib.atomic_write as aw

    target = tmp_path / "f.json"
    target.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(aw, "_is_windows", lambda: True)
    monkeypatch.setattr(aw, "READ_RETRY_BUDGET_SECONDS", 0.02)
    monkeypatch.setattr(Path, "read_text",
                        lambda self, *a, **k: (_ for _ in ()).throw(
                            _sharing_violation(5)))

    with pytest.raises(PermissionError):
        durable_read_text(target)


def test_reading_bytes_preserves_line_endings_that_reading_text_destroys(tmp_path):
    """Why `durable_read_bytes` exists at all, as a difference rather than a claim.

    `restore_derived_to_head`'s run-written carve-out carries a file across a merge:
    read the bytes, hand git a clean path, write the bytes back. Read through the TEXT
    helper and that round-trip is not byte-preserving — universal-newline translation
    turns CRLF into LF — so a CRLF ledger would come back rewritten and show as a diff
    the run never made. The two are asserted side by side because the failure is
    invisible in isolation: both reads succeed, and only one gives back what was there.
    """
    target = tmp_path / "crlf.json"
    original = b'{"iterate_latest": {"run_id": "x"}}\r\n'
    target.write_bytes(original)

    assert durable_read_bytes(target) == original
    assert durable_read_text(target).encode("utf-8") != original


def test_reading_bytes_retries_past_a_sharing_violation_then_raises(tmp_path, monkeypatch):
    """Same posture as the text reader: bounded patience, then loud.

    Pinned separately because the two go through different `Path` methods, so a
    future change could harden one and silently leave the other bare — which is
    exactly the asymmetry this function was added to remove.
    """
    import lib.atomic_write as aw

    target = tmp_path / "f.json"
    target.write_bytes(b"{}")

    monkeypatch.setattr(aw, "_is_windows", lambda: True)
    monkeypatch.setattr(aw, "READ_RETRY_BUDGET_SECONDS", 0.02)
    calls = []
    monkeypatch.setattr(Path, "read_bytes",
                        lambda self, *a, **k: (calls.append(1), (_ for _ in ()).throw(
                            _sharing_violation(32)))[0])

    with pytest.raises(PermissionError):
        durable_read_bytes(target)
    assert len(calls) > 1, "it must RETRY, not fail on the first violation"
