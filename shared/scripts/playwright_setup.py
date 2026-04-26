#!/usr/bin/env python3
"""Idempotent Playwright setup in the target project.

Usage:
    uv run playwright_setup.py --cwd /path/to/project [--profile supabase-nextjs]
    uv run playwright_setup.py --cwd /path --multi-service-json '{...}'

For multi-service repos (e.g. shipwright-webui's `client/` + `server/` with
no root `package.json`), pass `--multi-service-json` carrying the
detector's output. Setup pivots into the primary frontend service dir so
`npm install -D @playwright/test` finds a real `package.json` and the
generated `playwright.config.ts` lives next to it.

Actions (all idempotent):
1. Creates e2e/ directory if absent
2. Copies playwright.config.ts from template if absent
3. Copies browser-verify.ts from template if absent
4. Installs @playwright/test as devDependency if absent
5. Installs Chromium browser if not installed

Output (JSON):
    {"success": true, "config_path": "...", "browsers": ["chromium"], "actions": [...],
     "setup_dir": "..."}
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# Local helper. shared/tests/conftest.py adds shared/scripts/ to sys.path
# for tests; CLI invocation works because we add it ourselves below.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.cmd_resolver import resolve_executable  # noqa: E402


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


def _resolve_setup_dir(cwd: Path, multi_service: dict[str, Any] | None) -> Path:
    """Return the directory where Playwright should be installed.

    For multi-service repos, the frontend service is the right home for
    Playwright (its `package.json` exists; its dev URL is what we crawl).
    For single-service repos, return cwd unchanged.
    """
    if not multi_service or not multi_service.get("detected"):
        return cwd
    services = multi_service.get("services", []) or []
    primary = next((s for s in services if s.get("primary")), None)
    if primary is None:
        primary = next((s for s in services if (s.get("name") or "").lower() in ("frontend", "client", "web")), None)
    if primary is None and services:
        primary = services[0]
    root = primary.get("root") if primary else None
    if not root:
        return cwd
    return cwd / root


def setup(
    cwd: Path,
    profile: str | None = None,
    multi_service: dict[str, Any] | None = None,
) -> dict:
    """Run idempotent Playwright setup."""
    shared_dir = _find_shared_dir()
    templates_dir = shared_dir / "templates"
    actions: list[str] = []

    setup_dir = _resolve_setup_dir(cwd, multi_service)
    if setup_dir != cwd:
        actions.append(f"Multi-service detected — pivoting Playwright setup into {setup_dir.relative_to(cwd).as_posix()}/")

    # 1. Create e2e/ directory in setup_dir
    e2e_dir = setup_dir / "e2e"
    if not e2e_dir.exists():
        e2e_dir.mkdir(parents=True)
        actions.append("Created e2e/ directory")

    # 2. Copy playwright.config.ts (with port substitution from build config)
    config_path = setup_dir / "playwright.config.ts"
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
    npm = resolve_executable("npm")
    npx = resolve_executable("npx")
    if not _has_package(setup_dir, "@playwright/test"):
        try:
            r = subprocess.run(
                [npm, "install", "-D", "@playwright/test"],
                cwd=str(setup_dir),
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            return {"success": False, "error": f"Failed to spawn npm install: {e}", "setup_dir": str(setup_dir)}
        if r.returncode != 0:
            # Surface stderr tail so the operator can act — previously this was
            # silently swallowed and "Installed @playwright/test" was appended.
            tail = (r.stderr or r.stdout or "")[-600:]
            return {
                "success": False,
                "error": f"npm install -D @playwright/test failed (rc={r.returncode}): {tail}",
                "setup_dir": str(setup_dir),
            }
        actions.append("Installed @playwright/test")

    # 5. Install tsx for running browser-verify.ts (non-critical — log on failure
    # but don't fail the whole setup).
    if not _has_package(setup_dir, "tsx"):
        try:
            r = subprocess.run(
                [npm, "install", "-D", "tsx"],
                cwd=str(setup_dir),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if r.returncode == 0:
                actions.append("Installed tsx")
            else:
                actions.append(f"WARN: tsx install failed (rc={r.returncode}); continuing")
        except (subprocess.TimeoutExpired, OSError):
            actions.append("WARN: tsx install raised; continuing")

    # 6. Install Chromium browser
    try:
        r = subprocess.run(
            [npx, "playwright", "install", "chromium"],
            cwd=str(setup_dir),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"success": False, "error": f"Failed to spawn `npx playwright install`: {e}", "setup_dir": str(setup_dir)}
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "")[-600:]
        return {
            "success": False,
            "error": f"`npx playwright install chromium` failed (rc={r.returncode}): {tail}",
            "setup_dir": str(setup_dir),
        }
    actions.append("Installed Chromium browser")

    if not actions:
        actions.append("Everything already set up")

    return {
        "success": True,
        "config_path": str(config_path),
        "e2e_dir": str(e2e_dir),
        "setup_dir": str(setup_dir),
        "browsers": ["chromium"],
        "actions": actions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Idempotent Playwright setup")
    parser.add_argument("--cwd", required=True, help="Target project directory")
    parser.add_argument("--profile", help="Stack profile name")
    parser.add_argument(
        "--multi-service-json",
        help="Multi-service detector output as inline JSON (object with `detected` + `services`)",
    )
    args = parser.parse_args()

    cwd = Path(args.cwd).resolve()
    if not cwd.is_dir():
        print(json.dumps({"error": f"Directory not found: {cwd}"}, indent=2))
        return 1

    multi_service = None
    if args.multi_service_json:
        try:
            multi_service = json.loads(args.multi_service_json)
        except json.JSONDecodeError as e:
            print(json.dumps({"success": False, "error": f"invalid --multi-service-json: {e}"}, indent=2))
            return 2

    result = setup(cwd, args.profile, multi_service=multi_service)
    print(json.dumps(result, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
