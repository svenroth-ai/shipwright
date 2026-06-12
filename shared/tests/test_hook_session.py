"""Tests for ``shared/scripts/lib/hook_session.py`` (deep-audit F1).

The multi-session phase hooks resolve ``(project_root, session_id)`` from the
hook **stdin payload** (which always carries ``session_id`` + ``cwd``), NOT from
process env vars that no launcher sets. This module is the single tested unit
the three hooks share so the resolution can't drift between them.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib import hook_session  # noqa: E402


# ---------------------------------------------------------------------------
# read_hook_payload
# ---------------------------------------------------------------------------

class TestReadHookPayload:
    def test_valid_object(self):
        stream = io.StringIO(json.dumps({"session_id": "abc", "cwd": "/x"}))
        assert hook_session.read_hook_payload(stream) == {"session_id": "abc", "cwd": "/x"}

    def test_empty_stream(self):
        assert hook_session.read_hook_payload(io.StringIO("")) == {}

    def test_whitespace_only(self):
        assert hook_session.read_hook_payload(io.StringIO("   \n  ")) == {}

    def test_malformed_json(self):
        assert hook_session.read_hook_payload(io.StringIO("{not json")) == {}

    def test_non_object_json_returns_empty(self):
        # A JSON array / scalar is not a payload dict.
        assert hook_session.read_hook_payload(io.StringIO("[1,2,3]")) == {}
        assert hook_session.read_hook_payload(io.StringIO("42")) == {}

    def test_stream_read_error_returns_empty(self):
        class _Boom:
            def read(self):
                raise OSError("stdin closed")

        assert hook_session.read_hook_payload(_Boom()) == {}


# ---------------------------------------------------------------------------
# resolve_session_id
# ---------------------------------------------------------------------------

class TestResolveSessionId:
    def test_from_payload(self, monkeypatch):
        monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
        assert hook_session.resolve_session_id({"session_id": "sess-1"}) == "sess-1"

    def test_payload_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "env-sess")
        assert hook_session.resolve_session_id({"session_id": "payload-sess"}) == "payload-sess"

    def test_env_fallback_when_payload_absent(self, monkeypatch):
        monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "env-sess")
        assert hook_session.resolve_session_id({}) == "env-sess"

    def test_none_when_neither(self, monkeypatch):
        monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
        assert hook_session.resolve_session_id({}) is None

    def test_blank_payload_session_falls_back(self, monkeypatch):
        monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "env-sess")
        assert hook_session.resolve_session_id({"session_id": "   "}) == "env-sess"

    def test_non_string_payload_session_ignored(self, monkeypatch):
        monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
        assert hook_session.resolve_session_id({"session_id": 123}) is None


# ---------------------------------------------------------------------------
# resolve_project_root_from_payload
# ---------------------------------------------------------------------------

def _make_project(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
    return path


class TestResolveProjectRootFromPayload:
    def test_env_override_when_project(self, tmp_path, monkeypatch):
        proj = _make_project(tmp_path / "proj")
        monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(proj))
        # payload cwd points elsewhere; env override wins.
        got = hook_session.resolve_project_root_from_payload({"cwd": str(tmp_path / "nope")})
        assert got == proj.resolve()

    def test_env_ignored_when_not_a_project(self, tmp_path, monkeypatch):
        not_proj = tmp_path / "empty"
        not_proj.mkdir()
        proj = _make_project(tmp_path / "proj")
        monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(not_proj))
        got = hook_session.resolve_project_root_from_payload({"cwd": str(proj)})
        assert got == proj.resolve()

    def test_payload_cwd_when_project(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SHIPWRIGHT_PROJECT_ROOT", raising=False)
        proj = _make_project(tmp_path / "proj")
        got = hook_session.resolve_project_root_from_payload({"cwd": str(proj)})
        assert got == proj.resolve()

    def test_falls_back_to_resolver(self, tmp_path, monkeypatch):
        # No env, payload cwd not a project -> resolver fallback (cwd-based).
        monkeypatch.delenv("SHIPWRIGHT_PROJECT_ROOT", raising=False)
        proj = _make_project(tmp_path / "proj")
        monkeypatch.chdir(proj)
        got = hook_session.resolve_project_root_from_payload({"cwd": str(tmp_path / "nope")})
        assert got == proj.resolve()

    def test_ambiguous_resolver_returns_none(self, tmp_path, monkeypatch):
        # Two sibling projects under cwd with no env / cwd-project -> resolver
        # raises ValueError -> helper returns None (standalone).
        monkeypatch.delenv("SHIPWRIGHT_PROJECT_ROOT", raising=False)
        parent = tmp_path / "parent"
        _make_project(parent / "a")
        _make_project(parent / "b")
        monkeypatch.chdir(parent)
        got = hook_session.resolve_project_root_from_payload({"cwd": str(parent)})
        assert got is None
