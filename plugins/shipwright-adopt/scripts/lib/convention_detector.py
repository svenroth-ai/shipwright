"""Detect code conventions from linter/formatter/tsconfig/editorconfig files."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _exists_any(project_root: Path, names: list[str]) -> str | None:
    for n in names:
        p = project_root / n
        if p.exists():
            return n
    return None


def detect_conventions(project_root: Path) -> dict[str, Any]:
    """Return convention markers. Pure, read-only."""
    out: dict[str, Any] = {
        "linter": None,
        "formatter": None,
        "tsconfig_strict": False,
        "editorconfig": None,
        "python_style": None,
        "typescript": False,
    }

    # ESLint (flat vs legacy)
    flat = _exists_any(project_root, [
        "eslint.config.js", "eslint.config.mjs", "eslint.config.ts", "eslint.config.cjs"
    ])
    legacy = _exists_any(project_root, [
        ".eslintrc", ".eslintrc.json", ".eslintrc.js", ".eslintrc.cjs",
        ".eslintrc.yml", ".eslintrc.yaml"
    ])
    if flat:
        out["linter"] = "eslint-flat"
    elif legacy:
        out["linter"] = "eslint-legacy"

    # Prettier
    prettier = _exists_any(project_root, [
        ".prettierrc", ".prettierrc.json", ".prettierrc.js", ".prettierrc.cjs",
        ".prettierrc.yml", ".prettierrc.yaml", "prettier.config.js", "prettier.config.cjs"
    ])
    if prettier:
        out["formatter"] = "prettier"

    # tsconfig strict
    tsconfig = project_root / "tsconfig.json"
    if tsconfig.exists():
        out["typescript"] = True
        try:
            data = json.loads(tsconfig.read_text(encoding="utf-8"))
            if data.get("compilerOptions", {}).get("strict") is True:
                out["tsconfig_strict"] = True
        except (json.JSONDecodeError, OSError):
            pass

    # .editorconfig
    ec = project_root / ".editorconfig"
    if ec.exists():
        content = ec.read_text(encoding="utf-8", errors="replace")
        ec_data: dict[str, str] = {}
        indent_style = re.search(r"indent_style\s*=\s*(\w+)", content)
        if indent_style:
            ec_data["indent_style"] = indent_style.group(1)
        indent_size = re.search(r"indent_size\s*=\s*(\d+)", content)
        if indent_size:
            ec_data["indent_size"] = indent_size.group(1)
        end_of_line = re.search(r"end_of_line\s*=\s*(\w+)", content)
        if end_of_line:
            ec_data["end_of_line"] = end_of_line.group(1)
        if ec_data:
            out["editorconfig"] = ec_data

    # Python style: ruff > black > none
    pypro = project_root / "pyproject.toml"
    if pypro.exists():
        content = pypro.read_text(encoding="utf-8", errors="replace")
        if "[tool.ruff" in content:
            out["python_style"] = "ruff"
            if out["linter"] is None:
                out["linter"] = "ruff"
        elif "[tool.black]" in content:
            out["python_style"] = "black"
            if out["formatter"] is None:
                out["formatter"] = "black"

    return out
