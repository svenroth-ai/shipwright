#!/usr/bin/env python3
"""BFS route crawler for /shipwright-adopt (Layer 1.5).

Copies the `shared/templates/crawler.ts.template` into the target
project's e2e/ directory and runs it via `npx playwright test`. Parses
the resulting `routes.json` and prints a structured summary.

Usage:
    uv run route_crawler.py --cwd <project> --base-url http://localhost:3000 \\
        [--max-depth 3] [--max-pages 50] \\
        [--output <path>] [--screenshots <dir>] [--auth-token <bearer>]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


_DEFAULT_CRAWL_TIMEOUT = 240  # seconds


def _find_template() -> Path | None:
    here = Path(__file__).resolve()
    for ancestor in [here, *here.parents]:
        candidate = ancestor.parent / "shared" / "templates" / "crawler.ts.template"
        if candidate.exists():
            return candidate
    return None


def _install_template(project_root: Path) -> Path:
    """Copy the crawler template into the project's e2e/ directory."""
    tpl = _find_template()
    if tpl is None:
        raise RuntimeError("crawler.ts.template not found in shared/templates/")
    dst_dir = project_root / "e2e"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "_shipwright-adopt-crawler.spec.ts"
    shutil.copyfile(tpl, dst)
    return dst


def _cleanup_template(spec_path: Path) -> None:
    try:
        spec_path.unlink(missing_ok=True)
    except OSError:
        pass


def run_crawl(
    project_root: Path,
    *,
    base_url: str,
    output: Path,
    screenshots_dir: Path,
    max_depth: int,
    max_pages: int,
    auth_token: str | None,
    timeout_sec: int = _DEFAULT_CRAWL_TIMEOUT,
) -> dict:
    """Run the crawler. Returns summary dict with status + route count."""
    output.parent.mkdir(parents=True, exist_ok=True)
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    spec_path = _install_template(project_root)
    env = os.environ.copy()
    env["SHIPWRIGHT_CRAWL_BASE_URL"] = base_url
    env["SHIPWRIGHT_CRAWL_OUT"] = str(output)
    env["SHIPWRIGHT_CRAWL_SCREENSHOTS"] = str(screenshots_dir)
    env["SHIPWRIGHT_CRAWL_MAX_DEPTH"] = str(max_depth)
    env["SHIPWRIGHT_CRAWL_MAX_PAGES"] = str(max_pages)
    if auth_token:
        env["SHIPWRIGHT_CRAWL_AUTH_TOKEN"] = auth_token

    try:
        result = subprocess.run(
            ["npx", "playwright", "test", str(spec_path.relative_to(project_root))],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
            shell=sys.platform == "win32",
        )
    except subprocess.TimeoutExpired:
        _cleanup_template(spec_path)
        return {"status": "timeout", "routes": 0, "output": str(output)}
    except FileNotFoundError:
        _cleanup_template(spec_path)
        return {"status": "npx_missing", "routes": 0, "output": str(output)}
    finally:
        _cleanup_template(spec_path)

    # Parse results
    if not output.exists():
        return {
            "status": "no_output",
            "routes": 0,
            "output": str(output),
            "stderr": result.stderr[-800:] if hasattr(result, "stderr") else "",
        }
    try:
        data = json.loads(output.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {
            "status": "invalid_json",
            "routes": 0,
            "output": str(output),
            "error": str(e),
        }

    return {
        "status": "success" if data else "empty",
        "routes": len(data) if isinstance(data, list) else 0,
        "output": str(output),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Playwright BFS route crawler for /shipwright-adopt")
    parser.add_argument("--cwd", required=True, type=Path)
    parser.add_argument("--base-url", required=True, type=str)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--screenshots", type=Path, default=None)
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--max-pages", type=int, default=50)
    parser.add_argument("--auth-token", type=str, default=None)
    args = parser.parse_args()

    cwd = args.cwd.resolve()
    if not cwd.is_dir():
        print(f"ERROR: not a directory: {cwd}", file=sys.stderr)
        return 1
    output = args.output or (cwd / ".shipwright" / "adopt" / "routes.json")
    screenshots = args.screenshots or (cwd / ".shipwright" / "adopt" / "screenshots")

    summary = run_crawl(
        cwd,
        base_url=args.base_url,
        output=output,
        screenshots_dir=screenshots,
        max_depth=args.max_depth,
        max_pages=args.max_pages,
        auth_token=args.auth_token,
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "success" else 2


if __name__ == "__main__":
    sys.exit(main())
