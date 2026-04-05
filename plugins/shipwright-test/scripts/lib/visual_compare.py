#!/usr/bin/env python3
"""Visual comparison: screenshot mockup HTMLs vs live app, generate side-by-side report.

Usage:
    uv run visual_compare.py --cwd <project_root> [--base-url http://localhost:3000]
    uv run visual_compare.py --cwd <project_root> --screen 01-login.html --screen 02-register.html

Reads designs/screen-routes.json for mockup-to-route mapping.
Supports authenticated routes via "auth" field (member/student/admin).
Use --screen (repeatable) to filter to specific screens (e.g. per build section).
Outputs designs/visual-comparison/index.html with side-by-side pairs.
Returns JSON with comparison results.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

# Test user credentials (same as E2E auth.setup.ts)
_TEST_USERS = {
    "member": {"email": "e2e-member@test.local", "password": "TestPass123!"},
    "student": {"email": "e2e-student@test.local", "password": "TestPass123!"},
    "admin": {"email": "e2e-admin@test.local", "password": "TestPass123!"},
}

CHUNK_SIZE = 3180


def _get_auth_cookie_js(supabase_url: str, service_role_key: str, email: str, password: str, base_url: str) -> str:
    """Generate JS code to authenticate and set Supabase cookies on the browser context."""
    project_ref = urlparse(supabase_url).hostname.split(".")[0]
    cookie_name = f"sb-{project_ref}-auth-token"

    return f"""
    // Authenticate via Supabase Admin API
    const authResp = await fetch('{supabase_url}/auth/v1/token?grant_type=password', {{
        method: 'POST',
        headers: {{
            'apikey': '{service_role_key}',
            'Content-Type': 'application/json',
        }},
        body: JSON.stringify({{ email: '{email}', password: '{password}' }}),
    }});
    if (!authResp.ok) throw new Error('Auth failed: ' + await authResp.text());
    const session = await authResp.json();

    const cookieValue = JSON.stringify({{
        access_token: session.access_token,
        refresh_token: session.refresh_token,
        expires_at: session.expires_at,
        expires_in: session.expires_in,
        token_type: session.token_type,
    }});

    const cookieName = '{cookie_name}';
    const baseHostname = new URL('{base_url}').hostname;

    if (cookieValue.length <= {CHUNK_SIZE}) {{
        await context.addCookies([{{
            name: cookieName,
            value: cookieValue,
            domain: baseHostname,
            path: '/',
            httpOnly: false,
            secure: false,
            sameSite: 'Lax',
        }}]);
    }} else {{
        const chunks = Math.ceil(cookieValue.length / {CHUNK_SIZE});
        const cookies = [];
        for (let i = 0; i < chunks; i++) {{
            cookies.push({{
                name: cookieName + '.' + i,
                value: cookieValue.slice(i * {CHUNK_SIZE}, (i + 1) * {CHUNK_SIZE}),
                domain: baseHostname,
                path: '/',
                httpOnly: false,
                secure: false,
                sameSite: 'Lax',
            }});
        }}
        await context.addCookies(cookies);
    }}
"""


def _screenshot_page(
    url: str,
    output_path: Path,
    *,
    width: int = 1440,
    height: int = 900,
    cwd: Path | None = None,
    auth_role: str | None = None,
    base_url: str = "http://localhost:3000",
) -> bool:
    """Take a full-page screenshot via Node.js Playwright."""
    supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")
    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    auth_js = ""
    if auth_role and supabase_url and service_role_key:
        user = _TEST_USERS.get(auth_role, _TEST_USERS["member"])
        auth_js = _get_auth_cookie_js(supabase_url, service_role_key, user["email"], user["password"], base_url)

    # Build JS: use context (not default browser page) for cookie support
    js_code = f"""
const {{ chromium }} = require('playwright');
(async () => {{
    const browser = await chromium.launch();
    const context = await browser.newContext({{ viewport: {{ width: {width}, height: {height} }} }});
    {auth_js}
    const page = await context.newPage();
    await page.goto('{url}', {{ waitUntil: 'networkidle', timeout: 15000 }});
    await page.screenshot({{ path: '{output_path.as_posix()}', fullPage: true }});
    await browser.close();
}})().catch(e => {{ console.error(e.message); process.exit(1); }});
"""
    try:
        result = subprocess.run(
            ["node", "-e", js_code],
            capture_output=True,
            timeout=30,
            text=True,
            cwd=str(cwd) if cwd else None,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _parse_route_config(value) -> tuple[str, str | None]:
    """Parse route config value. Supports both old (string) and new (object) format.

    Returns (route, auth_role).
    """
    if isinstance(value, str):
        return value, None
    if isinstance(value, dict):
        return value.get("route", ""), value.get("auth")
    return "", None


def _generate_comparison_html(comparisons: list[dict], output_dir: Path) -> Path:
    """Generate an HTML page showing mockup vs live screenshots side by side."""
    rows = []
    for comp in comparisons:
        mockup_img = comp.get("mockup_screenshot", "")
        live_img = comp.get("live_screenshot", "")
        route = comp.get("route", "")
        mockup_name = comp.get("mockup", "")
        auth = comp.get("auth", "")
        status = "MATCH" if comp.get("match") else "DIFFERS"
        status_color = "#059669" if comp.get("match") else "#DC2626"
        auth_badge = f' <span style="background:#ede8e1;padding:2px 8px;border-radius:4px;font-size:12px;">{auth}</span>' if auth else ""

        mockup_rel = Path(mockup_img).name if mockup_img else ""
        live_rel = Path(live_img).name if live_img else ""

        rows.append(f"""
        <div class="comparison">
            <h2>{mockup_name} &rarr; <code>{route}</code>{auth_badge}
                <span style="color:{status_color}; font-size:14px; margin-left:12px;">{status}</span>
            </h2>
            <div class="pair">
                <div class="side">
                    <h3>Mockup (Design)</h3>
                    <img src="{mockup_rel}" alt="Mockup: {mockup_name}" />
                </div>
                <div class="side">
                    <h3>Live App</h3>
                    <img src="{live_rel}" alt="Live: {route}" />
                </div>
            </div>
        </div>
        """)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Visual Comparison — Mockup vs Live</title>
<style>
    body {{ font-family: Inter, system-ui, sans-serif; margin: 0; padding: 24px; background: #f5f0eb; color: #1a1a1a; }}
    h1 {{ font-size: 24px; margin-bottom: 8px; }}
    .meta {{ color: #6b7280; font-size: 14px; margin-bottom: 32px; }}
    .comparison {{ background: #fff; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); }}
    .comparison h2 {{ font-size: 18px; margin: 0 0 16px 0; }}
    .pair {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    .side h3 {{ font-size: 14px; color: #6b7280; margin: 0 0 8px 0; text-transform: uppercase; letter-spacing: 0.5px; }}
    .side img {{ width: 100%; border: 1px solid #e0dbd4; border-radius: 8px; }}
    code {{ background: #ede8e1; padding: 2px 6px; border-radius: 4px; font-size: 14px; }}
</style>
</head>
<body>
<h1>Visual Comparison</h1>
<p class="meta">{len(comparisons)} screens compared | Generated by shipwright-test --visual</p>
{"".join(rows)}
</body>
</html>"""

    output_path = output_dir / "index.html"
    output_path.write_text(html, encoding="utf-8")
    return output_path


def run_visual_comparison(
    project_root: Path,
    base_url: str = "http://localhost:3000",
    screens: list[str] | None = None,
) -> dict:
    """Run visual comparison and return results.

    Args:
        project_root: Path to the project root directory.
        base_url: Base URL of the live application.
        screens: Optional list of screen filenames to compare (e.g. ["01-login.html"]).
                 When provided, only these screens are compared. When None, all screens
                 from screen-routes.json are compared.
    """
    routes_path = project_root / "designs" / "screen-routes.json"
    if not routes_path.exists():
        return {
            "passed": 0, "total": 0, "skipped": True,
            "skip_reason": "No designs/screen-routes.json found",
            "comparisons": [], "report_path": "",
        }

    try:
        routes = json.loads(routes_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {
            "passed": 0, "total": 0, "skipped": True,
            "skip_reason": f"Failed to read screen-routes.json: {e}",
            "comparisons": [], "report_path": "",
        }

    if not routes:
        return {
            "passed": 0, "total": 0, "skipped": True,
            "skip_reason": "screen-routes.json is empty",
            "comparisons": [], "report_path": "",
        }

    # Filter to requested screens if specified
    if screens is not None:
        available = set(routes.keys())
        requested = set(screens)
        missing = requested - available
        if missing:
            return {
                "passed": 0, "total": 0, "skipped": False,
                "skip_reason": "",
                "comparisons": [],
                "report_path": "",
                "error": (
                    f"Requested screens not found in screen-routes.json: "
                    f"{sorted(missing)}. Available: {sorted(available)}"
                ),
            }
        routes = {k: v for k, v in routes.items() if k in requested}

    # Load env for auth (from .env.local via @next/env or OS env)
    _load_env_local(project_root)

    output_dir = project_root / "designs" / "visual-comparison"
    output_dir.mkdir(parents=True, exist_ok=True)

    comparisons = []
    passed = 0
    total = 0

    for mockup_file, config_value in routes.items():
        total += 1
        route, auth_role = _parse_route_config(config_value)
        mockup_path = project_root / "designs" / "screens" / mockup_file

        if not mockup_path.exists():
            comparisons.append({
                "mockup": mockup_file, "route": route, "auth": auth_role,
                "match": False, "error": f"Mockup file not found: {mockup_file}",
            })
            continue

        # Screenshot mockup HTML (no auth needed — local file)
        mockup_screenshot = output_dir / f"mockup-{mockup_file.replace('.html', '.png')}"
        mockup_url = mockup_path.as_uri()
        mockup_ok = _screenshot_page(mockup_url, mockup_screenshot, cwd=project_root)

        # Screenshot live app (with auth if needed)
        live_screenshot = output_dir / f"live-{mockup_file.replace('.html', '.png')}"
        live_url = f"{base_url}{route}"
        live_ok = _screenshot_page(
            live_url, live_screenshot, cwd=project_root,
            auth_role=auth_role, base_url=base_url,
        )

        match = mockup_ok and live_ok
        if match:
            passed += 1

        comparisons.append({
            "mockup": mockup_file, "route": route, "auth": auth_role,
            "match": match,
            "mockup_screenshot": str(mockup_screenshot) if mockup_ok else "",
            "live_screenshot": str(live_screenshot) if live_ok else "",
        })

    report_path = _generate_comparison_html(comparisons, output_dir)

    return {
        "passed": passed, "total": total, "skipped": False, "skip_reason": "",
        "comparisons": comparisons, "report_path": str(report_path),
    }


def _load_env_local(project_root: Path) -> None:
    """Load .env.local into os.environ if not already set."""
    env_file = project_root / ".env.local"
    if not env_file.exists():
        return
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key not in os.environ:
                os.environ[key] = value
    except OSError:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Visual comparison: mockup vs live")
    parser.add_argument("--cwd", required=True, help="Project root directory")
    parser.add_argument("--base-url", default="http://localhost:3000", help="Live app base URL")
    parser.add_argument(
        "--screen", action="append", dest="screens", metavar="FILENAME",
        help="Screen filename to compare (repeatable, e.g. --screen 01-login.html --screen 02-register.html). "
             "When omitted, all screens from screen-routes.json are compared.",
    )
    args = parser.parse_args()

    # Validate --screen args are non-empty strings
    screens = args.screens
    if screens is not None:
        screens = [s.strip() for s in screens if s.strip()]
        if not screens:
            print(json.dumps({"error": "--screen flag provided but no valid screen names given"}))
            return 1

    result = run_visual_comparison(Path(args.cwd).resolve(), args.base_url, screens=screens)

    # Non-zero exit if --screen was used but resulted in an error
    if result.get("error"):
        print(json.dumps(result, indent=2))
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
