"""Unit contract for the reusable host-resource lease."""

from __future__ import annotations

import sys
import errno
import threading
import time
from types import SimpleNamespace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.lib import host_resource_lease as lease
from scripts.lib import _host_resource_locking as locking


def test_state_round_trip_is_utf8_and_preserves_queue_metadata(tmp_path):
    path = tmp_path / "cpu.state.json"
    state = {"version": 1, "capacity": 4, "next_seq": 2, "entries": [{
        "ticket": "a" * 32, "seq": 1, "weight": 2, "owner": "München",
        "run_id": "iterate-test", "pid": 1, "status": "waiting",
    }]}
    lease._write(path, state)
    assert lease._load(path, 4) == state
    assert "München" in path.read_text(encoding="utf-8")


def test_malformed_state_fails_closed_instead_of_minting_capacity(tmp_path):
    path = tmp_path / "cpu.state.json"
    path.write_text("{not-json", encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(lease.HostLeaseError, match="malformed"):
        lease._load(path, 8)


def test_repository_identity_fails_closed_when_git_cannot_resolve(tmp_path):
    with pytest.raises(lease.HostLeaseError, match="repository identity"):
        lease.repository_identity(tmp_path)


def test_state_cannot_claim_more_granted_weight_than_capacity(tmp_path):
    path = tmp_path / "cpu.state.json"
    entries = [{
        "ticket": char * 32, "seq": seq, "weight": 2, "owner": "owner",
        "run_id": "run", "pid": seq, "status": "granted",
    } for seq, char in ((1, "a"), (2, "b"), (3, "c"))]
    lease._write(path, {"version": 1, "capacity": 4, "next_seq": 4,
                        "entries": entries})
    with pytest.raises(lease.HostLeaseError, match="capacity exceeded"):
        lease._load(path, 4)


def test_boolean_serialized_capacity_is_malformed_not_one(tmp_path):
    path = tmp_path / "cpu.state.json"
    lease._write(path, {"version": 1, "capacity": True,
                        "next_seq": 1, "entries": []})
    with pytest.raises(lease.HostLeaseError, match="invalid shape"):
        lease._load(path, 1)


def test_capacity_change_is_allowed_only_when_no_owner_is_recorded(tmp_path):
    path = tmp_path / "cpu.state.json"
    lease._write(path, {"version": 1, "capacity": 8, "next_seq": 1, "entries": []})
    state = lease._load(path, 4)
    assert lease._adopt_capacity(state, 4) and state["capacity"] == 4
    state["entries"].append({"ticket": "x"})
    with pytest.raises(lease.HostLeaseError, match="capacity changed"):
        lease._adopt_capacity(state, 2)


def test_permanent_os_lock_error_fails_instead_of_waiting(monkeypatch, tmp_path):
    def _fail(*_args):
        raise OSError(errno.EIO, "permanent lock failure")

    fake = SimpleNamespace(LK_LOCK=1, LK_NBLCK=2, LK_UNLCK=3, locking=_fail)
    monkeypatch.setitem(sys.modules, "msvcrt", fake)
    monkeypatch.setattr(locking.os, "name", "nt")
    path = tmp_path / "lock"
    path.write_bytes(b"0")
    with path.open("r+b") as handle:
        with pytest.raises(lease.HostLeaseError, match="OS lock failed"):
            locking._lock_byte(handle, blocking=False)


def test_safe_dir_rejects_reparse_in_an_intermediate_component(monkeypatch, tmp_path):
    intermediate = tmp_path / "redirect"
    intermediate.mkdir()
    original = locking._is_reparse
    monkeypatch.setattr(
        locking, "_is_reparse",
        lambda path: path == intermediate or original(path),
    )
    with pytest.raises(lease.HostLeaseError, match="unsafe host lease directory"):
        locking._safe_dir(intermediate / "nested", trusted_parent=tmp_path)


def test_missing_owner_ticket_fails_closed(tmp_path):
    with pytest.raises(lease.HostLeaseError, match="missing or unsafe"):
        locking._probe_dead(tmp_path / "unlinked-live-ticket.owner.lock")


def test_owner_ticket_open_race_fails_closed(monkeypatch, tmp_path):
    path = tmp_path / "owner.lock"
    path.write_bytes(b"0")
    path.chmod(0o600)
    real_safe = locking._safe_file

    def _unlink_after_check(current, **kwargs):
        real_safe(current, **kwargs)
        current.unlink()

    monkeypatch.setattr(locking, "_safe_file", _unlink_after_check)
    with pytest.raises(lease.HostLeaseError, match="could not open owner ticket"):
        locking._probe_dead(path)


def test_owner_lock_closes_raw_fd_when_initial_write_fails(monkeypatch, tmp_path):
    closed = []
    real_close = locking.os.close

    def _fail_write(*_args):
        raise OSError(errno.EIO, "write failed")

    def _record_close(fd):
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr(locking.os, "write", _fail_write)
    monkeypatch.setattr(locking.os, "close", _record_close)
    with pytest.raises(lease.HostLeaseError, match="could not create owner ticket"):
        locking._new_owner_lock(tmp_path, "a" * 32)
    assert len(closed) == 1


def test_failed_release_write_keeps_ticket_and_queue_recovers(monkeypatch, tmp_path):
    monkeypatch.setattr(lease, "repository_identity", lambda _root: "a" * 24)
    real_write = lease._write
    writes = 0

    def _fail_release(path, state):
        nonlocal writes
        writes += 1
        if writes == 3:
            raise lease.HostLeaseError("simulated release write failure")
        real_write(path, state)

    monkeypatch.setattr(lease, "_write", _fail_release)
    lease_root = tmp_path / "leases"
    ticket_path = None
    with pytest.raises(lease.HostLeaseError, match="release write failure"):
        with lease.host_resource_lease(
                tmp_path, resource="cpu", capacity=1, weight=1,
                owner="first", lease_root=lease_root) as grant:
            ticket_path = (lease_root / ("a" * 24) / "tickets"
                           / f"{grant.ticket}.owner.lock")
    assert ticket_path is not None and ticket_path.exists()
    with lease.host_resource_lease(
            tmp_path, resource="cpu", capacity=1, weight=1,
            owner="next", lease_root=lease_root):
        pass


def test_same_process_owner_is_not_reaped_or_over_granted(monkeypatch, tmp_path):
    monkeypatch.setattr(lease, "repository_identity", lambda _root: "b" * 24)
    lease_root = tmp_path / "leases"
    acquired = threading.Event()

    def _second_lease():
        with lease.host_resource_lease(
                tmp_path, resource="cpu", capacity=1, weight=1,
                owner="second-thread", heartbeat_seconds=.02, poll_seconds=.01,
                lease_root=lease_root):
            acquired.set()

    with lease.host_resource_lease(
            tmp_path, resource="cpu", capacity=1, weight=1,
            owner="first-thread", lease_root=lease_root):
        thread = threading.Thread(target=_second_lease)
        thread.start()
        time.sleep(.1)
        assert not acquired.is_set()
    thread.join(timeout=3)
    assert not thread.is_alive() and acquired.is_set()


def test_process_mutex_serializes_same_process_threads(tmp_path):
    path = tmp_path / "cpu.mutex.lock"
    barrier = threading.Barrier(3)
    guard = threading.Lock()
    active = maximum = 0

    def _contend():
        nonlocal active, maximum
        barrier.wait()
        with locking._mutex(path):
            with guard:
                active += 1
                maximum = max(maximum, active)
            time.sleep(.05)
            with guard:
                active -= 1

    threads = [threading.Thread(target=_contend) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=3)
    assert all(not thread.is_alive() for thread in threads)
    assert maximum == 1


@pytest.mark.parametrize("resource", ["", "CPU", "../cpu", "cpu_lease"])
def test_resource_name_cannot_escape_its_namespace(tmp_path, resource):
    with pytest.raises(lease.HostLeaseError, match="resource name"):
        with lease.host_resource_lease(tmp_path, resource=resource, capacity=1,
                                      weight=1, owner="test", lease_root=tmp_path / "l"):
            pass


@pytest.mark.parametrize("capacity,weight", [(0, 1), (2, 0), (2, 3), (True, 1)])
def test_invalid_or_never_satisfiable_weight_is_rejected(tmp_path, capacity, weight):
    with pytest.raises(lease.HostLeaseError):
        with lease.host_resource_lease(tmp_path, resource="cpu", capacity=capacity,
                                      weight=weight, owner="test", lease_root=tmp_path / "l"):
            pass


def test_diagnostic_is_single_line_and_escapes_owner_text():
    line = lease._diagnostic(
        "heartbeat", resource="cpu", run_id="run\nforge", owner="me\rhere",
        blocker={"owner": "other\nowner", "run_id": "run-1"},
        used=2, capacity=4, waited=30.0)
    assert "\n" not in line and "\r" not in line
    assert "queue_owner=other owner" in line and "queue_run_id=run-1" in line
