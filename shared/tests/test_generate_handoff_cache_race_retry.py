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
