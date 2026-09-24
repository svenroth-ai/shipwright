"""Unit tests for ``lib.loop_claim``'s ``_retry_on_transient_permission_
error`` and its two callers, ``_load_state``/``_save_state`` (campaign-
dag-scheduler R4, round 13): a concurrent unlocked reader and a locked
writer's atomic tmp+replace can transiently deny EACH OTHER a
``PermissionError`` on Windows. Reproduced as a real CI failure (`Shared
tests (Windows)`, `test_n_concurrent_claimers_never_double_claim`) and
independently in local reruns, not tied to any specific diff. Split into
its own file rather than added to an already-full sibling — no baseline
implication, this file never existed before.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from lib.loop_claim import (
    _TRANSIENT_PERMISSION_RETRY_ATTEMPTS,
    _load_state,
    _retry_on_transient_permission_error,
    _save_state,
)


def _write_state_file(tmp_path: Path) -> Path:
    state_path = tmp_path / "loop_state.json"
    state_path.write_text(json.dumps({"loop_id": "x", "kind": "sub_iterate", "units": []}),
                           encoding="utf-8")
    return state_path


class TestRetryOnTransientPermissionError:
    def test_succeeds_immediately_when_fn_never_raises(self):
        assert _retry_on_transient_permission_error(lambda: 42) == 42

    def test_retries_through_transient_failures_then_succeeds(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:  # fewer failures than the retry budget
                raise PermissionError("simulated transient contention")
            return "done"

        with patch("time.sleep"):  # no real backoff delay in the test
            assert _retry_on_transient_permission_error(flaky) == "done"
        assert calls["n"] == 3

    def test_raises_once_the_retry_budget_is_exhausted(self):
        """A REAL, persistent permission problem (missing ACL, wrong user)
        must still surface as an error, not be silently swallowed into an
        infinite or masked retry."""
        calls = {"n": 0}

        def always_denied():
            calls["n"] += 1
            raise PermissionError("persistent, not transient")

        with patch("time.sleep"), pytest.raises(PermissionError, match="persistent"):
            _retry_on_transient_permission_error(always_denied)
        assert calls["n"] == _TRANSIENT_PERMISSION_RETRY_ATTEMPTS

    def test_a_non_permission_exception_is_never_retried(self):
        calls = {"n": 0}

        def raises_value_error():
            calls["n"] += 1
            raise ValueError("not a permission problem")

        with pytest.raises(ValueError, match="not a permission problem"):
            _retry_on_transient_permission_error(raises_value_error)
        assert calls["n"] == 1  # no retry attempted


class TestLoadStateUsesTheSharedRetry:
    def test_succeeds_on_the_happy_path(self, tmp_path):
        state_path = _write_state_file(tmp_path)
        assert _load_state(state_path) == {"loop_id": "x", "kind": "sub_iterate", "units": []}

    def test_retries_through_a_transient_permission_error_on_read(self, tmp_path, monkeypatch):
        state_path = _write_state_file(tmp_path)
        real_read_text = Path.read_text
        calls = {"n": 0}

        def flaky_read_text(self, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] < 2:
                raise PermissionError("simulated concurrent replace window")
            return real_read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", flaky_read_text)
        with patch("time.sleep"):
            result = _load_state(state_path)
        assert result == {"loop_id": "x", "kind": "sub_iterate", "units": []}


class TestSaveStateUsesTheSharedRetry:
    def test_writes_successfully_on_the_happy_path(self, tmp_path):
        state_path = tmp_path / "loop_state.json"
        _save_state(state_path, {"loop_id": "x", "kind": "sub_iterate", "units": []})
        assert json.loads(state_path.read_text(encoding="utf-8")) == {
            "loop_id": "x", "kind": "sub_iterate", "units": []}

    def test_retries_through_a_transient_permission_error_on_replace(self, tmp_path, monkeypatch):
        """The writer-side failure mode (round 13's local stress-test
        rerun, distinct from the reader-side one): a concurrent reader
        holding the destination open denies `tmp.replace` itself, not just
        another process's `read_text`."""
        state_path = tmp_path / "loop_state.json"
        real_replace = Path.replace
        calls = {"n": 0}

        def flaky_replace(self, target):
            calls["n"] += 1
            if calls["n"] < 2:
                raise PermissionError("simulated concurrent reader holding the file open")
            return real_replace(self, target)

        monkeypatch.setattr(Path, "replace", flaky_replace)
        with patch("time.sleep"):
            _save_state(state_path, {"loop_id": "x", "kind": "sub_iterate", "units": []})
        assert json.loads(state_path.read_text(encoding="utf-8")) == {
            "loop_id": "x", "kind": "sub_iterate", "units": []}
