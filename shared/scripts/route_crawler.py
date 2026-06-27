#!/usr/bin/env python3
"""BFS route crawler for /shipwright-adopt (Layer 1.5).

Copies the `shared/templates/crawler.ts.template` into the target
project's e2e/ directory and runs it via `npx playwright test`. Parses
the resulting `routes.json` and prints a structured summary.

For multi-service repos where `playwright.config.ts` lives in a service
subdir (e.g. `client/playwright.config.ts`), pass `--config-dir` so the
spec is installed into that dir's `e2e/` and Playwright runs from there
— otherwise Playwright finds no config and falls back to defaults.

Usage:
    uv run route_crawler.py --cwd <project> --base-url http://localhost:3000 \\
        [--max-depth 3] [--max-pages 50] \\
        [--output <path>] [--screenshots <dir>] [--auth-token <bearer>] \\
        [--config-dir <dir-containing-playwright.config>]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.cmd_resolver import resolve_executable  # noqa: E402


_DEFAULT_CRAWL_TIMEOUT = 240  # seconds

# Static SPA-route extraction. Keep these globs narrow — broad scans
# (`**/*.tsx`) trip on Playwright bundles, vendor copies, build output.
_ROUTER_FILE_GLOBS = (
    "**/router.tsx",
    "**/router.ts",
    "**/routes.tsx",
    "**/routes.ts",
)

# Match `path: '...'` and `path: "..."` literals. Captures the literal
# only — no template strings (we'd need a JS parser to resolve those).
# Not anchored to a router builder call: TanStack-style nested route
# objects, react-router `RouteObject[]`s, and plain config arrays all
# share this shape, and the false-positive cost of grabbing an unrelated
# `path:` is just an extra harmless GET.
_ROUTE_LITERAL_RE = re.compile(r"""\bpath\s*:\s*['"]([^'"\n]+)['"]""")


def _read_playwright_error_context(run_cwd: Path, max_chars: int = 1500) -> str:
    """Surface the most recent Playwright error-context.md tail.

    Playwright writes test failures to `<run_cwd>/test-results/<spec>-<test>/error-context.md`
    and not to stderr (subprocess.stderr was empty in the original
    no_output diagnostic). On failure, glob test-results/ for the
    most-recently-modified error-context.md and return its tail.

    Returns "" if test-results/ doesn't exist or no error-context.md is
    present — the caller treats absent context as "no extra info" rather
    than as an error.
    """
    test_results = run_cwd / "test-results"
    if not test_results.is_dir():
        return ""
    candidates = list(test_results.glob("**/error-context.md"))
    if not candidates:
        return ""
    # Most recently modified wins (Playwright leaves multiple dirs across runs).
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    try:
        body = latest.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    return body[-max_chars:] if len(body) > max_chars else body


def _normalize_route(raw: str) -> str | None:
    """Normalize a route literal into a crawlable path.

    - Strips param markers (`:id`, `*`, `?`) so the seeded URL is at
      least visitable; the SPA may redirect or 404, that's fine.
    - Drops empty segments that result from stripping.
    - Drops the literal `*` catch-all (yields no useful route).

    Returns None for routes that don't normalize to anything useful.
    """
    raw = raw.strip()
    if not raw or raw == "*":
        return None
    # Make path-relative routes absolute.
    if not raw.startswith("/"):
        raw = "/" + raw
    parts: list[str] = []
    for seg in raw.split("/"):
        if not seg:
            continue
        if seg.startswith(":") or seg == "*":
            # `:id` or splat — skip; visiting "/users/:id" literally
            # almost never resolves. We could substitute "1" but that
            # invites false 200s; better to just not seed it.
            return None
        # `:id?` style optional params — also skip.
        if seg.endswith("?"):
            return None
        parts.append(seg)
    return "/" + "/".join(parts) if parts else "/"


def extract_static_routes(project_root: Path) -> list[str]:
    """Best-effort static extraction of SPA route literals.

    Scans common router-config files (`router.tsx`, `routes.tsx`, etc.)
    for `path: '...'` literals and returns a deduplicated, ordered list
    of normalized paths. Used to seed the BFS queue when the crawled
    entry page exposes no static <a href> links (lazy sidebars, post-
    hydration nav, etc.).

    Heuristic and intentionally simple — see `references/feature-inference.md`
    for context. Silently returns [] on any I/O / parse failure rather
    than raising; the crawl proceeds without seeds.

    Param routes (`:id`, `:slug?`) and splat `*` are skipped because
    visiting them literally is pointless.

    `index: true` children inherit the parent path. We don't try to walk
    nested-array structure; we just emit the parents normally and let
    the SPA's own router resolve the index.
    """
    seeds: list[str] = []
    seen: set[str] = set()
    for glob in _ROUTER_FILE_GLOBS:
        try:
            files = list(project_root.glob(glob))
        except OSError:
            continue
        for f in files:
            # Skip node_modules and build output to avoid grabbing routes
            # from bundled vendor code.
            parts = f.parts
            if any(p in {"node_modules", "dist", "build", ".next", "out"} for p in parts):
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for m in _ROUTE_LITERAL_RE.finditer(text):
                normalized = _normalize_route(m.group(1))
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    seeds.append(normalized)
    return seeds


def _summarize_screenshots(routes_data: list) -> tuple[int, int]:
    """Return (succeeded, failed) screenshot counts from routes.json data.

    Each route entry has a `screenshot_error` field iff the screenshot
    failed. Absence of the field = success. Routes that failed to
    navigate aren't in routes_data at all (the template `continue`s past
    them), so this counts only routes that made it into the results
    array.
    """
    if not isinstance(routes_data, list):
        return (0, 0)
    failed = sum(1 for r in routes_data if isinstance(r, dict) and r.get("screenshot_error"))
    succeeded = len(routes_data) - failed
    return (succeeded, failed)


def _find_template() -> Path | None:
    here = Path(__file__).resolve()
    for ancestor in [here, *here.parents]:
        candidate = ancestor.parent / "shared" / "templates" / "crawler.ts.template"
        if candidate.exists():
            return candidate
    return None


def _install_template(project_root: Path, config_dir: Path | None = None) -> Path:
    """Copy the crawler template into the appropriate e2e/ directory.

    If `config_dir` is provided (the dir containing `playwright.config.ts`),
    install into `<config_dir>/e2e/`. Otherwise install at project root —
    callers without an explicit hint stay back-compatible.
    """
    tpl = _find_template()
    if tpl is None:
        raise RuntimeError("crawler.ts.template not found in shared/templates/")
    target_root = config_dir if config_dir is not None else project_root
    dst_dir = target_root / "e2e"
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
    config_dir: Path | None = None,
    timeout_sec: int = _DEFAULT_CRAWL_TIMEOUT,
) -> dict:
    """Run the crawler. Returns summary dict with status + route count.

    `output` and `screenshots_dir` are kept under `project_root` regardless
    of `config_dir` — the artifact location should not move when a repo
    happens to have its config in a subdir.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    spec_path = _install_template(project_root, config_dir=config_dir)
    run_cwd = config_dir if config_dir is not None else project_root

    env = os.environ.copy()
    env["SHIPWRIGHT_CRAWL_BASE_URL"] = base_url
    env["SHIPWRIGHT_CRAWL_OUT"] = str(output)
    env["SHIPWRIGHT_CRAWL_SCREENSHOTS"] = str(screenshots_dir)
    env["SHIPWRIGHT_CRAWL_MAX_DEPTH"] = str(max_depth)
    env["SHIPWRIGHT_CRAWL_MAX_PAGES"] = str(max_pages)
    if auth_token:
        env["SHIPWRIGHT_CRAWL_AUTH_TOKEN"] = auth_token

    # Auto-seed routes from static router-config files unless the caller
    # has already populated SHIPWRIGHT_CRAWL_SEED_ROUTES (manual override
    # wins). Best-effort — empty list is fine.
    if not env.get("SHIPWRIGHT_CRAWL_SEED_ROUTES"):
        seeds = extract_static_routes(project_root)
        if seeds:
            env["SHIPWRIGHT_CRAWL_SEED_ROUTES"] = ",".join(seeds)

    npx = resolve_executable("npx")
    # `playwright test <path>` treats the path argument as a REGEX. On Windows
    # `relative_to` returns backslashes (`e2e\_shipwright-adopt-crawler.spec.ts`),
    # which Playwright then interprets as `e2e<escape>...` and fails with
    # "No tests found." Always use forward slashes — Playwright accepts them on
    # both platforms and they don't trip the regex parser.
    spec_arg = spec_path.relative_to(run_cwd).as_posix()
    try:
        result = subprocess.run(
            [npx, "playwright", "test", spec_arg],
            cwd=str(run_cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
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
            "error_context": _read_playwright_error_context(run_cwd),
        }
    try:
        data = json.loads(output.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {
            "status": "invalid_json",
            "routes": 0,
            "output": str(output),
            "error": str(e),
            "error_context": _read_playwright_error_context(run_cwd),
        }

    routes_count = len(data) if isinstance(data, list) else 0
    succeeded, failed = _summarize_screenshots(data if isinstance(data, list) else [])
    return {
        "status": "success" if data else "empty",
        "routes": routes_count,
        "screenshots_succeeded": succeeded,
        "screenshots_failed": failed,
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
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help=(
            "Directory containing playwright.config.ts. For multi-service "
            "repos where the config lives in a service subdir (e.g. client/), "
            "pass that path so the spec is installed there and npx runs from "
            "there. Defaults to --cwd."
        ),
    )
    args = parser.parse_args()

    cwd = args.cwd.resolve()
    if not cwd.is_dir():
        print(f"ERROR: not a directory: {cwd}", file=sys.stderr)
        return 1
    output = args.output or (cwd / ".shipwright" / "adopt" / "routes.json")
    screenshots = args.screenshots or (cwd / ".shipwright" / "adopt" / "screenshots")
    config_dir = args.config_dir.resolve() if args.config_dir is not None else None

    summary = run_crawl(
        cwd,
        base_url=args.base_url,
        output=output,
        screenshots_dir=screenshots,
        max_depth=args.max_depth,
        max_pages=args.max_pages,
        auth_token=args.auth_token,
        config_dir=config_dir,
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "success" else 2


if __name__ == "__main__":
    sys.exit(main())
