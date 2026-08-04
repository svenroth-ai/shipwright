"""Bounded-output process supervision for one F0 test-unit attempt.

One dedicated reader drains combined output continuously into a fixed-size byte tail;
the attempt-owned file receives only that tail, so a verbose or wedged child cannot
fill its pipe, grow parent memory, or consume unbounded disk. Windows children enter a
handshake launcher that is assigned to a kill-on-close Job Object before it can spawn
the real command.  POSIX uses one process group.  Every return path reaps the direct
child and tears down any descendants still owned by that attempt.
"""

from __future__ import annotations

import contextlib
import ctypes
import os
import signal
import subprocess  # nosec B404 - caller supplies validated argv, always shell=False
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

RC_TIMEOUT = 124
RC_CANCELLED = 130
DEFAULT_TAIL_BYTES = 64 * 1024
_POLL_SECONDS = 0.05


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    tail: str
    seconds: float
    truncated: bool
    timed_out: bool = False
    cancelled: bool = False


class _BoundedCapture:
    """Thread-safe byte tail; total memory and persisted disk are both capped."""

    def __init__(self, cap: int) -> None:
        self.cap = max(1, int(cap))
        self._tail = bytearray()
        self._total = 0
        self._lock = threading.Lock()

    def append(self, chunk: bytes) -> None:
        with self._lock:
            self._total += len(chunk)
            self._tail.extend(chunk)
            if len(self._tail) > self.cap:
                del self._tail[:-self.cap]

    def snapshot(self) -> tuple[bytes, bool]:
        with self._lock:
            return bytes(self._tail), self._total > self.cap


def _drain_output(pipe, capture: _BoundedCapture) -> None:
    try:
        while chunk := pipe.read(16 * 1024):
            capture.append(chunk)
    except OSError:
        pass


def read_output_tail(path: Path, cap: int = DEFAULT_TAIL_BYTES) -> tuple[str, bool]:
    """Read a deterministic byte tail after an interrupted supervisor unwound."""
    cap = max(1, int(cap))
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > cap:
                fh.seek(-cap, os.SEEK_END)
            raw = fh.read(cap)
    except OSError:
        return "", False
    return raw.decode("utf-8", errors="replace"), size > cap


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _BasicLimit(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", ctypes.c_ulong),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_ulong),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_ulong),
        ("SchedulingClass", ctypes.c_ulong),
    ]


class _ExtendedLimit(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimit),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _WindowsJob:
    """Minimal ctypes Job Object owner; close is the descendant kill boundary."""

    _KILL_ON_CLOSE = 0x00002000
    _EXTENDED_LIMIT_INFORMATION = 9

    def __init__(self) -> None:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.restype = ctypes.c_void_p
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        kernel.SetInformationJobObject.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong]
        kernel.SetInformationJobObject.restype = ctypes.c_int
        kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        kernel.AssignProcessToJobObject.restype = ctypes.c_int
        kernel.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        kernel.TerminateJobObject.restype = ctypes.c_int
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle.restype = ctypes.c_int
        self._kernel = kernel
        self._handle = kernel.CreateJobObjectW(None, None)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = _ExtendedLimit()
        info.BasicLimitInformation.LimitFlags = self._KILL_ON_CLOSE
        if not kernel.SetInformationJobObject(
                self._handle, self._EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(info), ctypes.sizeof(info)):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, process: subprocess.Popen) -> None:
        if not self._kernel.AssignProcessToJobObject(
                self._handle, ctypes.c_void_p(int(process._handle))):  # noqa: SLF001
            raise ctypes.WinError(ctypes.get_last_error())

    def terminate(self) -> None:
        if self._handle:
            self._kernel.TerminateJobObject(self._handle, 1)

    def close(self) -> None:
        if self._handle:
            self._kernel.CloseHandle(self._handle)
            self._handle = None


def _stop_posix_group(proc: subprocess.Popen, *, gentle: bool) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signal.SIGTERM)
    if gentle:
        deadline = time.monotonic() + .5
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(.02)
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signal.SIGKILL)


def run_process(
    argv: list[str], *, cwd: Path, env: dict[str, str], log_path: Path,
    timeout: int | float | None = None,
    cancel_event: threading.Event | None = None,
    tail_bytes: int = DEFAULT_TAIL_BYTES,
) -> ProcessResult:
    """Run one argv and return only its deterministic, byte-capped output tail."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    proc: subprocess.Popen | None = None
    job: _WindowsJob | None = None
    reader: threading.Thread | None = None
    capture = _BoundedCapture(tail_bytes)
    timed_out = cancelled = False
    try:
        if os.name == "nt":
            launcher = Path(__file__).with_name("suite_process_child.py")
            proc = subprocess.Popen(  # nosec B603 - fixed launcher + validated argv
                [sys.executable, str(launcher), "--", *argv], cwd=cwd, env=env,
                shell=False, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            try:
                job = _WindowsJob()
                job.assign(proc)
                assert proc.stdin is not None
                proc.stdin.write(b"1")
                proc.stdin.close()
            except BaseException:
                with contextlib.suppress(OSError):
                    proc.kill()
                with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                    proc.wait(timeout=5)
                if job:
                    job.close()
                raise
        else:
            proc = subprocess.Popen(  # nosec B603 - validated argv, no shell
                argv, cwd=cwd, env=env, shell=False, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        assert proc.stdout is not None
        reader = threading.Thread(
            target=_drain_output, args=(proc.stdout, capture),
            name=f"f0-output-{proc.pid}", daemon=True)
        reader.start()

        deadline = None if timeout is None else started + max(0, float(timeout))
        while proc.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                break
            if deadline is not None and time.monotonic() >= deadline:
                timed_out = True
                break
            time.sleep(_POLL_SECONDS)

        if timed_out or cancelled:
            if job:
                job.terminate()
            else:
                _stop_posix_group(proc, gentle=True)
        elif job is None:
            # The direct child may exit after orphaning a worker. The attempt owns
            # the process group, so normal completion closes that lifecycle too.
            _stop_posix_group(proc, gentle=False)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=5)
        if proc.poll() is None:
            if job:
                job.terminate()
            else:
                _stop_posix_group(proc, gentle=False)
            proc.wait(timeout=5)
    except BaseException:
        if proc is not None and proc.poll() is None:
            if job:
                job.terminate()
            else:
                _stop_posix_group(proc, gentle=False)
            with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                proc.wait(timeout=5)
        raise
    finally:
        if job:
            # KILL_ON_JOB_CLOSE catches descendants orphaned before the wrapper
            # returned; close only after the direct launcher has been reaped.
            job.close()
        if reader:
            reader.join(timeout=5)
        if proc is not None and proc.stdout is not None:
            if reader is not None and reader.is_alive():
                with contextlib.suppress(OSError):
                    proc.stdout.close()
                reader.join(timeout=1)
            with contextlib.suppress(OSError):
                proc.stdout.close()
        raw, truncated = capture.snapshot()
        log_path.write_bytes(raw)
    tail = raw.decode("utf-8", errors="replace")
    rc = (RC_CANCELLED if cancelled else RC_TIMEOUT if timed_out
          else int(proc.returncode if proc and proc.returncode is not None else 126))
    return ProcessResult(rc, tail, time.monotonic() - started, truncated,
                         timed_out=timed_out, cancelled=cancelled)
