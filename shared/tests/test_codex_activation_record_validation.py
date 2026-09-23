"""Field-type validation and mkdir fail-open coverage for
``shared/scripts/lib/codex_activation_record.py`` (external code review
findings, R2 — AC1a). Split from ``test_codex_activation_record.py`` to
keep that file under the bloat-gate line limit; see that module's own
docstring for the mint/read/consume contract these tests build on.
"""

from __future__ import annotations

import json


def test_read_returns_none_when_expiry_field_has_wrong_type(tmp_path):
    # external review, openai medium: a wrong-typed field must not reach
    # `ts >= record.expiry` and raise TypeError -- fail-open like any other
    # corruption class.
    from lib.codex_activation_record import _record_path, read

    path = _record_path(tmp_path, "s1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 1, "session_id": "s1", "turn_id": "t1", "cwd": "/proj",
        "generation": "abc", "armed": True, "skill_id": "x", "args": {},
        "minted_at": 0.0, "expiry": None,
    }), encoding="utf-8")

    assert read(tmp_path, "s1", cwd="/proj") is None


def test_read_returns_none_when_armed_field_is_not_bool(tmp_path):
    from lib.codex_activation_record import _record_path, read

    path = _record_path(tmp_path, "s1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 1, "session_id": "s1", "turn_id": "t1", "cwd": "/proj",
        "generation": "abc", "armed": "yes", "skill_id": "x", "args": {},
        "minted_at": 0.0, "expiry": 9e9,
    }), encoding="utf-8")

    assert read(tmp_path, "s1", cwd="/proj") is None


def test_read_returns_none_when_minted_at_is_infinite(tmp_path):
    from lib.codex_activation_record import _record_path, read

    path = _record_path(tmp_path, "s1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 1, "session_id": "s1", "turn_id": "t1", "cwd": "/proj",
        "generation": "abc", "armed": True, "skill_id": "x", "args": {},
        "minted_at": float("inf"), "expiry": 9e9,
    }), encoding="utf-8")

    assert read(tmp_path, "s1", cwd="/proj") is None


def test_exclusive_create_mkdir_failure_is_fail_open(tmp_path, monkeypatch):
    # external review, glm low: mkdir previously sat outside the OSError
    # guard, so an unwritable parent raised past mint()'s never-an-
    # exception contract instead of falling open.
    import lib.codex_activation_record as car
    from pathlib import Path as _Path

    def _boom(self, parents=True, exist_ok=True):
        raise OSError("read-only filesystem")

    monkeypatch.setattr(_Path, "mkdir", _boom)

    assert car.mint(tmp_path, session_id="s1", turn_id="t1", cwd="/proj", armed=True) is None
