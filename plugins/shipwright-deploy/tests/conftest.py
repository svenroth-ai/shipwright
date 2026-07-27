"""Shared test fixtures for shipwright-deploy."""

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

# Shared scripts
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

# A VCS project as the hosting target reports it: the branch is one field among
# several, and the others (url, credentials) must survive a ref pin untouched.
PROJECT = {
    "context": "ROOT",
    "type": "git",
    "url": "https://example.invalid/app.git",
    "branch": "main",
    "login": "shipwright-bot",
    "keyId": "7",
}


@pytest.fixture
def plugin_root():
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def vcs_project():
    """The VCS project the RecordingClient serves, as a fresh dict."""
    return dict(PROJECT)


class RecordingClient:
    """Records every outbound call so a test can assert what was actually sent.

    The critical rollback defect was invisible to a test that only inspected the
    returned payload, so the fixture exposes the call log as the primary surface.
    """

    def __init__(self, *, project=None, fail_on=None):
        import rollback

        self._error = rollback.HostingError
        self.calls = []
        self._project = dict(PROJECT if project is None else project)
        self._fail_on = set(fail_on or ())

    def _maybe_fail(self, key):
        if key in self._fail_on:
            raise self._error(f"{key} failed")

    def get_vcs_project(self, env_name, context="ROOT"):
        self.calls.append(("getprojects", {"envName": env_name, "context": context}))
        self._maybe_fail("getprojects")
        return dict(self._project)

    def set_vcs_ref(self, env_name, project, ref):
        self.calls.append(("editproject", {"envName": env_name, **project, "branch": ref}))
        self._maybe_fail("editproject")
        self._project = {**project, "branch": ref}
        return {"result": 0}

    def vcs_update(self, env_name, context="ROOT"):
        self.calls.append(("update", {"envName": env_name, "context": context}))
        self._maybe_fail("update")
        return {"result": 0}

    def stop_env(self, env_name):
        self.calls.append(("stopenv", {"envName": env_name}))
        self._maybe_fail("stopenv")
        return {"result": 0}

    @property
    def endpoints(self):
        return [name for name, _ in self.calls]

    def params_for(self, endpoint):
        return [params for name, params in self.calls if name == endpoint]


@pytest.fixture
def client(monkeypatch):
    """Install a RecordingClient behind rollback.py's client factory."""

    def _install(**kwargs):
        import rollback

        recording = RecordingClient(**kwargs)
        fake = types.ModuleType("jelastic_client")
        fake.get_client = lambda: recording
        fake.JelasticError = rollback.HostingError
        monkeypatch.setitem(sys.modules, "jelastic_client", fake)
        return recording

    return _install
