"""The bundled `skill-companion-app` profile (campaign e2e-run-findings, unit E2).

A skill-backed app is a skill/plugin (front door, in the Claude desktop app or the
terminal) plus a companion: a served HTML board and a Python backend with a JSON data
folder, started and stopped by the skill. These tests pin what each phase does with
such an app today, by calling the real consumers (never a subprocess).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "shared" / "scripts"))

import dev_server  # type: ignore  # noqa: E402
import profile_resolver as pr  # type: ignore  # noqa: E402
from lib.ci_workflow import TEMPLATE_BY_PROFILE, template_path_for_profile  # noqa: E402
from lib.codeql_workflow import CODEQL_LANGUAGES_BY_PROFILE  # noqa: E402

_NAME = "skill-companion-app"
_PROFILE = REPO / "shared" / "profiles" / f"{_NAME}.json"
_SHELL_META = re.compile(r"[;&|<>$`(){}\\\"'*?!]")
_HOSTS = {"desktop-app", "terminal"}
_DELIVERIES = {"skill", "plugin"}


def _data() -> dict:
    return json.loads(_PROFILE.read_text(encoding="utf-8"))


def _sc() -> dict:
    """The skill-companion facts. They sit under a comment key: no schema key, no reader yet."""
    return _data()["_skill_companion"]


@pytest.mark.covers("FR-01.06")
def test_resolves_as_bundled_and_passes_the_schema(tmp_path):
    res = pr.resolve_profile(_NAME, tmp_path)
    assert (res.name, res.source) == (_NAME, "bundled")
    assert res.data["ux_shape"] == "skill-companion"
    assert _NAME in pr.bundled_names()


@pytest.mark.covers("FR-01.02")
def test_describes_the_host_the_delivery_and_the_companion():
    d, sc = _data(), _sc()
    assert set(sc["host"]) == _HOSTS  # desktop app and terminal
    assert sc["delivery"] in _DELIVERIES
    life = sc["companion"]["lifecycle"]
    assert life["owner"] == "skill"  # the skill starts and stops the companion
    assert life["health_path"] == d["dev_server"]["ready_path"]
    assert sc["companion"]["bind"]["port"] == 3901
    assert d["dev_server"]["port"] != sc["companion"]["bind"]["port"]  # dev/E2E never attach to the real companion
    assert sc["companion"]["ui"]["served_by"] == "backend"
    assert "outside the plugin install" in sc["data_folder"]["location"]  # a plugin update must not wipe data
    assert sc["data_folder"]["contents"].startswith("JSON")


@pytest.mark.covers("FR-01.06")
def test_the_four_concepts_are_not_top_level_keys_until_a_reader_exists():
    # Operator decision (architecture review, E2): nothing reads host/delivery/companion/data_folder,
    # so they are not schema keys and not top-level profile keys. The unit that adds a reader promotes them.
    d = _data()
    for key in ("host", "delivery", "companion", "data_folder"):
        assert key not in d and key in _sc()
    # the resolver keeps comment keys, so the convention survives loading
    assert "_skill_companion" in pr.resolve_profile(_NAME, REPO).data


@pytest.mark.covers("FR-01.12/AC01")
def test_preview_and_browser_verify_start_exactly_the_declared_block(tmp_path):
    services, warnings = dev_server._get_services(_NAME, tmp_path)
    assert warnings == [] and len(services) == 1
    svc = services[0]
    assert svc["command"] == _data()["dev_server"]["command"]
    assert svc["command"] != dev_server._DEFAULT_SERVICE["command"]  # no npm fallback
    assert (svc["host"], svc["port"], svc["ready_path"]) == ("127.0.0.1", 3911, "/api/health")
    assert not _SHELL_META.search(svc["command"])  # the WebUI preview starts this one executable
    assert svc["port"] not in (3900, 3901)  # chat-first-json and the real companion keep their ports


@pytest.mark.covers("FR-01.12/AC01")
def test_declares_a_frontend_and_no_services_list():
    d = _data()
    assert d["stack"]["frontend"]
    assert "services" not in d  # the WebUI preview ignores 'services'


@pytest.mark.covers("FR-01.08")
def test_deploy_phase_has_nothing_to_deploy_and_no_ci_template():
    d = _data()
    assert d["deploy"] is None  # the plugin is installed, not deployed
    assert _NAME not in TEMPLATE_BY_PROFILE
    assert template_path_for_profile(_NAME, "bundled") is None
    assert _NAME not in CODEQL_LANGUAGES_BY_PROFILE


@pytest.mark.covers("FR-01.05")
def test_build_scaffold_folders_are_the_plugin_shape():
    folders = _data()["folder_structure"]
    for must in (".claude-plugin/", "skills/", "backend/", "board/", "tests/", "e2e/"):
        assert must in folders
    for tooling in ("pyproject.toml", "package.json", "playwright.config.ts"):
        assert tooling in folders  # uv pytest and Playwright need their project files
    assert "node_modules/" not in folders and "src/" not in folders  # dev tooling only, not a node app


@pytest.mark.covers("FR-01.06")
def test_chat_first_json_is_kept_for_existing_apps():
    assert "chat-first-json" in pr.bundled_names()
