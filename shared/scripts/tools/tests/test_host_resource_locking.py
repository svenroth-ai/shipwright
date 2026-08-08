"""Native platform proofs for host-resource lock and namespace hardening."""

from __future__ import annotations

import os
import select
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.lib import _host_resource_locking as locking
from scripts.lib import host_resource_lease as lease


def test_runtime_root_rejects_reparse_in_intermediate_component(monkeypatch, tmp_path):
    intermediate = tmp_path / "alias"
    root = intermediate / "private"
    root.mkdir(parents=True)
    original = locking._is_reparse
    monkeypatch.setattr(
        locking, "_is_reparse",
        lambda path: path == intermediate or original(path),
    )
    with pytest.raises(lease.HostLeaseError, match="unsafe host lease path component"):
        locking._safe_runtime_root(root, allow_sticky_shared=False)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink alias proof")
def test_process_registry_key_canonicalizes_symlink_alias(tmp_path):
    physical = tmp_path / "physical"
    physical.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(physical, target_is_directory=True)
    assert locking._ticket_key(alias / "mutex.lock") == locking._ticket_key(
        physical / "mutex.lock")


@pytest.mark.skipif(os.name == "nt", reason="native POSIX fork-lock proof")
def test_posix_fork_child_waits_for_live_parent_lease(monkeypatch, tmp_path):
    monkeypatch.setattr(lease, "repository_identity", lambda _root: "c" * 24)
    lease_root = tmp_path / "leases"
    read_fd, write_fd = os.pipe()
    with lease.host_resource_lease(
            tmp_path, resource="cpu", capacity=1, weight=1,
            owner="fork-parent", lease_root=lease_root):
        child_pid = os.fork()
        if child_pid == 0:
            os.close(read_fd)
            try:
                with lease.host_resource_lease(
                        tmp_path, resource="cpu", capacity=1, weight=1,
                        owner="fork-child", poll_seconds=.01,
                        lease_root=lease_root):
                    os.write(write_fd, b"A")
                code = 0
            except Exception:
                os.write(write_fd, b"E")
                code = 2
            finally:
                os.close(write_fd)
            os._exit(code)
        os.close(write_fd)
        assert not select.select([read_fd], [], [], .2)[0]
    assert select.select([read_fd], [], [], 3)[0]
    assert os.read(read_fd, 1) == b"A"
    os.close(read_fd)
    _pid, status = os.waitpid(child_pid, 0)
    assert os.waitstatus_to_exitcode(status) == 0


def _child_lock_result(path: Path) -> str:
    shared = str(Path(__file__).resolve().parent.parent.parent.parent)
    probe = (
        "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
        "from scripts.lib._host_resource_locking import _lock_byte, _unlock_byte; "
        "h=Path(sys.argv[2]).open('r+b'); ok=_lock_byte(h, blocking=False); "
        "print(int(ok)); _unlock_byte(h) if ok else None"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe, shared, str(path)],
        capture_output=True, text=True, errors="replace", check=True,
    )
    return result.stdout.strip()


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows byte-range proof")
def test_windows_byte_lock_blocks_an_independent_process(tmp_path):
    path = tmp_path / "owner.lock"
    path.write_bytes(b"0")
    with path.open("r+b") as handle:
        assert locking._lock_byte(handle, blocking=False)
        assert _child_lock_result(path) == "0"
        locking._unlock_byte(handle)
        assert _child_lock_result(path) == "1"


@pytest.mark.skipif(os.name == "nt", reason="native POSIX byte-range proof")
def test_posix_byte_lock_blocks_an_independent_process(tmp_path):
    path = tmp_path / "owner.lock"
    path.write_bytes(b"0")
    with path.open("r+b") as handle:
        assert locking._lock_byte(handle, blocking=False)
        assert _child_lock_result(path) == "0"
        locking._unlock_byte(handle)
        assert _child_lock_result(path) == "1"


@pytest.mark.skipif(os.name == "nt", reason="native POSIX permission proof")
def test_posix_private_file_rejects_group_or_world_access(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{}", encoding="utf-8")
    path.chmod(0o644)
    with pytest.raises(lease.HostLeaseError, match="file is not private"):
        locking._safe_file(path)
    path.chmod(0o600)
    locking._safe_file(path)


def test_posix_fallback_uses_sticky_shared_root_and_private_child(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("POSIX permission contract")
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o1777)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    for name in ("TMPDIR", "TEMP", "TMP"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(lease, "_posix_shared_temp_root", lambda: shared)
    root = lease._private_root()
    _root, anchor, allow_sticky = lease._private_location()
    locking._safe_runtime_root(anchor, allow_sticky_shared=allow_sticky)
    lease._safe_dir(root, trusted_parent=shared)
    assert root.stat().st_mode & 0o077 == 0


@pytest.mark.skipif(os.name == "nt", reason="native POSIX runtime-root proof")
def test_posix_fallback_rejects_shared_temp_without_sticky_bit(tmp_path, monkeypatch):
    hostile = tmp_path / "shared-no-sticky"
    hostile.mkdir()
    hostile.chmod(0o777)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    for name in ("TMPDIR", "TEMP", "TMP"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(lease, "_posix_shared_temp_root", lambda: hostile)
    _root, anchor, allow_sticky = lease._private_location()
    with pytest.raises(lease.HostLeaseError, match="lacks sticky"):
        locking._safe_runtime_root(anchor, allow_sticky_shared=allow_sticky)


@pytest.mark.skipif(os.name == "nt", reason="native POSIX runtime-root proof")
def test_posix_fallback_rejects_arbitrary_private_tmpdir(tmp_path, monkeypatch):
    approved = tmp_path / "approved"
    approved.mkdir()
    approved.chmod(0o1777)
    arbitrary = tmp_path / "private"
    arbitrary.mkdir()
    arbitrary.chmod(0o700)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("TMPDIR", str(arbitrary))
    monkeypatch.setattr(lease, "_posix_shared_temp_root", lambda: approved)
    with pytest.raises(lease.HostLeaseError, match="untrusted TMPDIR"):
        lease._private_location()
