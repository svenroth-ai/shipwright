"""Tests for multi_service_detector — split frontend/backend layout detection."""

from __future__ import annotations

import json
from pathlib import Path



from lib.multi_service_detector import detect_multi_service_layout


def _make_pkg(deps: dict[str, str] | None = None,
              dev_deps: dict[str, str] | None = None,
              scripts: dict[str, str] | None = None,
              name: str = "x") -> str:
    return json.dumps({
        "name": name,
        "version": "0.1.0",
        "dependencies": deps or {},
        "devDependencies": dev_deps or {},
        "scripts": scripts or {},
    })


def _make_vite_config(proxy_target: str = "http://localhost:3001") -> str:
    return f"""
import {{ defineConfig }} from 'vite';
export default defineConfig({{
  server: {{
    port: 5173,
    proxy: {{
      '/api': {{
        target: '{proxy_target}',
        changeOrigin: true,
      }},
    }},
  }},
}});
"""


# ---------------------------------------------------------------------------
# Layout detection
# ---------------------------------------------------------------------------

def test_detect_client_server_with_framework_signal(tmp_path: Path):
    (tmp_path / "client").mkdir()
    (tmp_path / "server").mkdir()
    (tmp_path / "client" / "package.json").write_text(
        _make_pkg(deps={"vite": "^5.0", "react": "^18.0"}), encoding="utf-8"
    )
    (tmp_path / "server" / "package.json").write_text(
        _make_pkg(deps={"hono": "^4.0"}), encoding="utf-8"
    )
    result = detect_multi_service_layout(tmp_path)
    assert result["detected"] is True
    assert result["confidence"] == "medium"
    names = {s["name"] for s in result["services"]}
    assert names == {"frontend", "backend"}


def test_detect_client_server_with_vite_proxy_high_confidence(tmp_path: Path):
    (tmp_path / "client").mkdir()
    (tmp_path / "server").mkdir()
    (tmp_path / "client" / "package.json").write_text(
        _make_pkg(deps={"vite": "^5.0", "react": "^18.0"}), encoding="utf-8"
    )
    (tmp_path / "server" / "package.json").write_text(
        _make_pkg(deps={"hono": "^4.0"}), encoding="utf-8"
    )
    (tmp_path / "client" / "vite.config.ts").write_text(
        _make_vite_config("http://localhost:3001"), encoding="utf-8"
    )
    result = detect_multi_service_layout(tmp_path)
    assert result["detected"] is True
    assert result["confidence"] == "high"
    backend = next(s for s in result["services"] if s["name"] == "backend")
    assert backend.get("proxy_target") is not None
    assert "3001" in backend["proxy_target"]


def test_detect_frontend_backend_layout(tmp_path: Path):
    (tmp_path / "frontend").mkdir()
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text(
        _make_pkg(deps={"vite": "^5.0", "vue": "^3.0"}), encoding="utf-8"
    )
    (tmp_path / "backend" / "package.json").write_text(
        _make_pkg(deps={"express": "^4.0"}), encoding="utf-8"
    )
    result = detect_multi_service_layout(tmp_path)
    assert result["detected"] is True


def test_detect_web_api_layout(tmp_path: Path):
    (tmp_path / "web").mkdir()
    (tmp_path / "api").mkdir()
    (tmp_path / "web" / "package.json").write_text(
        _make_pkg(deps={"next": "^14.0", "react": "^18.0"}), encoding="utf-8"
    )
    (tmp_path / "api" / "package.json").write_text(
        _make_pkg(deps={"fastify": "^4.0"}), encoding="utf-8"
    )
    result = detect_multi_service_layout(tmp_path)
    assert result["detected"] is True


def test_detect_vite_config_in_frontend_root(tmp_path: Path):
    """vite.config in frontend/ root, not only client/."""
    (tmp_path / "frontend").mkdir()
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text(
        _make_pkg(deps={"vite": "^5.0", "react": "^18.0"}), encoding="utf-8"
    )
    (tmp_path / "backend" / "package.json").write_text(
        _make_pkg(deps={"hono": "^4.0"}), encoding="utf-8"
    )
    (tmp_path / "frontend" / "vite.config.ts").write_text(
        _make_vite_config(), encoding="utf-8"
    )
    result = detect_multi_service_layout(tmp_path)
    assert result["detected"] is True
    assert result["confidence"] == "high"


def test_detect_vite_config_in_project_root(tmp_path: Path):
    """vite.config at project root."""
    (tmp_path / "client").mkdir()
    (tmp_path / "server").mkdir()
    (tmp_path / "client" / "package.json").write_text(
        _make_pkg(deps={"vite": "^5.0", "react": "^18.0"}), encoding="utf-8"
    )
    (tmp_path / "server" / "package.json").write_text(
        _make_pkg(deps={"hono": "^4.0"}), encoding="utf-8"
    )
    (tmp_path / "vite.config.ts").write_text(_make_vite_config(), encoding="utf-8")
    result = detect_multi_service_layout(tmp_path)
    assert result["detected"] is True
    assert result["confidence"] == "high"


# ---------------------------------------------------------------------------
# Negative / no-detection cases
# ---------------------------------------------------------------------------

def test_no_detection_for_single_service(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        _make_pkg(deps={"next": "^14.0", "react": "^18.0"}), encoding="utf-8"
    )
    result = detect_multi_service_layout(tmp_path)
    assert result["detected"] is False


def test_no_detection_for_unrelated_subfolders(tmp_path: Path):
    """client/ exists but no package.json inside."""
    (tmp_path / "client").mkdir()
    (tmp_path / "client" / "README.md").write_text("hi", encoding="utf-8")
    result = detect_multi_service_layout(tmp_path)
    assert result["detected"] is False


def test_no_detection_without_framework_signal(tmp_path: Path):
    """Sibling package.jsons exist but neither has framework deps."""
    (tmp_path / "client").mkdir()
    (tmp_path / "server").mkdir()
    (tmp_path / "client" / "package.json").write_text(
        _make_pkg(deps={"lodash": "^4.0"}), encoding="utf-8"
    )
    (tmp_path / "server" / "package.json").write_text(
        _make_pkg(deps={"chalk": "^5.0"}), encoding="utf-8"
    )
    result = detect_multi_service_layout(tmp_path)
    assert result["detected"] is False
    assert result["confidence"] == "low"
    # Evidence still recorded for human review
    assert len(result["evidence"]) > 0


def test_no_detection_with_only_one_sided_framework(tmp_path: Path):
    """One-sided framework signal NEVER yields detected:true (Round-2 fix)."""
    (tmp_path / "client").mkdir()
    (tmp_path / "server").mkdir()
    (tmp_path / "client" / "package.json").write_text(
        _make_pkg(deps={"vite": "^5.0", "react": "^18.0"}), encoding="utf-8"
    )
    (tmp_path / "server" / "package.json").write_text(
        _make_pkg(deps={"lodash": "^4.0"}), encoding="utf-8"
    )
    result = detect_multi_service_layout(tmp_path)
    assert result["detected"] is False


# ---------------------------------------------------------------------------
# Evidence + result shape
# ---------------------------------------------------------------------------

def test_detector_evidence_listed(tmp_path: Path):
    (tmp_path / "client").mkdir()
    (tmp_path / "server").mkdir()
    (tmp_path / "client" / "package.json").write_text(
        _make_pkg(deps={"vite": "^5.0", "react": "^18.0"}), encoding="utf-8"
    )
    (tmp_path / "server" / "package.json").write_text(
        _make_pkg(deps={"hono": "^4.0"}), encoding="utf-8"
    )
    result = detect_multi_service_layout(tmp_path)
    assert isinstance(result["evidence"], list)
    assert len(result["evidence"]) >= 1
    # evidence is human-readable
    assert all(isinstance(e, str) for e in result["evidence"])


def test_backend_dev_script_counts_as_framework_signal(tmp_path: Path):
    """Backend qualifies even without a framework dep, if it has a `dev` script."""
    (tmp_path / "client").mkdir()
    (tmp_path / "server").mkdir()
    (tmp_path / "client" / "package.json").write_text(
        _make_pkg(deps={"vite": "^5.0", "react": "^18.0"}), encoding="utf-8"
    )
    (tmp_path / "server" / "package.json").write_text(
        _make_pkg(deps={"some-helper": "^1.0"}, scripts={"dev": "node index.js"}),
        encoding="utf-8",
    )
    result = detect_multi_service_layout(tmp_path)
    assert result["detected"] is True
