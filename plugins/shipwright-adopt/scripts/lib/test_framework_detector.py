"""Detect test frameworks (unit / integration / e2e / db) for /shipwright-adopt."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_UNIT_JS = [
    ("vitest", "vitest", "npx vitest run"),
    ("jest", "jest", "npx jest"),
    ("@jest/core", "jest", "npx jest"),
    ("mocha", "mocha", "npx mocha"),
    ("ava", "ava", "npx ava"),
    ("node:test", "node-test", "node --test"),
]
_E2E_JS = [
    ("@playwright/test", "playwright", "npx playwright test"),
    ("playwright", "playwright", "npx playwright test"),
    ("cypress", "cypress", "npx cypress run"),
]


def _read_pkg_deps(project_root: Path) -> dict[str, str]:
    pkg = project_root / "package.json"
    if not pkg.exists():
        return {}
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {**data.get("dependencies", {}), **data.get("devDependencies", {})}


def detect_test_frameworks(project_root: Path) -> dict[str, Any]:
    """Return detected test frameworks by layer. Pure, read-only."""
    out: dict[str, Any] = {
        "unit": None,
        "integration": None,
        "e2e": None,
        "db": None,
        "coverage_tool": None,
    }

    deps = _read_pkg_deps(project_root)

    # JS unit
    for dep, framework, cmd in _UNIT_JS:
        if dep in deps:
            out["unit"] = {"framework": framework, "command": cmd}
            break

    # JS e2e
    for dep, framework, cmd in _E2E_JS:
        if dep in deps:
            out["e2e"] = {"framework": framework, "command": cmd}
            break

    # Python pytest (pyproject.toml or pytest.ini or setup.cfg)
    pytest_ini = project_root / "pytest.ini"
    pypro = project_root / "pyproject.toml"
    pyproj_has_pytest = False
    if pypro.exists():
        content = pypro.read_text(encoding="utf-8", errors="replace")
        pyproj_has_pytest = "[tool.pytest" in content or '"pytest"' in content
    if pytest_ini.exists() or pyproj_has_pytest:
        if out["unit"] is None:
            out["unit"] = {"framework": "pytest", "command": "pytest"}
        else:
            out["integration"] = {"framework": "pytest", "command": "pytest"}

    # Go test (if go.mod)
    if (project_root / "go.mod").exists():
        if out["unit"] is None:
            out["unit"] = {"framework": "go-test", "command": "go test ./..."}

    # Rust test
    if (project_root / "Cargo.toml").exists():
        if out["unit"] is None:
            out["unit"] = {"framework": "cargo-test", "command": "cargo test"}

    # DB tests — pgTAP signal (supabase-style)
    if (project_root / "supabase" / "tests" / "database").is_dir():
        out["db"] = {"framework": "pgtap", "command": "supabase test db"}

    # Coverage
    if "c8" in deps:
        out["coverage_tool"] = "c8"
    elif "nyc" in deps:
        out["coverage_tool"] = "nyc"
    elif "@vitest/coverage-v8" in deps or "@vitest/coverage-c8" in deps:
        out["coverage_tool"] = "vitest-coverage"
    elif pypro.exists():
        content = pypro.read_text(encoding="utf-8", errors="replace")
        if "coverage" in content or "pytest-cov" in content:
            out["coverage_tool"] = "coverage.py"

    # Has e2e/ folder?
    if (project_root / "e2e").is_dir() and out["e2e"] is None:
        out["e2e"] = {"framework": "unknown-e2e-dir", "command": None}

    return out
