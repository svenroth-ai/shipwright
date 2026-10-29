"""screenshot_check on a served board: screens that are STATES of one page (``steps``) and a capture that survives the app's CSP (E5, F2/F3)."""

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

pytestmark = pytest.mark.covers("FR-01.06")

NODE_MODULES = os.environ.get("SHIPWRIGHT_PLAYWRIGHT_NODE_MODULES", "")
_HAVE = bool(shutil.which("node") and NODE_MODULES and (Path(NODE_MODULES) / "playwright").is_dir())
needs_browser = pytest.mark.skipif(not _HAVE, reason="set SHIPWRIGHT_PLAYWRIGHT_NODE_MODULES to a node_modules dir with playwright + Chromium installed")

QUEUE = ('<!doctype html><body style="margin:0;font-family:Arial"><input id="q"><button id="tab-queue">Queue</button>'
         '<main id="pane"><h1>Board</h1></main><script src="/app.js"></script></body>')
APP_JS = ("document.getElementById('tab-queue').onclick=function(){document.getElementById('pane').innerHTML="
          "'<h1>Queue</h1><div style=\"height:300px;background:#123\">queue</div>'}")


def project(tmp_path, entries):
    root = tmp_path / "proj"
    designs = root / ".shipwright" / "designs"
    (designs / "uploads").mkdir(parents=True)
    (designs / sc.MARKER).write_text("{}", encoding="utf-8")
    (designs / "uploads" / "04-queue.html").write_text("<body><h1>Queue</h1></body>", encoding="utf-8")
    (designs / "screen-routes.json").write_text(json.dumps({"screens": entries}), encoding="utf-8")
    return root


# ---- unit level (in-process, capture replaced) ----

def test_steps_ride_on_the_built_job_only(tmp_path, monkeypatch):
    steps = [{"click": "#tab-queue"}, {"fill": ["#q", "x"]}, {"wait_for": ".card"}]
    root = project(tmp_path, [{"mockup": "04-queue.html", "route": "/", "steps": steps}])
    seen = {}
    monkeypatch.setattr(sc, "_capture", lambda r, jobs, t: seen.update(jobs=jobs) or "stub")
    sc.run_screenshot_check(root, base_url="http://h")
    approved, built = seen["jobs"]
    assert "steps" not in approved and built["steps"] == steps and built["url"] == "http://h/"


@pytest.mark.parametrize("steps", ["click", [{"hover": "a"}], [{"click": 1}], [{"fill": ["only-selector"]}], ["click"], [{"click": "a", "wait_for": "b"}], {}, "", [{"click": ""}], [{"fill": [1, 2]}], [{"wait_for": "a"}] * 11])
def test_malformed_steps_are_an_error_not_a_pass(tmp_path, steps):
    root = project(tmp_path, [{"mockup": "04-queue.html", "route": "/", "steps": steps}])
    r = sc.run_screenshot_check(root, base_url="http://h", capture=False)
    assert r["status"] == "error" and "04-queue.html" in r["screens"][0]["error"]


def test_capture_script_injects_nothing_into_the_page():
    js = (Path(sc.__file__).parent / "screenshot_capture.mjs").read_text(encoding="utf-8")
    assert "addStyleTag" not in js and "addScriptTag" not in js and 'animations: "disabled"' in js


# ---- real Chromium ----

@pytest.fixture
def board():
    """A served board: one route, its Queue tab is a state; every response carries a strict CSP (no inline style, own-origin script)."""
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            js = self.path == "/app.js"
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript" if js else "text/html")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'")
            self.end_headers()
            self.wfile.write((APP_JS if js else QUEUE).encode())

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(H))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@needs_browser
@pytest.mark.integration
def test_csp_restricted_board_is_captured_and_a_state_is_reached(tmp_path, board, monkeypatch):
    monkeypatch.setenv("NODE_PATH", NODE_MODULES)
    root = project(tmp_path, [{"mockup": "04-queue.html", "route": "/", "steps": [{"fill": ["#q", "x"]}, {"click": "#tab-queue"}, {"wait_for": "div"}]}])
    r = sc.run_screenshot_check(root, base_url=board)
    assert "capture_error" not in r, r  # F3: the injected <style> used to be blocked by the page's CSP
    built = root / "e2e" / "screenshots" / "screenshot-check" / "built" / "01-04-queue.png"
    assert built.is_file() and r["screens"][0]["status"] in {"pass", "fail"}


@needs_browser
@pytest.mark.integration
def test_a_step_that_cannot_run_fails_the_screen_with_its_number(tmp_path, board, monkeypatch):
    monkeypatch.setenv("NODE_PATH", NODE_MODULES)
    root = project(tmp_path, [{"mockup": "04-queue.html", "route": "/", "steps": [{"wait_for": "#tab-queue"}, {"click": "#no-such-tab"}]}])
    r = sc.run_screenshot_check(root, base_url=board, timeout=120)
    assert r["status"] == "error" and "step 2" in r["capture_error"] and "no-such-tab" in r["capture_error"], r
