"""Unit tests for ``lib.atomic_write.durable_atomic_write`` — the shared
durable-write primitive (audit follow-up to WP2 runconfig-atomic-writes).

WP2 closed *torn reads* (``tmp + os.replace``). These tests pin the
*durability* contract this primitive adds on top: the temp file is
``fsync``'d **before** the rename, and a failing parent-directory fsync is
best-effort (never fails the write).
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


# --- byte-faithful round-trip (boundary probe) ---------------------------

def test_roundtrip_str(tmp_path):
    target = tmp_path / "f.json"
    durable_atomic_write(target, '{"a": 1}\n')
    assert target.read_text(encoding="utf-8") == '{"a": 1}\n'


def test_roundtrip_bytes(tmp_path):
    target = tmp_path / "f.bin"
    durable_atomic_write(target, b"\x00\x01\x02payload")
    assert target.read_bytes() == b"\x00\x01\x02payload"


def test_str_written_verbatim_no_newline_translation(tmp_path):
    """``str`` is encoded UTF-8 and written verbatim — LF stays LF (never
    translated to CRLF), and no trailing newline is invented."""
    target = tmp_path / "f.txt"
    durable_atomic_write(target, "line1\nline2\nno-trailing")
    assert target.read_bytes() == b"line1\nline2\nno-trailing"


def test_unicode_roundtrip(tmp_path):
    target = tmp_path / "f.txt"
    durable_atomic_write(target, "héllo — wörld ✅\n")
    assert target.read_text(encoding="utf-8") == "héllo — wörld ✅\n"


def test_overwrite_is_wholesale(tmp_path):
    """A shorter second write leaves no stale tail bytes from the first."""
    target = tmp_path / "f.txt"
    durable_atomic_write(target, "x" * 500)
    durable_atomic_write(target, "short")
    assert target.read_text(encoding="utf-8") == "short"


def test_creates_parent_dirs(tmp_path):
    target = tmp_path / "deep" / "nested" / "f.txt"
    durable_atomic_write(target, "ok")
    assert target.read_text(encoding="utf-8") == "ok"


def test_accepts_str_path(tmp_path):
    target = tmp_path / "f.txt"
    durable_atomic_write(str(target), "ok")
    assert target.read_text(encoding="utf-8") == "ok"


def test_no_tmp_leftover_on_success(tmp_path):
    durable_atomic_write(tmp_path / "f.txt", "ok")
    assert [p.name for p in tmp_path.iterdir() if p.suffix == ".tmp"] == []


# --- durability ordering: fsync(file) BEFORE os.replace ------------------

def test_file_is_fsynced_before_replace(tmp_path, monkeypatch):
    """The durability contract: the temp file's bytes are flushed to disk
    (``os.fsync``) before the atomic rename, so a crash after the rename can
    never expose an empty/stale file."""
    import lib.atomic_write as aw

    calls: list[str] = []
    real_fsync = os.fsync
    real_replace = os.replace

    def spy_fsync(fd):
        calls.append("fsync")
        return real_fsync(fd)

    def spy_replace(src, dst):
        calls.append("replace")
        return real_replace(src, dst)

    monkeypatch.setattr(aw.os, "fsync", spy_fsync)
    monkeypatch.setattr(aw.os, "replace", spy_replace)

    durable_atomic_write(tmp_path / "f.txt", "data")

    assert "fsync" in calls and "replace" in calls
    # At least one fsync (the temp file) precedes the rename.
    assert calls.index("fsync") < calls.index("replace")


# --- best-effort parent-directory fsync ----------------------------------

def test_fsync_parent_dir_swallows_oserror(tmp_path, monkeypatch):
    """The dir-fsync is best-effort: an ``OSError`` from ``os.open``/``os.fsync``
    (e.g. a filesystem that rejects directory fsync) is swallowed, never raised.
    Forces the POSIX branch so this exercises the swallow on every host."""
    import lib.atomic_write as aw

    monkeypatch.setattr(aw.os, "name", "posix")

    def boom(*a, **k):
        raise OSError("no directory fsync here")

    monkeypatch.setattr(aw.os, "open", boom)
    aw._fsync_parent_dir(tmp_path)  # must not raise


def test_full_write_survives_dir_fsync_failure(tmp_path, monkeypatch):
    """End-to-end: even when the directory fsync fails, the write completes and
    the bytes land. ``os.O_RDONLY`` (0) is the dir-fsync open; tempfile opens the
    temp file with ``O_CREAT|O_RDWR|…`` (nonzero), so only the former is broken.
    Runs natively (no ``os.name`` patch — forcing ``posix`` on Windows would
    break ``pathlib``): exercises the swallow on POSIX, asserts the bytes land on
    every host (Windows skips dir-fsync, so the write trivially succeeds)."""
    import lib.atomic_write as aw

    real_open = os.open

    def maybe_boom(path, flags, *a, **k):
        if flags == os.O_RDONLY:
            raise OSError("dir fsync unsupported")
        return real_open(path, flags, *a, **k)

    monkeypatch.setattr(aw.os, "open", maybe_boom)
    durable_atomic_write(tmp_path / "f.txt", "still-durable")
    assert (tmp_path / "f.txt").read_text(encoding="utf-8") == "still-durable"


def test_windows_skips_directory_fsync(tmp_path, monkeypatch):
    """On Windows there is no directory fsync; the dir-fsync path returns early
    and must not attempt ``os.open`` (meaningless on a directory handle)."""
    import lib.atomic_write as aw

    monkeypatch.setattr(aw.os, "name", "nt")

    def fail_if_called(*a, **k):
        raise AssertionError("os.open must not be called on Windows dir-fsync")

    monkeypatch.setattr(aw.os, "open", fail_if_called)
    aw._fsync_parent_dir(tmp_path)  # returns immediately on nt — no os.open


# --- error path: cleanup + propagation -----------------------------------

def test_replace_failure_cleans_tmp_and_raises(tmp_path, monkeypatch):
    import lib.atomic_write as aw

    def boom(src, dst):
        raise OSError("rename blew up")

    monkeypatch.setattr(aw.os, "replace", boom)
    with pytest.raises(OSError, match="rename blew up"):
        durable_atomic_write(tmp_path / "f.txt", "data")

    # No temp cruft left behind, and the target was never created.
    assert list(tmp_path.iterdir()) == []
