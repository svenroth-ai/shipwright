"""screenshot_check against a REAL Chromium (campaign B3c, D9 hard gate: planted wrong screen vs right one).

Needs Node, Playwright and an installed Chromium. Opt in by pointing SHIPWRIGHT_PLAYWRIGHT_NODE_MODULES at a
``node_modules`` directory that holds ``playwright`` (``npm i playwright && npx playwright install chromium``).
Without it the test SKIPS -- the unit-level separation in test_screenshot_check.py still runs everywhere.
"""

import functools
import http.server
import json
import os
import shutil
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))
import screenshot_check as sc  # noqa: E402

NODE_MODULES = os.environ.get("SHIPWRIGHT_PLAYWRIGHT_NODE_MODULES", "")
pytestmark = [
    pytest.mark.covers("FR-01.06"),
    pytest.mark.integration,
    pytest.mark.skipif(not shutil.which("node"), reason="node is not installed"),
    pytest.mark.skipif(not (NODE_MODULES and (Path(NODE_MODULES) / "playwright").is_dir()),
                       reason="set SHIPWRIGHT_PLAYWRIGHT_NODE_MODULES to a node_modules dir with playwright + Chromium installed"),
]


def dashboard(title="Notes", font="Georgia,serif", accent="#2563eb", radius=8):
    cards = "".join(f'<div style="background:#fff;border:1px solid #e2e8f0;border-radius:{radius}px;padding:16px;height:120px">'
                    f'<small>Metric {i}</small><h2 style="color:{accent}">{i * 37}</h2></div>' for i in (1, 2, 3))
    rows = "".join(f"<p>Row {i} - some item text here</p>" for i in range(8))
    return (f'<!doctype html><body style="margin:0;font-family:{font};background:#f8fafc"><div style="display:flex;height:800px">'
            f'<nav style="width:240px;background:#fff;border-right:1px solid #e2e8f0;padding:16px"><b>{title}</b><p>Dashboard</p><p>Settings</p></nav>'
            f'<main style="flex:1;padding:24px"><h1>{title} overview</h1><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px">{cards}</div>'
            f'<div style="background:#fff;border:1px solid #e2e8f0;border-radius:{radius}px;margin-top:16px;padding:16px;height:380px"><h3>Recent</h3>{rows}</div>'
            "</main></div></body>")


LOGIN = ('<!doctype html><body style="margin:0;background:#0f172a;color:#fff;display:flex;align-items:center;justify-content:center;height:800px">'
         '<form style="background:#1e293b;padding:32px;width:360px;border-radius:12px"><h1>Sign in</h1><input style="width:100%;height:36px">'
         '<br><br><button style="width:100%;height:40px">Login</button></form></body>')


@pytest.fixture
def app(tmp_path):
    """A 'built app': /dashboard is the RIGHT screen (other font/accent/radius), /login is the PLANTED WRONG one (empty page)."""
    site = tmp_path / "site"
    site.mkdir()
    (site / "dashboard").write_text(dashboard("Notes app", "Arial,sans-serif", "#1d4ed8", 6), encoding="utf-8")
    (site / "login").write_text("<!doctype html><body style='margin:0;background:#f8fafc'></body>", encoding="utf-8")
    class Html(http.server.SimpleHTTPRequestHandler):
        def guess_type(self, path):
            return "text/html"

        def log_message(self, *args):
            pass

    handler = functools.partial(Html, directory=str(site))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_real_browser_separates_planted_wrong_screen_from_right_one(tmp_path, app, monkeypatch):
    monkeypatch.setenv("NODE_PATH", NODE_MODULES)
    root = tmp_path / "proj"
    designs = root / ".shipwright" / "designs"
    (designs / "uploads").mkdir(parents=True)
    (designs / sc.MARKER).write_text(json.dumps({"package_sha256": "0" * 64}), encoding="utf-8")
    (designs / "uploads" / "01-dashboard.html").write_text(dashboard(), encoding="utf-8")
    (designs / "uploads" / "02-login.html").write_text(LOGIN, encoding="utf-8")
    (designs / "screen-routes.json").write_text(json.dumps({"screens": [
        {"mockup": "01-dashboard.html", "route": "/dashboard"}, {"mockup": "02-login.html", "route": "/login"}]}), encoding="utf-8")
    r = sc.run_screenshot_check(root, base_url=app)
    by = {s["mockup"]: s for s in r["screens"]}
    assert by["01-dashboard.html"]["status"] == "pass", r
    assert by["02-login.html"]["status"] == "fail", r
    assert r["status"] == "fail" and r["metric"] and r["tolerance"] == sc.png_compare.TOLERANCE
    assert (root / "e2e" / "screenshots" / "screenshot-check" / "built" / "02-02-login.png").is_file()
