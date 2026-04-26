"""Verify route_crawler honors --config-dir for multi-service projects.

Bug repro: spec installed at <project_root>/e2e/, but client/playwright.config.ts
defines testDir: './e2e' relative to client/. Playwright run from project root
finds no config and falls back to defaults.

Fix: when --config-dir is given (the dir holding playwright.config.ts), install
the spec into <config-dir>/e2e/ and run npx from <config-dir>.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import route_crawler  # noqa: E402


def test_install_template_default_uses_project_root(tmp_path):
    """Without config_dir, spec lands at <project_root>/e2e/."""
    spec = route_crawler._install_template(tmp_path, config_dir=None)
    assert spec.parent == tmp_path / "e2e"
    assert spec.name == "_shipwright-adopt-crawler.spec.ts"
    assert spec.exists()


def test_install_template_uses_config_dir(tmp_path):
    """With config_dir, spec lands at <config_dir>/e2e/."""
    client = tmp_path / "client"
    client.mkdir()
    spec = route_crawler._install_template(tmp_path, config_dir=client)
    assert spec.parent == client / "e2e"
    assert spec.name == "_shipwright-adopt-crawler.spec.ts"
    assert spec.exists()


def test_run_crawl_uses_config_dir_as_cwd(tmp_path, monkeypatch):
    """When config_dir is set, npx playwright runs from there, not project root."""
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["cwd"] = kwargs.get("cwd")

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""

        return _R()

    monkeypatch.setattr(route_crawler.subprocess, "run", fake_run)
    # Pre-create the routes.json so parsing succeeds
    out = tmp_path / ".shipwright" / "adopt" / "routes.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("[]", encoding="utf-8")
    screenshots = tmp_path / ".shipwright" / "adopt" / "screenshots"

    client = tmp_path / "client"
    client.mkdir()

    route_crawler.run_crawl(
        tmp_path,
        base_url="http://localhost:5173",
        output=out,
        screenshots_dir=screenshots,
        max_depth=2,
        max_pages=10,
        auth_token=None,
        config_dir=client,
    )

    assert str(captured["cwd"]) == str(client)
    # Spec relative path should be inside e2e/
    assert any("e2e" in str(part) for part in captured["cmd"])


def test_run_crawl_default_runs_from_project_root(tmp_path, monkeypatch):
    """Without config_dir, npx runs from project root (back-compat)."""
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cwd"] = kwargs.get("cwd")

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""

        return _R()

    monkeypatch.setattr(route_crawler.subprocess, "run", fake_run)
    out = tmp_path / ".shipwright" / "adopt" / "routes.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("[]", encoding="utf-8")
    screenshots = tmp_path / ".shipwright" / "adopt" / "screenshots"

    route_crawler.run_crawl(
        tmp_path,
        base_url="http://localhost:5173",
        output=out,
        screenshots_dir=screenshots,
        max_depth=2,
        max_pages=10,
        auth_token=None,
    )

    assert str(captured["cwd"]) == str(tmp_path)
