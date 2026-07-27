"""Tests for Jelastic client (unit tests with mocked HTTP)."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from jelastic_client import DEFAULT_API_URL, JelasticClient, JelasticError


@pytest.fixture
def client():
    return JelasticClient(token="test-token-123")


def test_client_default_api_url(client):
    assert client.api_url == DEFAULT_API_URL
    assert "infomaniak" in client.api_url


def test_client_custom_api_url():
    c = JelasticClient(token="tok", api_url="https://custom.example.com/1.0")
    assert c.api_url == "https://custom.example.com/1.0"


def test_get_env_url(client):
    url = client.get_env_url("my-app-dev")
    assert url == "https://my-app-dev.jpc.infomaniak.com"


def test_get_client_no_token(monkeypatch):
    monkeypatch.delenv("JELASTIC_TOKEN", raising=False)
    from jelastic_client import get_client
    with pytest.raises(JelasticError, match="JELASTIC_TOKEN"):
        get_client()


def test_get_client_with_token(monkeypatch):
    monkeypatch.setenv("JELASTIC_TOKEN", "my-pat-token")
    from jelastic_client import get_client
    client = get_client()
    assert client.token == "my-pat-token"


def test_call_includes_session(client):
    """Verify that _call sends session parameter."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"result": 0}).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        client._call("environment/control/rest/getenvs")

        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        assert b"session=test-token-123" in request.data


def test_call_raises_on_api_error(client):
    """API returning result != 0 should raise."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "result": 702,
            "error": "environment not found"
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        with pytest.raises(JelasticError, match="environment not found"):
            client._call("environment/control/rest/getenvinfo", envName="nonexistent")


def test_jelastic_error_has_result_code():
    err = JelasticError("test error", 702)
    assert err.result_code == 702
    assert "test error" in str(err)


# --------------------------------------------------------------------------
# VCS project read/write — where a rollback's ref actually lives
# --------------------------------------------------------------------------

def _responding(client, body):
    """Patch urlopen to answer with `body` and return the captured requests."""
    captured = []

    def _fake(request, timeout=None):
        captured.append(request)
        response = MagicMock()
        response.read.return_value = json.dumps(body).encode()
        response.__enter__ = lambda s: s
        response.__exit__ = MagicMock(return_value=False)
        return response

    return patch("urllib.request.urlopen", side_effect=_fake), captured


def test_get_vcs_project_picks_the_matching_context_from_a_list(client):
    """`getprojects` answers with several contexts — never assume one object."""
    body = {"result": 0, "array": [
        {"context": "admin", "branch": "admin-main", "url": "https://x.invalid/a.git"},
        {"context": "ROOT", "branch": "main", "url": "https://x.invalid/root.git"},
    ]}
    patcher, _ = _responding(client, body)
    with patcher:
        project = client.get_vcs_project("dev-demo", "ROOT")

    assert project["branch"] == "main"
    assert project["url"] == "https://x.invalid/root.git"


def test_get_vcs_project_raises_when_no_context_matches(client):
    """An unreadable current config must fail loudly — callers merge into it."""
    body = {"result": 0, "array": [{"context": "admin", "branch": "x"}]}
    patcher, _ = _responding(client, body)
    with patcher, pytest.raises(JelasticError, match="no VCS project for context"):
        client.get_vcs_project("dev-demo", "ROOT")


def test_set_vcs_ref_sends_every_field_back_with_only_branch_replaced(client):
    """AC11 — a sparse write could clear the repo URL and credentials."""
    project = {"context": "ROOT", "branch": "main", "url": "https://x.invalid/a.git",
               "login": "bot", "autoUpdate": {"enabled": True, "interval": 5}}
    patcher, captured = _responding(client, {"result": 0})
    with patcher:
        client.set_vcs_ref("dev-demo", project, "v1.2.3")

    sent = captured[0].data.decode()
    assert "branch=v1.2.3" in sent
    assert "url=https" in sent
    assert "login=bot" in sent
    # Non-scalars are JSON-encoded, not dropped — dropping one IS the sparse write.
    assert "autoUpdate=" in sent
    assert "enabled" in sent


def test_set_vcs_ref_never_forwards_a_stale_session_or_envname(client):
    project = {"context": "ROOT", "branch": "main", "session": "stale", "envName": "other"}
    patcher, captured = _responding(client, {"result": 0})
    with patcher:
        client.set_vcs_ref("dev-demo", project, "v1")

    sent = captured[0].data.decode()
    assert "session=test-token-123" in sent
    assert "stale" not in sent
    assert "envName=dev-demo" in sent
    assert "other" not in sent
