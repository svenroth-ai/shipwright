"""Tests for the gitleaks config renderer (``gitleaks_config``).

AC-3 / AC-4 of iterate-2026-07-27-security-coverage-manifest: the local secret
scan must EXTEND the project's own ``.gitleaks.toml`` rather than substitute a
generated one, so a repository has a single accepted-findings answer whichever
path asked.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

from gitleaks_config import render_config, write_config  # noqa: E402
from gitleaks_inspect import (  # noqa: E402
    PROJECT_CONFIG_NAME,
    resolve_project_config,
)
from oss_backend import _run_gitleaks  # noqa: E402


@pytest.mark.covers("FR-01.07")
class TestResolveProjectConfig:
    def test_finds_gitleaks_toml_at_target_root(self, tmp_path: Path) -> None:
        cfg = tmp_path / PROJECT_CONFIG_NAME
        cfg.write_text("title = 'x'\n", encoding="utf-8")
        assert resolve_project_config(str(tmp_path)) == str(cfg)

    def test_returns_none_when_absent(self, tmp_path: Path) -> None:
        assert resolve_project_config(str(tmp_path)) is None

    def test_directory_named_like_the_config_is_not_a_config(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / PROJECT_CONFIG_NAME).mkdir()
        assert resolve_project_config(str(tmp_path)) is None

    def test_relative_target_still_yields_an_absolute_path(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Gitleaks resolves `[extend] path` against its OWN working directory,
        so a relative path here would point somewhere else the moment the scan
        is launched from a different directory than the target."""
        (tmp_path / "proj").mkdir()
        (tmp_path / "proj" / PROJECT_CONFIG_NAME).write_text("t = 1\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        resolved = resolve_project_config("proj")
        assert resolved is not None
        assert Path(resolved).is_absolute()
        assert Path(resolved) == (tmp_path / "proj" / PROJECT_CONFIG_NAME).resolve()


@pytest.mark.covers("FR-01.07")
class TestRenderConfig:
    def test_no_project_config_keeps_usedefault(self) -> None:
        body = render_config(("node_modules",), project_config_path=None)
        assert "useDefault = true" in body
        assert "[extend]" in body
        assert "path =" not in body

    def test_no_project_config_keeps_the_placeholder_allowlist(self) -> None:
        """With no project answer to defer to, the plugin keeps its own
        cafebabe:deadbeef defence (unchanged behaviour)."""
        body = render_config(("node_modules",), project_config_path=None)
        assert "cafebabe:deadbeef" in body

    def test_project_config_is_extended_by_absolute_path(self, tmp_path: Path) -> None:
        cfg = tmp_path / PROJECT_CONFIG_NAME
        cfg.write_text("title = 'x'\n", encoding="utf-8")
        body = render_config(("node_modules",), project_config_path=str(cfg))
        assert "path =" in body
        assert str(cfg).replace("\\", "\\\\") in body or str(cfg) in body

    def test_usedefault_and_path_are_never_both_emitted(self, tmp_path: Path) -> None:
        """Gitleaks aborts when a config sets both extend.useDefault and
        extend.path — emitting both would break every local secret scan."""
        cfg = tmp_path / PROJECT_CONFIG_NAME
        cfg.write_text("title = 'x'\n", encoding="utf-8")
        body = render_config(("node_modules",), project_config_path=str(cfg))
        assert "useDefault" not in body

    def test_project_config_drops_the_plugin_placeholder_allowlist(
        self, tmp_path: Path
    ) -> None:
        """One accepted-findings answer per repository: when the project has
        its own file, the plugin must not be quietly MORE permissive than the
        host path — that is the same divergence this AC removes."""
        cfg = tmp_path / PROJECT_CONFIG_NAME
        cfg.write_text("title = 'x'\n", encoding="utf-8")
        body = render_config(("node_modules",), project_config_path=str(cfg))
        assert "cafebabe" not in body

    def test_path_exclusions_survive_in_both_modes(self, tmp_path: Path) -> None:
        cfg = tmp_path / PROJECT_CONFIG_NAME
        cfg.write_text("title = 'x'\n", encoding="utf-8")
        for project in (None, str(cfg)):
            body = render_config(("node_modules", ".venv"), project_config_path=project)
            assert "node_modules" in body
            assert r"\.venv" in body or ".venv" in body

    def test_backslashes_in_a_windows_path_are_escaped_for_toml(self) -> None:
        r"""A Windows path lands in a TOML basic string; an unescaped ``\`` there
        is an escape sequence and would corrupt the path (or fail to parse)."""
        body = render_config((), project_config_path=r"C:\repo\.gitleaks.toml")
        assert r"C:\\repo\\.gitleaks.toml" in body

    def test_rendered_config_is_valid_toml(self, tmp_path: Path) -> None:
        import tomllib
        cfg = tmp_path / PROJECT_CONFIG_NAME
        cfg.write_text("title = 'x'\n", encoding="utf-8")
        for project in (None, str(cfg)):
            parsed = tomllib.loads(render_config(("node_modules",), project))
            assert "extend" in parsed
        # and the extend target round-trips to the exact path we passed
        parsed = tomllib.loads(render_config((), str(cfg)))
        assert parsed["extend"]["path"] == str(cfg)


@pytest.mark.covers("FR-01.07")
class TestWriteConfig:
    def test_writes_a_readable_temp_file(self, tmp_path: Path) -> None:
        path = write_config(("node_modules",), project_config_path=None)
        try:
            assert Path(path).read_text(encoding="utf-8").startswith("#")
        finally:
            Path(path).unlink(missing_ok=True)


@pytest.mark.covers("FR-01.07")
class TestRunGitleaksWiring:
    @patch("subprocess.run")
    def test_project_config_at_target_root_is_extended(
        self, mock_run, monkeypatch, tmp_path: Path
    ) -> None:
        """End-to-end wiring: a repo with .gitleaks.toml gets a generated
        config that EXTENDS it, not one that replaces it."""
        monkeypatch.delenv("SHIPWRIGHT_SCAN_EXCLUDES", raising=False)
        project_cfg = tmp_path / PROJECT_CONFIG_NAME
        project_cfg.write_text("title = 'project'\n", encoding="utf-8")

        captured: dict[str, str] = {}

        def _capture(cmd, *a, **kw):
            generated = cmd[cmd.index("--config") + 1]
            captured["body"] = Path(generated).read_text(encoding="utf-8")
            report_path = cmd[cmd.index("--report-path") + 1]
            Path(report_path).write_text("[]", encoding="utf-8")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = _capture
        _run_gitleaks(str(tmp_path))
        assert "path =" in captured["body"]
        assert "useDefault" not in captured["body"]

    @patch("subprocess.run")
    def test_no_project_config_keeps_previous_behaviour(
        self, mock_run, monkeypatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("SHIPWRIGHT_SCAN_EXCLUDES", raising=False)
        captured: dict[str, str] = {}

        def _capture(cmd, *a, **kw):
            generated = cmd[cmd.index("--config") + 1]
            captured["body"] = Path(generated).read_text(encoding="utf-8")
            Path(cmd[cmd.index("--report-path") + 1]).write_text("[]", encoding="utf-8")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = _capture
        _run_gitleaks(str(tmp_path))
        assert "useDefault = true" in captured["body"]
        assert "path =" not in captured["body"]
