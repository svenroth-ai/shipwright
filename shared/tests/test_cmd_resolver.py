"""Tests for shared/scripts/lib/cmd_resolver.

Cross-platform executable resolution. On Windows, npm/npx need to be resolved
to their `.cmd` shim before subprocess.Popen with shell=False — otherwise
WinError 2 ("system cannot find the file specified").
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from lib.cmd_resolver import resolve_executable  # noqa: E402


def test_unix_returns_name_unchanged(monkeypatch):
    monkeypatch.setattr("os.name", "posix")
    assert resolve_executable("npm") == "npm"
    assert resolve_executable("python") == "python"


def test_windows_returns_which_hit(monkeypatch):
    """Windows: prefer `shutil.which(name)` if it returns a path."""
    monkeypatch.setattr("os.name", "nt")
    with patch("lib.cmd_resolver.shutil.which") as mock_which:
        mock_which.side_effect = lambda n: r"C:\Program Files\nodejs\npm.cmd" if n == "npm" else None
        assert resolve_executable("npm") == r"C:\Program Files\nodejs\npm.cmd"


def test_windows_falls_back_to_dot_cmd(monkeypatch):
    """If `which('npm')` returns None, try `which('npm.cmd')`."""
    monkeypatch.setattr("os.name", "nt")
    with patch("lib.cmd_resolver.shutil.which") as mock_which:
        results = {"npm.cmd": r"C:\Program Files\nodejs\npm.cmd"}
        mock_which.side_effect = lambda n: results.get(n)
        assert resolve_executable("npm") == r"C:\Program Files\nodejs\npm.cmd"


def test_windows_returns_name_when_neither_found(monkeypatch):
    """Best-effort fallback: return the original name. Caller will see the
    error from subprocess.Popen if the exe truly isn't installed."""
    monkeypatch.setattr("os.name", "nt")
    with patch("lib.cmd_resolver.shutil.which", return_value=None):
        assert resolve_executable("nonexistent-tool") == "nonexistent-tool"


def test_windows_does_not_double_resolve_already_dot_cmd(monkeypatch):
    """If caller already passed a name ending in .cmd, don't re-append .cmd."""
    monkeypatch.setattr("os.name", "nt")
    with patch("lib.cmd_resolver.shutil.which") as mock_which:
        mock_which.side_effect = lambda n: r"C:\bin\foo.cmd" if n == "foo.cmd" else None
        assert resolve_executable("foo.cmd") == r"C:\bin\foo.cmd"
