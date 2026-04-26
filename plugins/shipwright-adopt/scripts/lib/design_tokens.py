"""Extract design tokens from a frontend project (Tier 5).

Sources, in order of precedence:
1. `tailwind.config.{ts,js,mjs,cjs}` — `theme.extend.{colors,spacing,fontSize}`
2. CSS variables in `:root { --var: value; }` blocks under `<root>/src/**/*.css`
   (typical of shadcn/ui-style projects).

Regex-based: adopt has no Node runtime to evaluate the config JS itself.
The common config shape (object literal under `theme.extend.*`) parses
reliably; configs that build their theme dynamically (functions, spreads
of imports) yield empty maps — documented limitation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


_TAILWIND_FILENAMES = (
    "tailwind.config.ts", "tailwind.config.js",
    "tailwind.config.mjs", "tailwind.config.cjs",
)


def _read_tailwind_config(frontend_root: Path) -> str | None:
    for name in _TAILWIND_FILENAMES:
        p = frontend_root / name
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
    return None


# Match `colors: { ... }` (or `Colors`/`spacing`/`fontSize`/etc.) inside a config.
# Grabs the body between the matching first-level braces. Naive on nested objects
# but good enough for the common flat color/spacing maps.
def _section_body(config: str, section_name: str) -> str | None:
    pattern = re.compile(
        rf"\b{re.escape(section_name)}\s*:\s*\{{([^{{}}]*(?:\{{[^{{}}]*\}}[^{{}}]*)*)\}}",
        re.DOTALL,
    )
    m = pattern.search(config)
    return m.group(1) if m else None


# Inside a section body: `keyOrQuotedKey: 'value'` or `keyOrQuotedKey: "value"`.
_KEY_VALUE_RE = re.compile(
    r"""['"]?([A-Za-z0-9_\-]+)['"]?\s*:\s*['"]([^'"]+)['"]""",
)


def _parse_kv_section(body: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in _KEY_VALUE_RE.finditer(body)}


def _extract_tailwind_tokens(config: str | None) -> dict[str, dict[str, str]]:
    if not config:
        return {"colors": {}, "spacing": {}, "typography": {}}
    colors_body = _section_body(config, "colors") or ""
    spacing_body = _section_body(config, "spacing") or ""
    fontsize_body = _section_body(config, "fontSize") or ""
    return {
        "colors": _parse_kv_section(colors_body),
        "spacing": _parse_kv_section(spacing_body),
        "typography": _parse_kv_section(fontsize_body),
    }


# `:root { --name: value; }` — captures the name (without leading --) and
# the value (everything up to the next `;` or block end).
_CSS_VAR_RE = re.compile(
    r":root\s*\{([^}]*)\}",
    re.DOTALL,
)
_VAR_LINE_RE = re.compile(
    r"--([A-Za-z0-9_\-]+)\s*:\s*([^;}]+)\s*[;}]",
)


def _extract_css_vars(frontend_root: Path) -> dict[str, str]:
    src = frontend_root / "src"
    out: dict[str, str] = {}
    if not src.is_dir():
        return out
    for css in src.rglob("*.css"):
        try:
            body = css.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for root_block in _CSS_VAR_RE.finditer(body):
            for name, value in _VAR_LINE_RE.findall(root_block.group(1)):
                out[name] = value.strip()
    return out


def extract_design_tokens(frontend_root: Path) -> dict[str, Any]:
    """Return `{colors, spacing, typography, css_vars}` dicts.

    Each value is `Mapping[token_name, token_value_string]`. Empty when no
    source produced data — adopt's downstream consumers handle empty
    sections without errors.
    """
    config = _read_tailwind_config(frontend_root)
    tw = _extract_tailwind_tokens(config)
    css_vars = _extract_css_vars(frontend_root)
    return {
        "colors": tw["colors"],
        "spacing": tw["spacing"],
        "typography": tw["typography"],
        "css_vars": css_vars,
    }
