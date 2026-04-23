"""Tests for OSS scanner backend."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure scripts/lib is on path
PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

from oss_backend import (
    OSSBackend,
    _DEFAULT_EXCLUDES,
    _resolve_excludes,
    _run_semgrep,
    _run_trivy,
    _run_gitleaks,
    _utf8_subprocess_env,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# OSSBackend
# ---------------------------------------------------------------------------

class TestOSSBackend:

    def test_name(self):
        backend = OSSBackend()
        assert backend.name == "oss"
        assert backend.requires_cloud is False

    @patch("shutil.which", side_effect=lambda t: "/usr/bin/" + t if t in ("semgrep", "trivy") else None)
    def test_capabilities_partial(self, mock_which):
        backend = OSSBackend()
        assert backend.capabilities == {"sast", "sca"}

    @patch("shutil.which", return_value=None)
    def test_not_configured_when_nothing_installed(self, mock_which):
        backend = OSSBackend()
        assert backend.is_configured() is False

    @patch("shutil.which", side_effect=lambda t: "/usr/bin/gitleaks" if t == "gitleaks" else None)
    def test_configured_with_single_tool(self, mock_which):
        backend = OSSBackend()
        assert backend.is_configured() is True
        assert backend.capabilities == {"secrets"}

    def test_setup_instructions_contains_tools(self):
        backend = OSSBackend()
        instructions = backend.get_setup_instructions()
        assert "semgrep" in instructions
        assert "trivy" in instructions
        assert "gitleaks" in instructions


# ---------------------------------------------------------------------------
# Tool runners (mocked subprocess)
# ---------------------------------------------------------------------------

class TestRunSemgrep:

    def test_parses_output(self):
        fixture = json.loads((FIXTURES_DIR / "sample_semgrep_output.json").read_text())
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(fixture)
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            findings = _run_semgrep("/tmp/test")

        assert len(findings) == 3
        assert findings[0]["source"] == "semgrep"
        assert findings[0]["type"] == "sast"


class TestRunTrivy:

    def test_parses_output(self):
        fixture = json.loads((FIXTURES_DIR / "sample_trivy_output.json").read_text())
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(fixture)
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            findings = _run_trivy("/tmp/test")

        assert len(findings) == 3
        assert findings[0]["source"] == "trivy"
        assert findings[0]["type"] == "sca"
        assert findings[0]["cve_id"] == "CVE-2024-1234"


class TestRunGitleaks:

    def test_parses_output(self):
        fixture = json.loads((FIXTURES_DIR / "sample_gitleaks_output.json").read_text())
        mock_result = MagicMock()
        mock_result.returncode = 1  # gitleaks returns 1 when findings exist
        mock_result.stdout = json.dumps(fixture)
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            findings = _run_gitleaks("/tmp/test")

        assert len(findings) == 2
        assert findings[0]["source"] == "gitleaks"
        assert findings[0]["type"] == "secret_detection"

    def test_returns_empty_on_timeout(self):
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="gitleaks", timeout=300)):
            findings = _run_gitleaks("/tmp/test")
        assert findings == []

    def test_returns_empty_on_missing_binary(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            findings = _run_gitleaks("/tmp/test")
        assert findings == []


# ---------------------------------------------------------------------------
# Full scan (mocked)
# ---------------------------------------------------------------------------

class TestOSSBackendScan:

    @patch("shutil.which", side_effect=lambda t: "/usr/bin/" + t)
    def test_full_scan_combines_all_tools(self, mock_which):
        semgrep_fixture = json.loads((FIXTURES_DIR / "sample_semgrep_output.json").read_text())
        trivy_fixture = json.loads((FIXTURES_DIR / "sample_trivy_output.json").read_text())
        gitleaks_fixture = json.loads((FIXTURES_DIR / "sample_gitleaks_output.json").read_text())

        def mock_run(cmd, **kwargs):
            result = MagicMock()
            result.stderr = ""
            if "semgrep" in cmd[0]:
                result.returncode = 0
                result.stdout = json.dumps(semgrep_fixture)
            elif "trivy" in cmd[0]:
                result.returncode = 0
                result.stdout = json.dumps(trivy_fixture)
            elif "gitleaks" in cmd[0]:
                result.returncode = 1
                result.stdout = json.dumps(gitleaks_fixture)
            return result

        with patch("subprocess.run", side_effect=mock_run):
            backend = OSSBackend()
            findings = backend.scan("/tmp/test")

        assert len(findings) == 8  # 3 semgrep + 3 trivy + 2 gitleaks
        # All findings should have _remediation_class
        for f in findings:
            assert "_remediation_class" in f

    @patch("shutil.which", side_effect=lambda t: "/usr/bin/semgrep" if t == "semgrep" else None)
    def test_scan_only_available_tools(self, mock_which):
        semgrep_fixture = json.loads((FIXTURES_DIR / "sample_semgrep_output.json").read_text())
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(semgrep_fixture)
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            backend = OSSBackend()
            findings = backend.scan("/tmp/test")

        assert len(findings) == 3
        assert all(f["source"] == "semgrep" for f in findings)

    @patch("shutil.which", side_effect=lambda t: "/usr/bin/" + t)
    def test_scan_with_type_filter(self, mock_which):
        trivy_fixture = json.loads((FIXTURES_DIR / "sample_trivy_output.json").read_text())
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(trivy_fixture)
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            backend = OSSBackend()
            findings = backend.scan("/tmp/test", scan_types=["sca"])

        assert len(findings) == 3
        assert all(f["source"] == "trivy" for f in findings)


# ---------------------------------------------------------------------------
# Default exclusions — verify scanner commands skip third-party / build dirs
# ---------------------------------------------------------------------------

class TestScannerExclusions:
    """Each scanner command must carry the default exclusion flags.

    Prevents Semgrep/Trivy/Gitleaks from scanning .venv, node_modules, etc.
    — they timed out and produced noise before this fix.
    """

    def test_default_excludes_covers_known_noise_dirs(self):
        for name in (
            ".venv",
            "node_modules",
            ".git",
            ".pytest_cache",
            "dist",
            "build",
            ".next",
            "__pycache__",
            ".cache",
        ):
            assert name in _DEFAULT_EXCLUDES

    @patch("subprocess.run")
    def test_semgrep_cmd_passes_each_default_as_exclude(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
        _run_semgrep("/tmp/test")
        cmd = mock_run.call_args[0][0]
        for name in _DEFAULT_EXCLUDES:
            assert name in cmd, f"semgrep cmd missing exclude for {name!r}: {cmd}"
        # --exclude flag must appear exactly once per default
        assert cmd.count("--exclude") == len(_DEFAULT_EXCLUDES)
        # Target still last arg
        assert cmd[-1] == "/tmp/test"

    @patch("subprocess.run")
    def test_trivy_cmd_passes_each_default_as_skip_dirs(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout='{"Results":[]}', stderr=""
        )
        _run_trivy("/tmp/test")
        cmd = mock_run.call_args[0][0]
        for name in _DEFAULT_EXCLUDES:
            assert name in cmd, f"trivy cmd missing skip-dirs for {name!r}: {cmd}"
        assert cmd.count("--skip-dirs") == len(_DEFAULT_EXCLUDES)
        assert cmd[-1] == "/tmp/test"

    def test_gitleaks_cmd_passes_generated_allowlist_config(self):
        """Config must exist AND contain each default at the moment gitleaks runs.

        Read the config inside the subprocess mock — the real _run_gitleaks
        unlinks the temp file in a finally block once the subprocess returns.
        """
        captured = {}

        def capture(cmd, **_kwargs):
            captured["cmd"] = cmd
            flag = "--config" if "--config" in cmd else "-c"
            assert flag in cmd, f"gitleaks cmd missing --config/-c: {cmd}"
            config_path = cmd[cmd.index(flag) + 1]
            captured["content"] = Path(config_path).read_text(encoding="utf-8")
            return MagicMock(returncode=0, stdout="[]", stderr="")

        with patch("subprocess.run", side_effect=capture):
            _run_gitleaks("/tmp/test")

        # Each default must appear as a path-segment regex in a TOML literal
        # single-quoted string so gitleaks' Go regex engine sees the intended
        # pattern unmodified (not double-escaped by TOML basic-string rules).
        for name in _DEFAULT_EXCLUDES:
            expected = f"'(^|/){re.escape(name)}(/|$)'"
            assert expected in captured["content"], (
                f"gitleaks config missing literal pattern {expected!r} for "
                f"{name!r}:\n{captured['content']}"
            )

    def test_gitleaks_cleans_up_temp_config(self):
        """Temp config file must be removed after gitleaks returns."""
        captured_path = {}

        def capture(cmd, **_kwargs):
            flag = "--config" if "--config" in cmd else "-c"
            captured_path["path"] = cmd[cmd.index(flag) + 1]
            return MagicMock(returncode=0, stdout="[]", stderr="")

        with patch("subprocess.run", side_effect=capture):
            _run_gitleaks("/tmp/test")

        assert not Path(captured_path["path"]).exists(), (
            "gitleaks temp config leaked"
        )


# ---------------------------------------------------------------------------
# _resolve_excludes — env-var extension + validation
# ---------------------------------------------------------------------------

class TestResolveExcludes:
    """SHIPWRIGHT_SCAN_EXCLUDES extends defaults; never replaces them."""

    def test_no_env_returns_only_defaults(self, monkeypatch):
        monkeypatch.delenv("SHIPWRIGHT_SCAN_EXCLUDES", raising=False)
        assert _resolve_excludes() == _DEFAULT_EXCLUDES

    def test_empty_env_returns_only_defaults(self, monkeypatch):
        monkeypatch.setenv("SHIPWRIGHT_SCAN_EXCLUDES", "")
        assert _resolve_excludes() == _DEFAULT_EXCLUDES

    def test_whitespace_only_env_returns_only_defaults(self, monkeypatch):
        monkeypatch.setenv("SHIPWRIGHT_SCAN_EXCLUDES", "   ,  ,")
        assert _resolve_excludes() == _DEFAULT_EXCLUDES

    def test_valid_names_extend_defaults(self, monkeypatch):
        monkeypatch.setenv("SHIPWRIGHT_SCAN_EXCLUDES", "vendor,generated")
        result = _resolve_excludes()
        # Defaults preserved
        for name in _DEFAULT_EXCLUDES:
            assert name in result
        # Additions appended
        assert "vendor" in result
        assert "generated" in result

    def test_valid_names_are_trimmed(self, monkeypatch):
        monkeypatch.setenv("SHIPWRIGHT_SCAN_EXCLUDES", "  vendor  ,generated  ")
        result = _resolve_excludes()
        assert "vendor" in result
        assert "generated" in result

    def test_duplicate_of_default_is_not_added_twice(self, monkeypatch):
        monkeypatch.setenv("SHIPWRIGHT_SCAN_EXCLUDES", "node_modules,vendor")
        result = _resolve_excludes()
        assert result.count("node_modules") == 1
        assert "vendor" in result

    def test_rejects_glob_wildcards(self, monkeypatch):
        monkeypatch.setenv("SHIPWRIGHT_SCAN_EXCLUDES", "vendor,**/*,*.py,a*b")
        result = _resolve_excludes()
        assert "vendor" in result
        assert "**/*" not in result
        assert "*.py" not in result
        assert "a*b" not in result

    def test_rejects_path_separators(self, monkeypatch):
        monkeypatch.setenv("SHIPWRIGHT_SCAN_EXCLUDES", "vendor,a/b,/etc,a\\b")
        result = _resolve_excludes()
        assert "vendor" in result
        assert "a/b" not in result
        assert "/etc" not in result
        assert "a\\b" not in result

    def test_rejects_parent_traversal(self, monkeypatch):
        monkeypatch.setenv("SHIPWRIGHT_SCAN_EXCLUDES", "vendor,..,../etc,.")
        result = _resolve_excludes()
        assert "vendor" in result
        assert ".." not in result
        assert "../etc" not in result
        assert "." not in result  # single dot is meaningless / dangerous too

    def test_env_var_cannot_shrink_defaults(self, monkeypatch):
        """Env var extends; it cannot remove defaults even if user tries tricks."""
        monkeypatch.setenv("SHIPWRIGHT_SCAN_EXCLUDES", "")
        result = _resolve_excludes()
        for name in _DEFAULT_EXCLUDES:
            assert name in result


# ---------------------------------------------------------------------------
# UTF-8 subprocess env — unblocks Semgrep SAST on Windows (cp1252 default)
# ---------------------------------------------------------------------------

class TestUtf8SubprocessEnv:
    """Scanners must run with PYTHONIOENCODING=utf-8 + PYTHONUTF8=1 so
    Semgrep does not crash on source files containing Unicode control chars
    (e.g. \\u202a LEFT-TO-RIGHT EMBEDDING)."""

    def test_env_forces_utf8_io(self, monkeypatch):
        monkeypatch.setenv("PYTHONIOENCODING", "cp1252")  # simulate Windows default
        env = _utf8_subprocess_env()
        assert env["PYTHONIOENCODING"] == "utf-8"
        assert env["PYTHONUTF8"] == "1"

    def test_env_preserves_existing_vars(self, monkeypatch):
        monkeypatch.setenv("MY_UNRELATED_VAR", "keep-me")
        env = _utf8_subprocess_env()
        assert env.get("MY_UNRELATED_VAR") == "keep-me"

    def test_env_preserves_path(self):
        env = _utf8_subprocess_env()
        # PATH must survive — otherwise the subprocess cannot find semgrep/trivy/gitleaks
        assert "PATH" in env or "Path" in env

    @patch("subprocess.run")
    def test_semgrep_subprocess_receives_utf8_env(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
        _run_semgrep("/tmp/test")
        env = mock_run.call_args.kwargs.get("env")
        assert env is not None, "subprocess.run must receive explicit env"
        assert env.get("PYTHONIOENCODING") == "utf-8"
        assert env.get("PYTHONUTF8") == "1"

    @patch("subprocess.run")
    def test_trivy_subprocess_receives_utf8_env(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout='{"Results":[]}', stderr=""
        )
        _run_trivy("/tmp/test")
        env = mock_run.call_args.kwargs.get("env")
        assert env is not None
        assert env.get("PYTHONIOENCODING") == "utf-8"

    @patch("subprocess.run")
    def test_gitleaks_subprocess_receives_utf8_env(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
        _run_gitleaks("/tmp/test")
        env = mock_run.call_args.kwargs.get("env")
        assert env is not None
        assert env.get("PYTHONIOENCODING") == "utf-8"

    @patch("subprocess.run")
    def test_subprocess_decodes_utf8_not_locale_default(self, mock_run):
        """Even if the tool emits UTF-8 containing non-cp1252 bytes, our
        subprocess.run must decode as UTF-8 so we don't crash parsing it."""
        mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
        _run_semgrep("/tmp/test")
        kwargs = mock_run.call_args.kwargs
        assert kwargs.get("encoding") == "utf-8"
        # errors='replace' is a belt-and-suspenders safety net for malformed
        # bytes — rare, but prevents UnicodeDecodeError from bubbling up.
        assert kwargs.get("errors") == "replace"
