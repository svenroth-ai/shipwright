"""dev_server resolves profiles through the stack-profile resolver (campaign S2).

Per-loader table (BRIEF S2 1a), dev_server row: a reserved sentinel (generic /
detecting) and "no profile" keep the ``shipwright_build_config.json`` ``dev_url``
fallback; an unknown name, a corrupt/invalid winning file or a too-new
``schema_version`` is an ERROR - never "no profile". Tagged to FR-01.06 (see
shared/tests/test_profile_resolver.py for the FR note).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import dev_server  # noqa: E402
from shared.tests.profile_test_fixtures import proj_dir, write_profile  # noqa: E402
from shared.tests.profile_test_fixtures import profile_project, profile_user_dir  # noqa: E402,F401  (module-local fixtures: "project", "user_dir")

pytestmark = pytest.mark.covers("FR-01.06")

SERVICE = {"name": "web", "command": "node srv.js", "port": 4321, "host": "localhost", "scheme": "http"}


def _start(project: Path, profile):
    proc = MagicMock(pid=42)
    proc.poll.return_value = None
    with patch("dev_server.subprocess.Popen", return_value=proc) as popen, \
         patch("dev_server._is_port_in_use_for_host", return_value=False), \
         patch("dev_server._wait_for_service", return_value=(True, "")):
        return dev_server.cmd_start(project, profile), popen


def test_custom_project_profile_is_used_and_source_reported(project, capsys):
    write_profile(proj_dir(project), "my-stack", services=[SERVICE])
    services, _warn, source = dev_server.profile_config._get_services_resolved("my-stack", project)
    assert source == "project" and services[0]["port"] == 4321
    result, _ = _start(project, "my-stack")
    assert result["profile_source"] == "project"
    assert "source=project" in capsys.readouterr().err  # D8a: the source line, on stderr


def test_corrupt_winning_profile_fails_and_bundled_of_that_name_is_not_used(project):
    path = proj_dir(project) / "vite-hono.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    result, popen = _start(project, "vite-hono")
    assert result["running"] is False and result["kind"] == "invalid"
    assert str(path) in result["error"]
    popen.assert_not_called()


def test_unknown_profile_is_an_error_naming_the_searched_paths(project):
    result, popen = _start(project, "no-such-stack")
    assert result["kind"] == "not_found" and result["running"] is False
    assert "Searched" in result["error"] and ".shipwright" in result["error"]
    popen.assert_not_called()


def test_too_new_schema_version_is_drift_not_a_fallback(project):
    write_profile(proj_dir(project), "my-stack", schema_version=99, services=[SERVICE])
    result, popen = _start(project, "my-stack")
    assert result["kind"] == "schema_drift" and "schema_version" in result["error"]
    popen.assert_not_called()


@pytest.mark.parametrize("profile", ["generic", "detecting", None])
def test_sentinel_and_no_profile_keep_the_build_config_dev_url_fallback(project, profile):
    (project / "shipwright_build_config.json").write_text(
        json.dumps({"dev_url": "http://localhost:5555"}), encoding="utf-8")
    services, _warn, source = dev_server.profile_config._get_services_resolved(profile, project)
    assert services[0]["port"] == 5555
    assert source == ("builtin" if profile else None)


def test_shadowing_a_bundled_name_warns_prominently_at_resolution(project, capsys):
    write_profile(proj_dir(project), "vite-hono", services=[SERVICE])
    dev_server.profile_config._get_services("vite-hono", project)
    err = capsys.readouterr().err
    assert "shadows the bundled profile 'vite-hono'" in err and "source=project" in err


def test_bundled_profile_behaviour_is_unchanged(project, monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("VITE_PORT", raising=False)
    services, _warn, source = dev_server.profile_config._get_services_resolved("vite-hono", project)
    assert source == "bundled" and {s["name"] for s in services} == {"backend", "frontend"}


def test_profiles_dir_seam_still_redirects_the_bundled_source(project, tmp_path):
    bundled = tmp_path / "bundled"
    write_profile(bundled, "seam-only", dev_server={"command": "x", "port": 4000})
    with patch("dev_server._profiles_dir", return_value=bundled):
        services, _w, source = dev_server.profile_config._get_services_resolved("seam-only", project)
    assert source == "bundled" and services[0]["port"] == 4000


# ---- numeric normalisation (S1 hand-off 3) ------------------------------------------------
@pytest.mark.parametrize("raw", [3000.0, "3000"])
def test_integral_float_and_digit_string_ports_are_coerced(raw):
    legacy = dev_server.profile_config._normalize_legacy_dev_server({"port": raw})
    assert legacy["port"] == 3000 and isinstance(legacy["port"], int)
    entry = dev_server.profile_config._normalize_service_entry({**SERVICE, "port": raw})
    assert entry["port"] == 3000 and isinstance(entry["port"], int)


@pytest.mark.parametrize("raw", [float("nan"), float("inf"), float("-inf"), 1e300, 3000.5, 0, 70000])
def test_non_finite_fractional_and_out_of_range_ports_are_rejected(raw):
    with pytest.raises(ValueError):
        dev_server.profile_config._normalize_legacy_dev_server({"port": raw})
    if isinstance(raw, float):
        with pytest.raises(ValueError):
            dev_server.profile_config._normalize_service_entry({**SERVICE, "port": raw})


def test_integral_float_ready_timeout_is_coerced_and_nan_rejected():
    entry = dev_server.profile_config._normalize_service_entry({**SERVICE, "ready_timeout_seconds": 30.0})
    assert entry["ready_timeout_seconds"] == 30
    with pytest.raises(ValueError):
        dev_server.profile_config._normalize_service_entry(
            {**SERVICE, "ready_timeout_seconds": float("nan")})


def test_nan_infinity_in_a_profile_file_is_invalid_json(project):
    path = proj_dir(project) / "my-stack.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"name": "my-stack", "dev_server": {"port": NaN}}', encoding="utf-8")
    result, _ = _start(project, "my-stack")
    assert result["kind"] == "invalid" and "not valid JSON" in result["error"]


def test_missing_bundled_file_is_an_error_not_the_legacy_map(project, tmp_path):
    """The old PROFILE_DEV_SERVERS fallback hid a broken install; now it names the search."""
    empty = tmp_path / "empty-bundled"
    empty.mkdir()
    with patch("dev_server._profiles_dir", return_value=empty):
        result, popen = _start(project, "supabase-nextjs")
    assert result["kind"] == "not_found" and str(empty) in result["error"]
    popen.assert_not_called()


def test_mixed_case_sentinel_is_a_name_error_not_a_sentinel(project):
    result, _ = _start(project, "Generic")
    assert result["kind"] == "invalid" and "reserved name" in result["error"]


def test_d6_declared_profile_keys_exist_in_the_schema():
    """D6 (forward only): every key the dev_server loader declares it reads is a schema property."""
    from dev_server import _profile_input
    schema = json.loads((Path(__file__).resolve().parents[1] / "schemas" / "stack_profile.schema.json")
                        .read_text(encoding="utf-8"))
    assert _profile_input.PROFILE_KEYS_READ and set(_profile_input.PROFILE_KEYS_READ) <= set(schema["properties"])


def test_bool_ports_and_timeouts_are_rejected_not_passed_through():
    for field in ("port", "ready_timeout_seconds"):
        with pytest.raises(ValueError, match="whole number"):
            dev_server.profile_config._normalize_service_entry({**SERVICE, field: True})
    with pytest.raises(ValueError, match="whole number"):
        dev_server.profile_config._normalize_legacy_dev_server({"port": True})


def test_cli_maps_resolver_error_kinds_to_exit_codes(project, capsys):
    from dev_server.cli import main_with_args
    assert main_with_args(["start", "--cwd", str(project), "--profile", "no-such-stack"]) == 2
    path = proj_dir(project) / "vite-hono.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    assert main_with_args(["start", "--cwd", str(project), "--profile", "vite-hono"]) == 3
    capsys.readouterr()
