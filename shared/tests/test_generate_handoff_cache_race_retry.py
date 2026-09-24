"""iterate-2026-09-24-stop-hook-cache-race: the hook must survive a momentary
absence of shared/scripts/lib, not just theorize that it would.

update-marketplace.sh's atomic cache swap moves the live shared/ tree aside
and the staged one into place with two back-to-back renames; a Stop hook
whose interpreter reaches the ``lib.*`` import between those renames sees no
``lib`` package at all. Reproduced directly here: copy the real hook and
``lib/`` into an isolated tree, rename ``lib`` away, restore it from a
background thread partway through the hook's retry budget, and assert the
import still succeeds instead of raising ModuleNotFoundError.
"""

import builtins
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

_REAL_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _prepare_isolated_hook_tree(tmp_path: Path) -> Path:
    """Copy just the hook file and lib/ into tmp_path; returns the hooks dir."""
    hooks_dir = tmp_path / "scripts" / "hooks"
    hooks_dir.mkdir(parents=True)
    shutil.copy(
        _REAL_SCRIPTS / "hooks" / "generate_handoff_on_stop.py",
        hooks_dir / "generate_handoff_on_stop.py",
    )
    shutil.copytree(
        _REAL_SCRIPTS / "lib", tmp_path / "scripts" / "lib",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    # lib.phase_quality reaches into tools.verifiers.common; without it this
    # would fail on an unrelated ModuleNotFoundError, not the one under test.
    shutil.copytree(
        _REAL_SCRIPTS / "tools", tmp_path / "scripts" / "tools",
        ignore=shutil.ignore_patterns("__pycache__", "tests"),
    )
    return hooks_dir


def test_import_survives_lib_vanishing_and_reappearing_mid_retry(tmp_path):
    hooks_dir = _prepare_isolated_hook_tree(tmp_path)
    lib_dir = tmp_path / "scripts" / "lib"
    hidden = tmp_path / "lib-hidden-during-swap"
    lib_dir.rename(hidden)  # simulate the window between the two renames

    def restore_after_delay():
        time.sleep(0.15)  # well inside the retry loop's ~1s budget
        hidden.rename(lib_dir)

    thread = threading.Thread(target=restore_after_delay)
    thread.start()
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import generate_handoff_on_stop"],
            cwd=hooks_dir, capture_output=True, text=True, timeout=15,
        )
    finally:
        thread.join()

    assert result.returncode == 0, result.stderr
    assert "ModuleNotFoundError" not in result.stderr, result.stderr


def test_import_retry_loop_retries_then_succeeds_in_process():
    """Same round-5 retry loop the tests above prove via a real filesystem
    race — but driven IN-PROCESS instead of through ``subprocess.run``, so
    coverage.py's tracer can see it. A subprocess child is invisible to the
    parent's coverage measurement, so the diff-coverage gate reported the
    except/raise/sleep lines uncovered despite them being exhaustively
    proven above (feedback_subprocess_tests_are_invisible_to_diff_coverage).
    Extracts the literal ``for``/``except`` block and drives it with a
    patched ``__import__`` that fails once before delegating to the real
    one — the race itself needs no re-proving here, only the loop's own
    control flow needs to execute where coverage is watching."""
    hook_path = _REAL_SCRIPTS / "hooks" / "generate_handoff_on_stop.py"
    src = hook_path.read_text(encoding="utf-8")
    start = src.index("for _attempt in range(20):")
    end = src.index("\n\n", start)
    # Padded with the file's own leading newlines so the compiled code
    # object's line numbers match generate_handoff_on_stop.py's real ones —
    # coverage.py (and diff-cover after it) attributes hits by (filename,
    # lineno), so line 1 here would silently miss the lines the gate checks.
    start_line = src.count("\n", 0, start)
    loop_src = ("\n" * start_line) + src[start:end]

    real_import = builtins.__import__
    calls = {"n": 0}

    def flaky_import(name, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    patched_builtins = builtins.__dict__.copy()
    patched_builtins["__import__"] = flaky_import
    namespace = {"time": time, "__builtins__": patched_builtins}
    exec(compile(loop_src, str(hook_path), "exec"), namespace)  # noqa: S102

    assert calls["n"] > 1, "the retry never attempted a second import after the first failure"
    assert "durable_atomic_write" in namespace, "the loop did not complete a successful retry"


def test_import_fails_when_lib_never_reappears(tmp_path):
    """The retry has a bound — this is not a silent infinite hang."""
    hooks_dir = _prepare_isolated_hook_tree(tmp_path)
    shutil.rmtree(tmp_path / "scripts" / "lib")

    result = subprocess.run(
        [sys.executable, "-c", "import generate_handoff_on_stop"],
        cwd=hooks_dir, capture_output=True, text=True, timeout=15,
    )

    assert result.returncode != 0
    assert "ModuleNotFoundError" in result.stderr, result.stderr


# Tier-3 review, PR #796 round 5: the swap can also lose a narrower race than
# "lib never existed" — the finder locates lib/atomic_write.py (stat
# succeeds), but the loader's own subsequent open() of that same path can
# still lose to the directory being renamed away in between, raising
# FileNotFoundError instead of ModuleNotFoundError. A real filesystem
# reproduction needs nanosecond-scale timing a test can't force, so this
# drives the exact same code path deterministically by making
# SourceFileLoader.get_data raise FileNotFoundError once, then succeed.
_FLAKY_LOADER_PATCH = """
import importlib.machinery
_orig_get_data = importlib.machinery.SourceFileLoader.get_data
_state = {"raised": False}
def _flaky_get_data(self, path):
    # Only the .py source read is unguarded in CPython's get_code() — the
    # .pyc bytecode-cache read just above it is already wrapped in the
    # stdlib's own try/except OSError, so matching that path too would
    # trigger the (harmless, pre-existing) cache-miss fallback instead of
    # the race this test exists to reproduce.
    if path.endswith("atomic_write.py") and not _state["raised"]:
        _state["raised"] = True
        raise FileNotFoundError(path)
    return _orig_get_data(self, path)
importlib.machinery.SourceFileLoader.get_data = _flaky_get_data
import generate_handoff_on_stop
"""

_ALWAYS_FLAKY_LOADER_PATCH = """
import importlib.machinery
_orig_get_data = importlib.machinery.SourceFileLoader.get_data
def _always_flaky_get_data(self, path):
    if path.endswith("atomic_write.py"):
        raise FileNotFoundError(path)
    return _orig_get_data(self, path)
importlib.machinery.SourceFileLoader.get_data = _always_flaky_get_data
import generate_handoff_on_stop
"""


def test_import_survives_a_transient_filenotfounderror_from_the_loaders_own_open(tmp_path):
    hooks_dir = _prepare_isolated_hook_tree(tmp_path)

    result = subprocess.run(
        [sys.executable, "-c", _FLAKY_LOADER_PATCH],
        cwd=hooks_dir, capture_output=True, text=True, timeout=15,
    )

    assert result.returncode == 0, result.stderr
    assert "FileNotFoundError" not in result.stderr, result.stderr


def test_import_fails_when_the_loaders_open_never_recovers(tmp_path):
    """The FileNotFoundError branch of the retry has the same bound — a
    persistent failure must still raise, not hang or swallow it silently."""
    hooks_dir = _prepare_isolated_hook_tree(tmp_path)

    result = subprocess.run(
        [sys.executable, "-c", _ALWAYS_FLAKY_LOADER_PATCH],
        cwd=hooks_dir, capture_output=True, text=True, timeout=15,
    )

    assert result.returncode != 0
    assert "FileNotFoundError" in result.stderr, result.stderr
