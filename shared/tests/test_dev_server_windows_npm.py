"""Verify dev_server._start_one resolves npm via cmd_resolver on Windows.

Regression: WinError 2 when profile command is `npm --prefix server run dev`
because subprocess.Popen with shell=False can't resolve `npm.cmd` from `npm`.
The fix is cmd_resolver.resolve_executable, NOT shell=True (command-injection
risk with profile-author-supplied commands).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import dev_server  # noqa: E402


def test_start_one_resolves_npm_on_windows(tmp_path, monkeypatch):
    captured: dict = {}

    class FakeProc:
        def __init__(self, cmd_parts, **kwargs):
            captured["cmd_parts"] = cmd_parts
            captured["shell"] = kwargs.get("shell", False)
            captured["kwargs"] = kwargs
            self.pid = 4242

    service = {
        "name": "backend",
        "command": "npm --prefix server run dev",
        "host": "localhost",
        "scheme": "http",
        "port": 3847,
        "ready_path": "/api/diagnostics",
        "ready_timeout_seconds": 60,
        "primary": True,
    }

    monkeypatch.setattr(dev_server.os, "name", "nt")
    monkeypatch.setattr(dev_server.subprocess, "Popen", FakeProc)
    monkeypatch.setattr(
        dev_server,
        "resolve_executable",
        lambda name: r"C:\Program Files\nodejs\npm.cmd" if name == "npm" else name,
    )

    proc, record = dev_server._start_one(service, tmp_path)

    assert captured["cmd_parts"][0] == r"C:\Program Files\nodejs\npm.cmd"
    assert captured["cmd_parts"][1:] == ["--prefix", "server", "run", "dev"]
    # CRITICAL: shell stays False (no command-injection surface).
    assert captured["shell"] is False or "shell" not in captured["kwargs"]
    assert record["pid"] == 4242
    assert record["command"] == "npm --prefix server run dev"  # original preserved


def test_start_one_does_not_resolve_on_unix(tmp_path, monkeypatch):
    """On non-Windows, resolve_executable is a no-op — npm stays as 'npm'."""
    captured: dict = {}

    class FakeProc:
        def __init__(self, cmd_parts, **kwargs):
            captured["cmd_parts"] = cmd_parts
            self.pid = 1

    service = {
        "name": "backend",
        "command": "npm run dev",
        "host": "localhost",
        "scheme": "http",
        "port": 3000,
        "ready_path": "/",
        "ready_timeout_seconds": 60,
        "primary": True,
    }

    monkeypatch.setattr(dev_server.os, "name", "posix")
    monkeypatch.setattr(dev_server.subprocess, "Popen", FakeProc)
    # resolve_executable on posix is a no-op even if called
    dev_server._start_one(service, tmp_path)
    assert captured["cmd_parts"][0] == "npm"
