"""Verify Vite DX templates are present and structurally sound.

Replit-pattern adopt (Sub-Iterate A): generated Vite-based apps should
ship with a runtime-error overlay + dev-mode banner out of the box.
These templates are referenced by shipwright-build and shipwright-adopt
when the target stack uses Vite.
"""

from __future__ import annotations

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

VITE_CONFIG = TEMPLATES_DIR / "vite.config.ts.template"
ERROR_OVERLAY = TEMPLATES_DIR / "dev-error-overlay.tsx.template"
DEV_BANNER = TEMPLATES_DIR / "dev-banner.tsx.template"


def _read(p: Path) -> str:
    assert p.exists(), f"missing template: {p}"
    return p.read_text(encoding="utf-8")


def test_vite_config_template_exists():
    assert VITE_CONFIG.exists(), "vite.config.ts.template not found"


def test_vite_config_template_uses_define_config():
    body = _read(VITE_CONFIG)
    assert "defineConfig" in body, "vite.config.ts.template must use defineConfig"


def test_vite_config_template_gates_dev_plugins_on_mode():
    """Mode-gating is the whole point of the template — production builds
    must not ship dev-only inspectors. We accept either the function-form
    `defineConfig(({ mode }) => ...)` with a mode check, or an explicit
    NODE_ENV !== 'production' check."""
    body = _read(VITE_CONFIG)
    has_mode_check = "mode === 'development'" in body or "mode === \"development\"" in body
    has_nodeenv_check = "NODE_ENV" in body and "production" in body
    assert has_mode_check or has_nodeenv_check, (
        "vite.config.ts.template must gate dev-only plugins on a mode/NODE_ENV check"
    )


def test_vite_config_template_imports_react():
    body = _read(VITE_CONFIG)
    assert "@vitejs/plugin-react" in body, (
        "vite.config.ts.template should import @vitejs/plugin-react (vite-hono profile uses React)"
    )


def test_error_overlay_template_exists():
    assert ERROR_OVERLAY.exists(), "dev-error-overlay.tsx.template not found"


def test_error_overlay_listens_for_runtime_errors():
    body = _read(ERROR_OVERLAY)
    assert "addEventListener('error'" in body or 'addEventListener("error"' in body, (
        "dev-error-overlay must listen for window 'error' events"
    )


def test_error_overlay_listens_for_unhandled_rejections():
    body = _read(ERROR_OVERLAY)
    assert (
        "addEventListener('unhandledrejection'" in body
        or 'addEventListener("unhandledrejection"' in body
    ), "dev-error-overlay must listen for 'unhandledrejection' events"


def test_error_overlay_is_dev_only():
    body = _read(ERROR_OVERLAY)
    assert "import.meta.env.DEV" in body, (
        "dev-error-overlay must short-circuit when not in dev mode (import.meta.env.DEV)"
    )


def test_error_overlay_default_export_is_component():
    body = _read(ERROR_OVERLAY)
    assert "export default" in body, "dev-error-overlay must default-export the component"


def test_dev_banner_template_exists():
    assert DEV_BANNER.exists(), "dev-banner.tsx.template not found"


def test_dev_banner_is_dev_only():
    body = _read(DEV_BANNER)
    assert "import.meta.env.DEV" in body, (
        "dev-banner must render nothing in production (import.meta.env.DEV gate)"
    )


def test_dev_banner_default_export_is_component():
    body = _read(DEV_BANNER)
    assert "export default" in body, "dev-banner must default-export the component"


def test_no_replit_proprietary_imports_in_templates():
    """Templates must not pull in @replit/* packages — proprietary, not on
    public npm in some cases, and adopting them would defeat the
    drift-free-OSS rationale for this iterate."""
    for path in (VITE_CONFIG, ERROR_OVERLAY, DEV_BANNER):
        body = _read(path)
        assert "@replit/" not in body, (
            f"{path.name} must not depend on @replit/* — adopt OSS-equivalent only"
        )
