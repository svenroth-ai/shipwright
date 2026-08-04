"""Real child-tree cleanup and bounded byte-tail probes for the F0 supervisor."""

from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.tools.suite_process import run_process
import scripts.tools.suite_process as process_mod


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)
        if not handle:
            return False
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(handle, 0) == 258
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def test_byte_tail_is_exactly_capped_and_decodes_invalid_utf8(tmp_path):
    script = "import os; os.write(1, b'A' * 20 + b'\\xffEND')"
    result = run_process(
        [sys.executable, "-c", script], cwd=tmp_path, env=os.environ.copy(),
        log_path=tmp_path / "attempt.log", tail_bytes=8,
    )
    assert result.returncode == 0
    assert len(result.tail.encode("utf-8")) <= 12  # replacement char expands to 3 bytes
    assert result.tail.endswith("END") and "\ufffd" in result.tail
    assert result.truncated is True


def test_verbose_child_cannot_grow_the_live_attempt_file_past_the_cap(tmp_path):
    cap = 1024
    result = run_process(
        [sys.executable, "-c", "import os; os.write(1, b'x' * 2_000_000)"],
        cwd=tmp_path, env=os.environ.copy(), log_path=tmp_path / "bounded.log",
        tail_bytes=cap, timeout=10,
    )
    assert result.returncode == 0 and result.truncated
    assert (tmp_path / "bounded.log").stat().st_size == cap


def test_missing_attempt_log_has_an_explicit_empty_tail(tmp_path):
    assert process_mod.read_output_tail(tmp_path / "missing.log") == ("", False)


def test_posix_group_cleanup_uses_term_then_kill(monkeypatch):
    signals = []
    monkeypatch.setattr(process_mod.signal, "SIGTERM", 15, raising=False)
    monkeypatch.setattr(process_mod.signal, "SIGKILL", 9, raising=False)
    monkeypatch.setattr(
        process_mod.os, "killpg", lambda pid, sig: signals.append((pid, sig)),
        raising=False)
    monkeypatch.setattr(process_mod.time, "sleep", lambda _seconds: None)

    class _Proc:
        pid = 42

        @staticmethod
        def poll():
            return 1

    process_mod._stop_posix_group(_Proc(), gentle=True)
    assert signals == [(42, process_mod.signal.SIGTERM),
                       (42, process_mod.signal.SIGKILL)]


def test_timeout_kills_and_reaps_descendant_tree(tmp_path):
    pid_file = tmp_path / "grandchild.pid"
    grandchild = "import time; time.sleep(60)"
    child = (
        "import pathlib,subprocess,sys,time; "
        f"p=subprocess.Popen([sys.executable,'-c',{grandchild!r}]); "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid)); time.sleep(60)"
    )
    result = run_process(
        [sys.executable, "-c", child], cwd=tmp_path, env=os.environ.copy(),
        log_path=tmp_path / "timeout.log", timeout=1,
    )
    assert result.timed_out and result.returncode == 124
    pid = int(pid_file.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 5
    while _pid_alive(pid) and time.monotonic() < deadline:
        time.sleep(.05)
    assert not _pid_alive(pid), "grandchild survived supervisor timeout"
    followup = run_process(
        [sys.executable, "-c", "print('clean-next-run')"], cwd=tmp_path,
        env=os.environ.copy(), log_path=tmp_path / "timeout.log", timeout=5,
    )
    assert followup.returncode == 0 and "clean-next-run" in followup.tail


def test_normal_parent_exit_still_kills_orphaned_grandchild(tmp_path):
    pid_file = tmp_path / "orphan.pid"
    script = (
        "import pathlib,subprocess,sys; "
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid))"
    )
    result = run_process(
        [sys.executable, "-c", script], cwd=tmp_path, env=os.environ.copy(),
        log_path=tmp_path / "normal.log", timeout=5,
    )
    assert result.returncode == 0
    pid = int(pid_file.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 5
    while _pid_alive(pid) and time.monotonic() < deadline:
        time.sleep(.05)
    assert not _pid_alive(pid), "orphan survived normal parent completion"


def test_cancellation_kills_tree_without_waiting_for_timeout(tmp_path):
    cancel = threading.Event()
    threading.Timer(.2, cancel.set).start()
    started = time.monotonic()
    result = run_process(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        cwd=tmp_path, env=os.environ.copy(), log_path=tmp_path / "cancel.log",
        timeout=30, cancel_event=cancel,
    )
    assert result.cancelled and result.returncode == 130
    assert time.monotonic() - started < 5


def test_windows_native_uv_pytest_xdist_tree_is_reaped_and_reusable(tmp_path):
    if os.name != "nt":
        # test-hygiene: allow-silent-skip — Windows Job Objects do not exist on
        # POSIX; the separate process-group tests exercise that platform contract.
        pytest.skip("Windows Job Object native probe")
    assert shutil.which("uv"), "uv is required by the F0 runner itself"
    pid_dir = tmp_path / "pids"
    pid_dir.mkdir()
    test_file = tmp_path / "test_native_tree.py"
    grandchild_marker = pid_dir / "grandchild.pid"
    middle = (
        "import pathlib,subprocess,sys; "
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
        f"pathlib.Path({str(grandchild_marker)!r}).write_text(str(p.pid))"
    )
    body = (
        "import os, pathlib, subprocess, sys, time\n"
        "def test_tree():\n"
        "    root = pathlib.Path(os.environ['SHIPWRIGHT_TREE_PID_DIR'])\n"
        "    root.joinpath('pytest.pid').write_text(str(os.getpid()))\n"
        f"    middle = {middle!r}\n"
        "    subprocess.Popen([sys.executable, '-c', middle])\n"
        "    for index in range(2):\n"
        "        p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "        root.joinpath(f'worker-{index}.pid').write_text(str(p.pid))\n"
        "    while not root.joinpath('grandchild.pid').exists(): time.sleep(.02)\n"
        "    time.sleep(60)\n"
    )
    test_file.write_text(body, encoding="utf-8")
    env = os.environ.copy()
    env["SHIPWRIGHT_TREE_PID_DIR"] = str(pid_dir)
    cancel = threading.Event()

    def _cancel_when_tree_exists():
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if len(list(pid_dir.glob("*.pid"))) >= 4:
                cancel.set()
                return
            time.sleep(.02)

    watcher = threading.Thread(target=_cancel_when_tree_exists)
    watcher.start()
    result = run_process(
        ["uv", "run", "--python", "3.11", "--with", "pytest",
         "--with", "pytest-xdist", "pytest", str(test_file), "-q", "-n", "2"],
        cwd=tmp_path, env=env, log_path=tmp_path / "native.log", timeout=35,
        cancel_event=cancel,
    )
    watcher.join(5)
    assert result.cancelled, result.tail
    pids = [int(path.read_text(encoding="utf-8")) for path in pid_dir.glob("*.pid")]
    assert len(pids) >= 4
    deadline = time.monotonic() + 5
    while any(_pid_alive(pid) for pid in pids) and time.monotonic() < deadline:
        time.sleep(.05)
    assert not any(_pid_alive(pid) for pid in pids)
    followup = run_process(
        ["uv", "run", "--python", "3.11", "python", "-c", "print('reused')"],
        cwd=tmp_path, env=env, log_path=tmp_path / "native-followup.log", timeout=30,
    )
    assert followup.returncode == 0 and "reused" in followup.tail
