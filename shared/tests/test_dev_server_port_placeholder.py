"""Verify ${VAR:-default} placeholder expansion in profile fields.

Profiles like vite-hono.json use `${PORT:-3847}` so adopt can run a crawl
without colliding with a user dev server on the default port. The
expansion happens at service-normalization time, before validation.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import dev_server  # noqa: E402


def test_port_placeholder_falls_back_to_default(tmp_path, monkeypatch):
    """${PORT:-3847} with no env var set → 3847 (int)."""
    monkeypatch.delenv("PORT", raising=False)
    services, _ = dev_server._get_services_for_test(
        profile_data={
            "services": [
                {"name": "api", "command": "echo hi", "port": "${PORT:-3847}", "ready_path": "/"},
            ]
        },
        cwd=tmp_path,
    )
    assert services[0]["port"] == 3847
    assert isinstance(services[0]["port"], int)


def test_port_placeholder_uses_env_when_set(tmp_path, monkeypatch):
    """${PORT:-3847} with PORT=4001 → 4001."""
    monkeypatch.setenv("PORT", "4001")
    services, _ = dev_server._get_services_for_test(
        profile_data={
            "services": [
                {"name": "api", "command": "echo hi", "port": "${PORT:-3847}", "ready_path": "/"},
            ]
        },
        cwd=tmp_path,
    )
    assert services[0]["port"] == 4001


def test_command_placeholder_expansion(tmp_path, monkeypatch):
    """Placeholders in `command` are expanded too."""
    monkeypatch.setenv("CLIENT_DIR", "client")
    services, _ = dev_server._get_services_for_test(
        profile_data={
            "services": [
                {
                    "name": "front",
                    "command": "npm --prefix ${CLIENT_DIR:-client} run dev",
                    "port": 5173,
                    "ready_path": "/",
                },
            ]
        },
        cwd=tmp_path,
    )
    assert services[0]["command"] == "npm --prefix client run dev"


def test_int_port_without_placeholder_passes_through(tmp_path):
    """Existing profiles with plain int ports keep working unchanged."""
    services, _ = dev_server._get_services_for_test(
        profile_data={
            "services": [
                {"name": "a", "command": "x", "port": 3000, "ready_path": "/"},
            ]
        },
        cwd=tmp_path,
    )
    assert services[0]["port"] == 3000


def test_invalid_port_string_after_expansion_errors(tmp_path, monkeypatch):
    """If the placeholder resolves to non-numeric, _validate_services should reject."""
    monkeypatch.setenv("PORT", "not-a-number")
    import pytest
    with pytest.raises(ValueError, match=r"port"):
        dev_server._get_services_for_test(
            profile_data={
                "services": [
                    {"name": "a", "command": "x", "port": "${PORT:-3847}", "ready_path": "/"},
                ]
            },
            cwd=tmp_path,
        )
