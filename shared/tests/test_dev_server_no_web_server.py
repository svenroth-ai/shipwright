"""Profiles that declare no web dev server (library/CLI/plugin stacks)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import dev_server  # type: ignore  # noqa: E402


# ---- profiles without a web dev server ----


@pytest.mark.covers("FR-01.12/AC01")
@pytest.mark.parametrize(
    "profile_data",
    [
        {"services": [], "dev_server": None},
        {"services": []},
        {"services": None, "dev_server": None},
        {"dev_server": None},
    ],
)
def test_profile_without_web_server_raises_clear_error(profile_data, tmp_path):
    with pytest.raises(dev_server.NoDevServerError, match="no web dev server"):
        dev_server._get_services_for_test(profile_data=profile_data, cwd=tmp_path)


@pytest.mark.covers("FR-01.12/AC01")
def test_empty_services_with_legacy_dev_server_still_starts(tmp_path):
    services, _ = dev_server._get_services_for_test(
        profile_data={"services": [], "dev_server": {"command": "x", "port": 4000}},
        cwd=tmp_path,
    )
    assert services[0]["port"] == 4000


@pytest.mark.covers("FR-01.12/AC01")
def test_cmd_start_reports_no_dev_server_instead_of_crashing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        dev_server.profile_config, "_load_profile_data", lambda name: {"services": [], "dev_server": None}
    )
    result = dev_server.cmd_start(tmp_path, profile="python-plugin-monorepo")
    assert result["running"] is False
    assert result["no_dev_server"] is True
    assert "python-plugin-monorepo" in result["error"]


@pytest.mark.covers("FR-01.12/AC01")
def test_non_object_dev_server_is_a_clear_error_not_a_crash(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="object or null"):
        dev_server._get_services_for_test(profile_data={"dev_server": "x"}, cwd=tmp_path)
    monkeypatch.setattr(
        dev_server.profile_config, "_load_profile_data", lambda name: {"dev_server": "x"}
    )
    result = dev_server.cmd_start(tmp_path, profile="p")
    assert result["running"] is False and "invalid services" in result["error"]
    assert "no_dev_server" not in result
