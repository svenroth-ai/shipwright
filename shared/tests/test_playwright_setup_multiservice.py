"""Verify playwright_setup pivots into the primary frontend service dir
in multi-service repos with no root package.json.

Bug repro: shipwright-webui has client/package.json + server/package.json
but no root package.json. Old code reads <cwd>/package.json → returns
False → tries `npm install` at the root → fails.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import playwright_setup  # noqa: E402


def _make_multiservice_repo(root: Path) -> None:
    """Lay out a fixture repo with client/ + server/ + no root package.json."""
    (root / "client").mkdir(parents=True, exist_ok=True)
    (root / "server").mkdir(parents=True, exist_ok=True)
    (root / "client" / "package.json").write_text(
        json.dumps({"name": "client", "devDependencies": {"vite": "^6.0.0"}}),
        encoding="utf-8",
    )
    (root / "server" / "package.json").write_text(
        json.dumps({"name": "server", "dependencies": {"hono": "^4.7.0"}}),
        encoding="utf-8",
    )


def test_resolve_setup_dir_finds_primary_frontend(tmp_path):
    """When given a multi-service hint, _resolve_setup_dir returns client/."""
    _make_multiservice_repo(tmp_path)
    result = playwright_setup._resolve_setup_dir(
        tmp_path,
        multi_service={"detected": True, "services": [
            {"name": "frontend", "root": "client"},
            {"name": "backend", "root": "server"},
        ]},
    )
    assert result == tmp_path / "client"


def test_resolve_setup_dir_falls_back_to_cwd_for_single_service(tmp_path):
    """When no multi-service info, returns cwd unchanged."""
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    result = playwright_setup._resolve_setup_dir(tmp_path, multi_service=None)
    assert result == tmp_path


def test_setup_uses_resolved_executable_for_npm(tmp_path, monkeypatch):
    """Verify subprocess.run for `npm install` uses the cmd_resolver result."""
    captured: list = []

    def fake_run(cmd, **kwargs):
        captured.append({"cmd": list(cmd), "cwd": kwargs.get("cwd")})

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""

        return _R()

    # Empty cwd — _has_package returns False → triggers install
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "x", "dependencies": {}}), encoding="utf-8"
    )
    monkeypatch.setattr(playwright_setup.os, "name", "nt")
    monkeypatch.setattr(playwright_setup.subprocess, "run", fake_run)
    monkeypatch.setattr(
        playwright_setup,
        "resolve_executable",
        lambda name: rf"C:\fake\{name}.cmd",
    )
    playwright_setup.setup(tmp_path)

    npm_calls = [c for c in captured if c["cmd"] and c["cmd"][0].endswith("npm.cmd")]
    npx_calls = [c for c in captured if c["cmd"] and c["cmd"][0].endswith("npx.cmd")]
    assert npm_calls, f"expected at least one resolved npm.cmd call; got {captured}"
    assert npx_calls, f"expected at least one resolved npx.cmd call; got {captured}"


def test_multiservice_setup_pivots_to_client(tmp_path, monkeypatch):
    """End-to-end: multi-service repo, setup pivots into client/."""
    _make_multiservice_repo(tmp_path)
    captured_cwds: list = []

    def fake_run(cmd, **kwargs):
        captured_cwds.append(str(kwargs.get("cwd", "")))

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""

        return _R()

    monkeypatch.setattr(playwright_setup.subprocess, "run", fake_run)
    monkeypatch.setattr(playwright_setup, "resolve_executable", lambda n: n)

    result = playwright_setup.setup(
        tmp_path,
        multi_service={"detected": True, "services": [
            {"name": "frontend", "root": "client"},
            {"name": "backend", "root": "server"},
        ]},
    )

    assert result["success"] is True
    # Every npm/npx call should run with cwd inside client/, NOT the project root
    client_dir = str(tmp_path / "client")
    assert all(cwd == client_dir for cwd in captured_cwds), (
        f"expected all subprocess cwds to be {client_dir}; got {captured_cwds}"
    )
    assert result.get("setup_dir") == str(tmp_path / "client")
