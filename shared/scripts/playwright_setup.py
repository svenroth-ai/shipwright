#!/usr/bin/env python3
"""Idempotent Playwright setup in the target project.

Usage:
    uv run playwright_setup.py --cwd /path/to/project [--profile supabase-nextjs]

Actions (all idempotent):
1. Creates e2e/ directory if absent
2. Copies playwright.config.ts from template if absent
3. Copies browser-verify.ts from template if absent
4. Installs @playwright/test as devDependency if absent
5. Installs Chromium browser if not installed

Output (JSON):
    {"success": true, "config_path": "...", "browsers": ["chromium"], "actions": [...]}
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _find_shared_dir() -> Path:
    """Find the shared/ directory relative to this script."""
    return Path(__file__).resolve().parent.parent


def _has_package(cwd: Path, package: str) -> bool:
    """Check if a package is in package.json devDependencies."""
    pkg_json = cwd / "package.json"
    if not pkg_json.exists():
        return False
    try:
        data = json.loads(pkg_json.read_text(encoding="utf-8"))
        dev_deps = data.get("devDependencies", {})
        return package in dev_deps
    except (json.JSONDecodeError, OSError):
        return False


def setup(cwd: Path, profile: str | None = None) -> dict:
    """Run idempotent Playwright setup."""
    shared_dir = _find_shared_dir()
    templates_dir = shared_dir / "templates"
    actions: list[str] = []

    # 1. Create e2e/ directory
    e2e_dir = cwd / "e2e"
    if not e2e_dir.exists():
        e2e_dir.mkdir(parents=True)
        actions.append("Created e2e/ directory")

    # 2. Copy playwright.config.ts (with port substitution from build config)
    config_path = cwd / "playwright.config.ts"
    template_config = templates_dir / "playwright.config.ts.template"
    if not config_path.exists() and template_config.exists():
        content = template_config.read_text(encoding="utf-8")
        # Self-healing: substitute port from build config if available
        build_cfg = cwd / "shipwright_build_config.json"
        if build_cfg.exists():
            try:
                data = json.loads(build_cfg.read_text(encoding="utf-8"))
                dev_url = data.get("dev_url", "")
                if dev_url and dev_url != "http://localhost:3000":
                    content = content.replace("http://localhost:3000", dev_url)
            except (json.JSONDecodeError, OSError):
                pass
        config_path.write_text(content, encoding="utf-8")
        actions.append("Created playwright.config.ts from template")

    # 3. Copy browser-verify.ts
    verify_path = e2e_dir / "browser-verify.ts"
    template_verify = templates_dir / "browser-verify.ts.template"
    if not verify_path.exists() and template_verify.exists():
        shutil.copy2(template_verify, verify_path)
        actions.append("Created e2e/browser-verify.ts from template")

    # 4. Install @playwright/test if not in devDependencies
    if not _has_package(cwd, "@playwright/test"):
        try:
            subprocess.run(
                ["npm", "install", "-D", "@playwright/test"],
                cwd=str(cwd),
                capture_output=True,
                timeout=120,
            )
            actions.append("Installed @playwright/test")
        except (subprocess.TimeoutExpired, OSError) as e:
            return {"success": False, "error": f"Failed to install @playwright/test: {e}"}

    # 5. Install tsx for running browser-verify.ts
    if not _has_package(cwd, "tsx"):
        try:
            subprocess.run(
                ["npm", "install", "-D", "tsx"],
                cwd=str(cwd),
                capture_output=True,
                timeout=120,
            )
            actions.append("Installed tsx")
        except (subprocess.TimeoutExpired, OSError):
            pass  # Non-critical

    # 6. Install Chromium browser
    try:
        result = subprocess.run(
            ["npx", "playwright", "install", "chromium"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            actions.append("Installed Chromium browser")
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"success": False, "error": f"Failed to install Chromium: {e}"}

    if not actions:
        actions.append("Everything already set up")

    return {
        "success": True,
        "config_path": str(config_path),
        "e2e_dir": str(e2e_dir),
        "browsers": ["chromium"],
        "actions": actions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Idempotent Playwright setup")
    parser.add_argument("--cwd", required=True, help="Target project directory")
    parser.add_argument("--profile", help="Stack profile name")
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    if not cwd.is_dir():
        print(json.dumps({"error": f"Directory not found: {cwd}"}, indent=2))
        return 1

    result = setup(cwd, args.profile)
    print(json.dumps(result, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
