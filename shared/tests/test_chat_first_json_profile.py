"""The bundled `chat-first-json` profile (campaign brief-driven-run, unit B4).

A chat-first app has a served pane, pytest + Playwright, local JSON data and no
deploy. The profile must pass the resolver and the schema, hand the dev server a
declared single-executable block (never the `_DEFAULT_SERVICE` npm fallback), and
stay out of the CI/CodeQL template registries on purpose.
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

_PROFILE = REPO / "shared" / "profiles" / "chat-first-json.json"
_SHELL_META = re.compile(r"[;&|<>$`(){}\\\"'*?!]")


def _data() -> dict:
    return json.loads(_PROFILE.read_text(encoding="utf-8"))


@pytest.mark.covers("FR-01.06")
def test_profile_resolves_as_bundled_and_passes_the_schema(tmp_path):
    res = pr.resolve_profile("chat-first-json", tmp_path)
    assert (res.name, res.source) == ("chat-first-json", "bundled")
    assert res.data["ux_shape"] == "chat-first"
    assert isinstance(res.data["ui_host"], str)


@pytest.mark.covers("FR-01.12/AC01")
def test_dev_server_is_the_declared_block_not_the_default_service(tmp_path):
    services, warnings = dev_server._get_services("chat-first-json", tmp_path)
    assert warnings == [] and len(services) == 1
    svc = services[0]
    assert svc == {"name": "primary", "command": "uv run uvicorn app.main:app --host 127.0.0.1 --port 3900",
                   "host": "127.0.0.1", "scheme": "http", "port": 3900, "ready_path": "/api/health",
                   "ready_timeout_seconds": 60, "primary": True}  # exactly the declared block, no default leaked
    assert svc["command"] == "uv run uvicorn app.main:app --host 127.0.0.1 --port 3900"
    assert svc["command"] != dev_server._DEFAULT_SERVICE["command"]
    assert (svc["port"], svc["ready_path"], svc["primary"]) == (3900, "/api/health", True)
    assert not _SHELL_META.search(svc["command"])  # the WebUI preview starts this one executable


@pytest.mark.covers("FR-01.12/AC01")
def test_profile_declares_a_frontend_and_no_services_list():
    data = _data()
    assert data["stack"]["frontend"]  # the preview button needs stack.frontend
    assert "services" not in data  # the WebUI preview ignores 'services'


@pytest.mark.covers("FR-01.06", "FR-01.01/AC11")
def test_testing_block_names_pytest_and_playwright_and_deploy_is_none():
    data = _data()
    assert data["testing"]["unit"]["command"] == "uv run pytest"
    assert data["testing"]["e2e"]["framework"] == "@playwright/test"  # *.spec.ts keeps journey coverage live
    assert data["deploy"] is None


@pytest.mark.covers("FR-01.13")
def test_ci_and_codeql_mapping_stay_an_explicit_none():
    assert "chat-first-json" not in TEMPLATE_BY_PROFILE
    assert template_path_for_profile("chat-first-json", "bundled") is None
    assert "chat-first-json" not in CODEQL_LANGUAGES_BY_PROFILE
