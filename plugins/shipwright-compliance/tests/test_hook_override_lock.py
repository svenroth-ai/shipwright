"""The override log: atomic stale-lock break, marker arbiter, restore-proof, one command (U13 follow-ups)."""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "lib"))
import compliance_override as co  # noqa: E402
import git_commit_command as gcc  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.10")
HOOK = "check_rtm_coverage"
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


# --- the override log ---------------------------------------------------------------------

def _log(root: Path, *lines: str) -> None:
    path = root / co.LOG_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.writelines(f"{line}\n" for line in lines)


def _entry(minutes_ago: int = 1) -> str:
    return f"{(NOW - timedelta(minutes=minutes_ago)).strftime('%Y-%m-%dT%H:%M:%SZ')}"


def test_breaking_a_stale_lock_never_takes_a_live_one(tmp_path):
    lock = tmp_path / "x.log.lock"
    lock.write_text("", encoding="utf-8")
    assert co._break_stale(lock)  # fresh: claimed, found live, put back
    assert lock.exists()
    assert [p.name for p in tmp_path.iterdir()] == ["x.log.lock"]  # no residue
    old = time.time() - co.STALE_LOCK_S - 5
    os.utime(lock, (old, old))
    co._break_stale(lock)
    assert not lock.exists() and list(tmp_path.iterdir()) == []
    assert not co._break_stale(lock)  # already gone: a lost race, not an error


def test_a_stale_lock_is_broken_by_exactly_one_of_two_waiters(tmp_path, monkeypatch):
    lock = tmp_path / "x.log.lock"
    lock.write_text("", encoding="utf-8")
    old = time.time() - co.STALE_LOCK_S - 5
    os.utime(lock, (old, old))
    seen, real = [], os.rename
    results = []

    def second_breaker(src, dst):
        if not seen:
            seen.append(1)
            results.append(co._break_stale(Path(src)))  # a rival breaks it first
        return real(src, dst)

    monkeypatch.setattr(co.os, "rename", second_breaker)
    results.append(co._break_stale(lock))  # our rename finds the file gone
    assert sorted(results) == [False, True]
    assert not lock.exists() and list(tmp_path.iterdir()) == []


def test_a_lost_marker_race_does_not_release(tmp_path):
    _log(tmp_path, f"{_entry()} | {HOOK} | OVERRIDE | because")
    found = co.active_override(tmp_path, HOOK, NOW)
    marker = co.marker_path(tmp_path, HOOK, found.at)
    marker.parent.mkdir(parents=True)
    marker.write_text("", encoding="utf-8")  # a rival hook got there first
    failure = co.consume(tmp_path, HOOK, found, NOW)
    assert failure and "concurrent" in failure
    assert co.try_release(tmp_path, HOOK, NOW)[0] is None


def test_an_unwritable_marker_dir_keeps_the_block(tmp_path):
    _log(tmp_path, f"{_entry()} | {HOOK} | OVERRIDE | because")
    (tmp_path / ".shipwright" / "locks").write_text("a file, not a dir", encoding="utf-8")
    released, why = co.try_release(tmp_path, HOOK, NOW)
    assert released is None and "NOT applied" in why
    assert "not a directory" in why and "concurrent" not in why  # not misreported as a race


def test_a_log_without_a_final_newline_is_not_glued_onto(tmp_path):
    path = tmp_path / co.LOG_RELPATH
    path.parent.mkdir(parents=True)
    path.write_bytes(f"{_entry()} | {HOOK} | OVERRIDE | because".encode())  # no newline
    assert co.try_release(tmp_path, HOOK, NOW)[0] is not None
    lines = path.read_text("utf-8").splitlines()
    assert lines[0].endswith("because") and "CONSUMED" in lines[1]
    assert co.try_release(tmp_path, HOOK, NOW)[0] is None


def test_a_lone_consume_wins_and_logs_the_line(tmp_path):
    _log(tmp_path, f"{_entry()} | {HOOK} | OVERRIDE | because")
    released, why = co.try_release(tmp_path, HOOK, NOW)
    assert released is not None and why is None
    assert "| CONSUMED |" in (tmp_path / co.LOG_RELPATH).read_text("utf-8")
    assert co.try_release(tmp_path, HOOK, NOW)[0] is None  # single use


def test_a_restored_log_does_not_revive_a_consumed_override(tmp_path):
    _log(tmp_path, f"{_entry()} | {HOOK} | OVERRIDE | because")
    log = tmp_path / co.LOG_RELPATH
    committed = log.read_text("utf-8")  # what `git restore` brings back: no CONSUMED line
    assert co.try_release(tmp_path, HOOK, NOW)[0] is not None
    log.write_text(committed, encoding="utf-8")
    assert co.active_override(tmp_path, HOOK, NOW) is None
    assert co.active_override(tmp_path, "check_security_scan", NOW) is None  # per hook


def test_an_unrenameable_stale_lock_times_out_instead_of_spinning(tmp_path, monkeypatch):
    log = tmp_path / "x.log"
    lock = tmp_path / "x.log.lock"
    lock.write_text("", encoding="utf-8")
    old = time.time() - co.STALE_LOCK_S - 5
    os.utime(lock, (old, old))
    monkeypatch.setattr(co, "LOCK_WAIT_S", 0.3)
    monkeypatch.setattr(co.os, "rename", lambda *_a: (_ for _ in ()).throw(PermissionError()))
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        with co._locked(log):
            pass
    assert 0.25 <= time.monotonic() - started < 5  # it waited out the deadline, no spin


def test_a_lock_re_taken_by_another_owner_is_not_removed_by_the_displaced_one(tmp_path):
    log = tmp_path / "x.log"
    lock = tmp_path / "x.log.lock"
    with co._locked(log):
        lock.unlink()  # broken from under us ...
        lock.write_text("another-owner", encoding="utf-8")  # ... and re-taken
    assert lock.read_text(encoding="utf-8") == "another-owner"  # the foreign one stays
    lock.unlink()
    with co._locked(log):  # a normal hold still releases its own lock
        pass
    assert not lock.exists()


def test_old_markers_are_swept_but_a_live_one_is_not(tmp_path):
    markers = tmp_path / ".shipwright" / "locks"
    markers.mkdir(parents=True)
    old, fresh = markers / "consumed-h-old", markers / "consumed-h-fresh"
    for item in (old, fresh):
        item.write_text("", encoding="utf-8")
    ancient = time.time() - 3 * 3600
    os.utime(old, (ancient, ancient))
    co.sweep(markers, co.WINDOW + co.CLOCK_SKEW + timedelta(minutes=10))
    assert not old.exists() and fresh.exists()


def test_one_override_releases_one_command_however_many_commits_it_holds(tmp_path):
    """The unit is a hook run: the whole command passes once, the next one is blocked again."""
    _log(tmp_path, f"{_entry()} | {HOOK} | OVERRIDE | because")
    assert len(list(gcc.iter_git_commits("git commit -m a && git commit -m b"))) == 2
    assert co.try_release(tmp_path, HOOK, NOW)[0] is not None  # the one hook run
    assert co.try_release(tmp_path, HOOK, NOW)[0] is None  # the next command


def test_a_read_only_directory_fails_closed_after_the_wait_without_spinning(tmp_path, monkeypatch):
    def deny(*_a, **_k):
        raise PermissionError("read-only")

    monkeypatch.setattr(co.os, "open", deny)
    monkeypatch.setattr(co, "LOCK_WAIT_S", 0.3)  # a pending delete may clear: wait, then fail closed
    started = time.monotonic()
    with pytest.raises(PermissionError):
        with co._locked(tmp_path / "x.log"):
            pass
    assert 0.25 <= time.monotonic() - started < 3


def test_the_security_hook_stays_blocked_after_the_log_is_restored(tmp_path, monkeypatch, capsys):
    import importlib.util
    import io
    import json

    summary = tmp_path / ".shipwright" / "compliance" / "ci-security.json"
    summary.parent.mkdir(parents=True)
    summary.write_text(json.dumps({
        "schema": 1, "scan_date": "2026-07-28T07:51:37Z", "source": "security.yml#1",
        "by_severity": {"critical": 2, "high": 0, "medium": 0, "low": 0}, "total": 2,
        "open_high_critical": 2, "critical_gate": "fail", "prompt_injection": 0,
        "degraded": False}), encoding="utf-8")
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    hook_file = Path(__file__).parent.parent / "scripts" / "hooks" / "check_security_scan.py"
    spec = importlib.util.spec_from_file_location("_sec_hook_restore", hook_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    payload = json.dumps({"tool_input": {"command": "deploy to jelastic"}})
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _log(tmp_path, f"{stamp} | check_security_scan | OVERRIDE | go")
    committed = (tmp_path / co.LOG_RELPATH).read_text("utf-8")  # what git restore brings back
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    assert mod.main() == 0  # released once ...
    (tmp_path / co.LOG_RELPATH).write_text(committed, encoding="utf-8")  # ... then restored
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    assert mod.main() == 2
    capsys.readouterr()


def test_an_unreadable_marker_means_used_not_released(tmp_path, monkeypatch):
    """Path.exists re-raises EACCES: that must keep the block, never crash into a fail-open."""
    _log(tmp_path, f"{_entry()} | {HOOK} | OVERRIDE | because")
    real = Path.exists

    def deny(self):
        if self.name.startswith("consumed-"):
            raise PermissionError("locked")
        return real(self)

    monkeypatch.setattr(Path, "exists", deny)
    assert co.active_override(tmp_path, HOOK, NOW) is None
    assert co.try_release(tmp_path, HOOK, NOW)[0] is None
