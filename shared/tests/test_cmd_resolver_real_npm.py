"""Real-subprocess verification of cmd_resolver against the host's actual npm.

Marked `slow` — only runs with `pytest -m slow`. Requires npm on PATH.
The point: prove that on a real Windows installation, `resolve_executable("npm")`
returns a path that subprocess.Popen can ACTUALLY invoke with shell=False
(i.e. the original WinError 2 bug really is fixed end-to-end, not just in mocks).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from lib.cmd_resolver import resolve_executable  # noqa: E402


_HAS_NPM = shutil.which("npm") is not None or shutil.which("npm.cmd") is not None


pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not _HAS_NPM, reason="npm not on PATH"),
]


def test_resolve_executable_returns_invokable_npm():
    """resolve_executable('npm') must give us a path subprocess.Popen can run."""
    resolved = resolve_executable("npm")
    # On Unix `resolved == 'npm'`; on Windows it should be an absolute path
    # ending in .cmd / .exe / .bat.
    if os.name == "nt":
        assert os.path.isabs(resolved), f"expected absolute path on Windows, got {resolved}"
        assert any(resolved.lower().endswith(ext) for ext in (".cmd", ".exe", ".bat")), (
            f"expected .cmd/.exe/.bat, got {resolved}"
        )

    # The actual end-to-end test — call it, shell=False, no shell=True bypass.
    r = subprocess.run(
        [resolved, "--version"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0, f"npm --version failed: rc={r.returncode}, stderr={r.stderr[:300]}"
    # npm --version emits "X.Y.Z" — at least 3 chars and contains a dot
    out = r.stdout.strip()
    assert "." in out and len(out) >= 3, f"unexpected npm version output: {out!r}"


def test_resolve_executable_returns_invokable_npx():
    """Same end-to-end check for npx — used by playwright_setup + route_crawler."""
    if not (shutil.which("npx") or shutil.which("npx.cmd")):
        pytest.skip("npx not on PATH")
    resolved = resolve_executable("npx")
    r = subprocess.run(
        [resolved, "--version"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0, f"npx --version failed: rc={r.returncode}, stderr={r.stderr[:300]}"


def test_resolve_executable_unknown_does_not_crash():
    """A name that genuinely doesn't exist still returns a string (the original
    name) — we don't raise. Subprocess.Popen will then surface the real error."""
    result = resolve_executable("definitely-not-installed-tool-xyz-12345")
    assert isinstance(result, str)
    assert result  # non-empty
