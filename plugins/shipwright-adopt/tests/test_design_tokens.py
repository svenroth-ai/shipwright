"""Verify design_tokens extracts colors/spacing/typography from tailwind config + CSS.

Regex-based parsing — adopt has no Node runtime to evaluate the config
JS itself. Good enough for the common `theme.extend.{colors,spacing,fontSize}`
shape; documented limitations for callbacks and dynamic values.
"""

from __future__ import annotations

from pathlib import Path

from lib.design_tokens import extract_design_tokens


def test_extracts_tailwind_colors(tmp_path: Path) -> None:
    (tmp_path / "tailwind.config.ts").write_text(
        """import type { Config } from 'tailwindcss';
const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: '#0066cc',
        secondary: '#ff5500',
        muted: 'hsl(210, 40%, 96.1%)',
      },
    },
  },
};
export default config;
""",
        encoding="utf-8",
    )
    tokens = extract_design_tokens(tmp_path)
    assert tokens["colors"]["primary"] == "#0066cc"
    assert tokens["colors"]["secondary"] == "#ff5500"
    assert "muted" in tokens["colors"]


def test_extracts_tailwind_spacing(tmp_path: Path) -> None:
    (tmp_path / "tailwind.config.js").write_text(
        """module.exports = {
  theme: {
    extend: {
      spacing: {
        '18': '4.5rem',
        '128': '32rem',
      },
    },
  },
};
""",
        encoding="utf-8",
    )
    tokens = extract_design_tokens(tmp_path)
    assert tokens["spacing"]["18"] == "4.5rem"
    assert tokens["spacing"]["128"] == "32rem"


def test_extracts_tailwind_font_size(tmp_path: Path) -> None:
    (tmp_path / "tailwind.config.ts").write_text(
        """export default {
  theme: { extend: {
    fontSize: { 'display': '4rem', 'micro': '0.625rem' },
  }},
};
""",
        encoding="utf-8",
    )
    tokens = extract_design_tokens(tmp_path)
    assert tokens["typography"]["display"] == "4rem"
    assert tokens["typography"]["micro"] == "0.625rem"


def test_extracts_css_variables_from_globals_css(tmp_path: Path) -> None:
    """`:root { --foreground: ...; }` style CSS variables are common in
    shadcn/ui-based projects."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "globals.css").write_text(
        """:root {
  --background: 0 0% 100%;
  --foreground: 222.2 47.4% 11.2%;
  --primary: 222.2 47.4% 11.2%;
}
""",
        encoding="utf-8",
    )
    tokens = extract_design_tokens(tmp_path)
    assert tokens["css_vars"]["background"] == "0 0% 100%"
    assert tokens["css_vars"]["foreground"] == "222.2 47.4% 11.2%"


def test_no_config_returns_empty_tokens(tmp_path: Path) -> None:
    tokens = extract_design_tokens(tmp_path)
    assert tokens["colors"] == {}
    assert tokens["spacing"] == {}
    assert tokens["typography"] == {}
    assert tokens["css_vars"] == {}


def test_handles_malformed_tailwind_config_gracefully(tmp_path: Path) -> None:
    """Garbled config returns empty tokens, not a crash."""
    (tmp_path / "tailwind.config.ts").write_text("definitely { not [ a valid config", encoding="utf-8")
    tokens = extract_design_tokens(tmp_path)
    # No colors extracted — but no exception raised
    assert isinstance(tokens["colors"], dict)


def test_extracts_from_subdir_config(tmp_path: Path) -> None:
    """Multi-service repos: tailwind config lives in client/, not at root."""
    (tmp_path / "client").mkdir()
    (tmp_path / "client" / "tailwind.config.ts").write_text(
        "export default { theme: { extend: { colors: { brand: '#abc' } } } };\n",
        encoding="utf-8",
    )
    tokens = extract_design_tokens(tmp_path / "client")
    assert tokens["colors"]["brand"] == "#abc"
