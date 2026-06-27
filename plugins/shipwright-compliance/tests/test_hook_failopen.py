"""Unit tests for the PreToolUse fail-open guard (``lib.hook_failopen``).

A PreToolUse ``Bash`` hook fires on EVERY Bash tool call. If the hook process
crashes (unhandled exception), Claude Code treats the failure as a block and the
unrelated Bash call (git add, test run, file read) is hard-blocked. A crashing
*check* must never hard-block work, so these gates fail OPEN: any unexpected
exception is logged (best-effort) and the hook returns 0 (allow). The deliberate
soft-block (return 2) is a normal return value, not an exception, so it passes
through unchanged.

Loaded via importlib file-spec (not ``from lib.hook_failopen import ...``)
because two ``lib/`` packages co-exist in this repo and ``sys.modules['lib']``
may already be cached at the shared package by an earlier test.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_LIB = Path(__file__).parent.parent / "scripts" / "lib" / "hook_failopen.py"


def _load():
    spec = importlib.util.spec_from_file_location("_hook_failopen_under_test", _LIB)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hook_failopen = _load()
LOG_REL = Path(".shipwright") / "agent_docs" / "runtime" / "hook_errors.log"


class TestRunFailopen:
    def test_passes_through_zero(self):
        assert hook_failopen.run_failopen("h", lambda: 0) == 0

    def test_passes_through_block_exit_two(self):
        # The deliberate soft-block must survive untouched.
        assert hook_failopen.run_failopen("h", lambda: 2) == 2

    def test_non_int_return_coerced_to_allow(self):
        assert hook_failopen.run_failopen("h", lambda: None) == 0

    def test_raising_main_fails_open(self, tmp_path: Path):
        def boom() -> int:
            raise AttributeError("'str' object has no attribute 'get'")

        rc = hook_failopen.run_failopen("check_security_scan", boom, project_root=tmp_path)
        assert rc == 0  # fail OPEN, never block on a crash

    def test_raising_main_logs_warning(self, tmp_path: Path):
        def boom() -> int:
            raise ValueError("kaboom")

        hook_failopen.run_failopen("check_rtm_coverage", boom, project_root=tmp_path)
        log = tmp_path / LOG_REL
        assert log.exists()
        content = log.read_text(encoding="utf-8")
        assert "FAILOPEN" in content
        assert "check_rtm_coverage" in content
        assert "kaboom" in content


class TestLogHookError:
    def test_writes_to_gitignored_runtime_dir(self, tmp_path: Path):
        hook_failopen.log_hook_error("h", RuntimeError("x"), project_root=tmp_path)
        # Diagnostic log lives under the gitignored runtime/ subdir, NOT beside
        # the tracked compliance_overrides.log.
        assert (tmp_path / LOG_REL).exists()

    def test_logging_never_raises_on_bad_root(self):
        # A project_root that cannot be created must not propagate — logging is
        # best-effort and must never defeat fail-open.
        bad = "\x00:/definitely/not/creatable"
        # Should silently swallow; no exception escapes.
        hook_failopen.log_hook_error("h", RuntimeError("x"), project_root=bad)

    def test_appends_rather_than_truncates(self, tmp_path: Path):
        hook_failopen.log_hook_error("h", RuntimeError("first"), project_root=tmp_path)
        hook_failopen.log_hook_error("h", RuntimeError("second"), project_root=tmp_path)
        content = (tmp_path / LOG_REL).read_text(encoding="utf-8")
        assert "first" in content and "second" in content
        assert content.count("FAILOPEN") == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
