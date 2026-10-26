"""screenshot_check: Design's flat screen-routes.json, the file the builder used, captured flag, timeout, Playwright dirs."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import screenshot_check as sc  # noqa: E402
from png_fixtures import dashboard, login  # noqa: E402
from test_screenshot_check import make_project, place, run  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.06")

FLAT = {"01-dashboard.html": "/dashboard", "02-login.html": "/login"}  # the step-8-completion.md format


def flat_project(tmp_path):
    root = make_project(tmp_path)
    designs = root / ".shipwright" / "designs"
    (designs / "screen-routes.json").write_text(json.dumps(FLAT), encoding="utf-8")
    for name in FLAT:
        (designs / "screens" / name).write_text("<html>screen</html>", encoding="utf-8")
    return root


def test_design_format_flat_routes_are_accepted(tmp_path):
    root = flat_project(tmp_path)
    for stem, art in (("01-01-dashboard", dashboard), ("02-02-login", login)):
        place(root, stem, "approved", art())
        place(root, stem, "built", art())
    r = run(root)
    assert r["status"] == "pass" and r["total"] == 2
    assert [s["route"] for s in r["screens"]] == ["/dashboard", "/login"]


def test_flat_and_nested_shapes_parse_to_the_same_entries():
    assert sc._route_entries(FLAT)[1] == [{"mockup": "01-dashboard.html", "route": "/dashboard"},
                                         {"mockup": "02-login.html", "route": "/login"}]
    assert sc._route_entries({"base_url": "http://x", "screens": [{"mockup": "a.html", "route": "/a"}]}) == (
        "http://x", [{"mockup": "a.html", "route": "/a"}])
    assert sc._route_entries([1, 2]) == ("", [])


def test_the_screen_as_design_left_it_wins_over_the_upload(tmp_path, monkeypatch):
    root = flat_project(tmp_path)
    seen = {}
    monkeypatch.setattr(sc, "_capture", lambda project, jobs, timeout: seen.update(jobs=jobs, timeout=timeout) or "stop")
    r = sc.run_screenshot_check(root, base_url="http://x", capture=True)
    assert r["screens"][0]["compared_with"] == ".shipwright/designs/screens/01-dashboard.html"
    assert seen["jobs"][0]["url"].endswith("/screens/01-dashboard.html")
    # no screens/ copy: fall back to the approved upload
    (root / ".shipwright" / "designs" / "screens" / "01-dashboard.html").unlink()
    r = sc.run_screenshot_check(root, base_url="http://x", capture=True)
    assert r["screens"][0]["compared_with"] == ".shipwright/designs/uploads/dash-mockup.html"


def test_captured_flag_and_scaled_timeout(tmp_path, monkeypatch):
    root = flat_project(tmp_path)
    assert run(root)["captured"] is False  # the no-capture path
    seen = {}
    monkeypatch.setattr(sc, "_capture", lambda project, jobs, timeout: seen.update(n=len(jobs), t=timeout) or "stop")
    r = sc.run_screenshot_check(root, base_url="http://x", capture=True)
    assert r["captured"] is True and seen == {"n": 4, "t": 60 + 45 * 4}


def test_playwright_is_also_looked_for_in_the_service_dir(tmp_path):
    (tmp_path / "client").mkdir()
    (tmp_path / "client" / "playwright.config.ts").write_text("", encoding="utf-8")
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "playwright.config.ts").write_text("", encoding="utf-8")
    (tmp_path / "playwright.config.ts").write_text("", encoding="utf-8")
    assert sc._playwright_dirs(tmp_path) == [tmp_path / "client"]


def test_search_dirs_reach_the_capture_command(tmp_path, monkeypatch):
    (tmp_path / "e2e" / "screenshots" / "screenshot-check").mkdir(parents=True)
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "playwright.config.ts").write_text("", encoding="utf-8")
    seen = {}
    monkeypatch.setattr(sc.shutil, "which", lambda name: "node")

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return sc.subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"ok": True}), stderr="")

    monkeypatch.setattr(sc.subprocess, "run", fake_run)
    assert sc._capture(tmp_path, [], 5) is None
    assert seen["cmd"][-2:] == ["--search", str(tmp_path / "web")]
