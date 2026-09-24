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

import importlib.util
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

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


def _load_hook_module_in_process():
    """Loads the real hook file via ``spec_from_file_location`` — a hook
    script is never on a normal package path, so this is the standard way to
    import one directly (not dynamic code execution: the same mechanism
    ``importlib`` itself uses). Gives tests direct access to
    ``_do_lib_imports``/``_import_lib_with_retry`` without a subprocess."""
    hook_path = _REAL_SCRIPTS / "hooks" / "generate_handoff_on_stop.py"
    spec = importlib.util.spec_from_file_location("generate_handoff_on_stop", hook_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_import_retry_helper_retries_then_succeeds_in_process():
    """Same round-5 retry the tests above prove via a real filesystem race —
    but driven IN-PROCESS through the directly callable
    ``_import_lib_with_retry`` helper, so coverage.py's tracer can see it. A
    subprocess child is invisible to the parent's coverage measurement, so
    the diff-coverage gate reported this loop uncovered despite it being
    exhaustively proven above (feedback_subprocess_tests_are_invisible_to_
    diff_coverage). Tier-3 review, PR #796 round 14 rejected an earlier
    version of this test that used ``exec(compile(...))`` on extracted
    source text as a security-blocking dynamic-execution pattern —
    ``_import_lib_with_retry``'s ``do_import`` parameter exists precisely so
    a test can inject a controlled failure without it."""
    module = _load_hook_module_in_process()
    calls = {"n": 0}

    def flaky_import():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ModuleNotFoundError("lib.atomic_write")
        return module._do_lib_imports()

    result = module._import_lib_with_retry(do_import=flaky_import, attempts=5, delay=0)

    assert calls["n"] == 2, "expected exactly one retry after the first failure"
    assert result == module._do_lib_imports()


def test_import_retry_helper_raises_after_exhausting_attempts():
    """The retry has the same bound as the real filesystem-race case above —
    a persistent failure must still raise, not hang or swallow it silently."""
    module = _load_hook_module_in_process()

    def always_fails():
        raise ModuleNotFoundError("lib.atomic_write")

    with pytest.raises(ModuleNotFoundError):
        module._import_lib_with_retry(do_import=always_fails, attempts=3, delay=0)


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
