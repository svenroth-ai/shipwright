"""screenshot_check: the BLOCKING Test-phase screenshot check (campaign B3c, D9).

Unit level: screenshots are pre-placed (``capture=False``) -- the planted-wrong-screen separation on
synthetic images lives here; the real-Chromium version is test_screenshot_check_playwright.py.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import screenshot_check as sc  # noqa: E402
from png_fixtures import blank, dashboard, login, write_png  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.06")


def make_project(tmp_path, routes=None, package=True, with_map=True):
    root = tmp_path / "proj"
    designs = root / ".shipwright" / "designs"
    (designs / "uploads").mkdir(parents=True)
    (designs / "screens").mkdir()
    (designs / "uploads" / "dash-mockup.html").write_text("<html>dash</html>", encoding="utf-8")
    (designs / "uploads" / "login-mockup.html").write_text("<html>login</html>", encoding="utf-8")
    if package:
        (designs / sc.MARKER).write_text(json.dumps({"package_sha256": "0" * 64}), encoding="utf-8")
    routes = routes if routes is not None else [
        {"mockup": "screens/01-dashboard.html", "route": "/dashboard"},
        {"mockup": "screens/02-login.html", "route": "/login"}]
    (designs / "screen-routes.json").write_text(json.dumps({"screens": routes}), encoding="utf-8")
    if with_map:
        (root / "brief").mkdir()
        (root / "brief" / "screen-map.json").write_text(json.dumps({"screens": [
            {"id": "dashboard", "mockup": "dash-mockup.html"}, {"id": "login", "mockup": "login-mockup.html"}]}), encoding="utf-8")
        (root / "shipwright_run_config.json").write_text(json.dumps({"brief_dir": "brief"}), encoding="utf-8")
    return root


def place(root, stem, side, pixels):
    d = root / "e2e" / "screenshots" / "screenshot-check" / side
    d.mkdir(parents=True, exist_ok=True)
    write_png(d / f"{stem}.png", pixels)


def run(root, **kw):
    return sc.run_screenshot_check(root, base_url="http://x", capture=False, **kw)


def test_project_without_a_package_is_untouched(tmp_path):
    root = make_project(tmp_path, package=False)
    r = sc.run_screenshot_check(root, capture=True)  # would need an app: must not even try
    assert r == {"applies": False, "status": "skipped", "reason": "no Brief package was applied by Design"}
    assert not (root / "e2e").exists()


def test_planted_wrong_screen_is_separated_from_the_right_one(tmp_path):
    root = make_project(tmp_path)
    place(root, "01-01-dashboard", "approved", dashboard())
    place(root, "02-02-login", "approved", login())
    place(root, "01-01-dashboard", "built", dashboard(accent=30, shift=2))  # right: harmless deviations
    place(root, "02-02-login", "built", blank())                           # PLANTED WRONG: an empty page
    r = run(root)
    by = {s["mockup"]: s for s in r["screens"]}
    assert by["screens/01-dashboard.html"]["status"] == "pass"
    assert by["screens/02-login.html"]["status"] == "fail"
    assert r["status"] == "fail" and (r["passed"], r["total"]) == (1, 2)
    assert r["metric"] and r["tolerance"] == sc.png_compare.TOLERANCE  # recorded, not implied
    assert by["screens/02-login.html"]["diff_ratio"] > by["screens/01-dashboard.html"]["diff_ratio"] * 5


def test_all_right_screens_pass(tmp_path):
    root = make_project(tmp_path)
    for stem, art in (("01-01-dashboard", dashboard), ("02-02-login", login)):
        place(root, stem, "approved", art())
        place(root, stem, "built", art())
    assert run(root)["status"] == "pass"


def test_missing_built_screenshot_is_an_error_that_blocks(tmp_path):
    root = make_project(tmp_path)
    place(root, "01-01-dashboard", "approved", dashboard())
    r = run(root)
    assert r["status"] == "error" and all(s["status"] == "error" for s in r["screens"])


def test_approved_mockup_is_found_via_screen_map_then_by_same_name(tmp_path):
    root = make_project(tmp_path, routes=[{"mockup": "screens/01-dashboard.html", "route": "/d"},
                                          {"mockup": "dash-mockup.html", "route": "/d"},
                                          {"mockup": "screens/09-nothing.html", "route": "/n"}])
    smap = sc._screen_map(root)
    assert sc._approved_for(root, "screens/01-dashboard.html", smap).name == "dash-mockup.html"
    assert sc._approved_for(root, "dash-mockup.html", smap).name == "dash-mockup.html"
    assert sc._approved_for(root, "screens/09-nothing.html", smap) is None
    r = run(root)
    assert r["screens"][2]["status"] == "error" and "no approved design screen" in r["screens"][2]["error"]


def test_dynamic_route_needs_a_sample_route(tmp_path):
    root = make_project(tmp_path, routes=[{"mockup": "screens/01-dashboard.html", "route": "/items/[id]"}])
    assert "sample_route" in run(root)["screens"][0]["error"]
    root2 = make_project(tmp_path / "b", routes=[{"mockup": "screens/01-dashboard.html", "route": "/items/[id]", "sample_route": "/items/1"}])
    place(root2, "01-01-dashboard", "approved", dashboard())
    place(root2, "01-01-dashboard", "built", dashboard())
    assert run(root2)["screens"][0]["status"] == "pass"


@pytest.mark.parametrize("routes", [[], None])
def test_missing_or_empty_routes_is_an_error(tmp_path, routes):
    root = make_project(tmp_path, routes=routes if routes is not None else [])
    if routes is None:
        (root / ".shipwright" / "designs" / "screen-routes.json").unlink()
    assert run(root)["status"] == "error"


def test_capture_needs_a_base_url(tmp_path):
    root = make_project(tmp_path)
    r = sc.run_screenshot_check(root, capture=True)
    assert r["status"] == "error" and "--base-url" in r["error"]


def test_capture_failure_is_reported_per_screen(tmp_path, monkeypatch):
    root = make_project(tmp_path)
    seen = {}

    def fake_capture(project, jobs, timeout):
        seen["jobs"] = jobs
        return "browser did not launch"

    monkeypatch.setattr(sc, "_capture", fake_capture)
    r = sc.run_screenshot_check(root, base_url="http://localhost:3000/", capture=True)
    assert r["status"] == "error" and r["capture_error"] == "browser did not launch"
    urls = [j["url"] for j in seen["jobs"]]
    assert "http://localhost:3000/dashboard" in urls and any(u.startswith("file:///") for u in urls)
    assert "browser did not launch" in r["screens"][0]["error"]


def test_cli_exit_codes_mirror_status(tmp_path, monkeypatch, capsys):
    root = make_project(tmp_path)
    place(root, "01-01-dashboard", "approved", dashboard())
    place(root, "01-01-dashboard", "built", blank())
    place(root, "02-02-login", "approved", login())
    place(root, "02-02-login", "built", login())
    monkeypatch.setattr(sys, "argv", ["screenshot_check.py", "--cwd", str(root), "--no-capture"])
    assert sc.main() == 1
    assert json.loads(capsys.readouterr().out)["status"] == "fail"
    place(root, "01-01-dashboard", "built", dashboard())
    assert sc.main() == 0
    (root / "e2e" / "screenshots" / "screenshot-check" / "built" / "02-02-login.png").unlink()
    assert sc.main() == 2


def test_a_package_screen_missing_from_screen_routes_is_an_error(tmp_path):
    root = make_project(tmp_path, routes=[{"mockup": "screens/01-dashboard.html", "route": "/dashboard"}])
    place(root, "01-01-dashboard", "approved", dashboard())
    place(root, "01-01-dashboard", "built", dashboard())
    r = run(root)
    missing = [x for x in r["screens"] if x["status"] == "error"]
    assert r["status"] == "error" and [x["mockup"] for x in missing] == ["login-mockup.html"]
    assert "never built or mapped" in missing[0]["error"]


def test_stale_pictures_from_a_previous_run_never_pass_a_failed_capture(tmp_path, monkeypatch):
    root = make_project(tmp_path)
    for stem, art in (("01-01-dashboard", dashboard), ("02-02-login", login)):
        place(root, stem, "approved", art())
        place(root, stem, "built", art())
    assert run(root)["status"] == "pass"  # the previous run's pictures would pass...
    monkeypatch.setattr(sc, "_capture", lambda project, jobs, timeout: "app returned HTTP 500")
    r = sc.run_screenshot_check(root, base_url="http://x", capture=True)  # ...but this run captured nothing
    assert r["status"] == "error" and all(s["status"] == "error" for s in r["screens"])


def test_same_named_mockups_get_their_own_pictures(tmp_path, monkeypatch):
    root = make_project(tmp_path, routes=[{"mockup": "screens/01-dashboard.html", "route": "/a"},
                                          {"mockup": "old/01-dashboard.html", "route": "/b"}])
    (root / ".shipwright" / "designs" / "uploads" / "01-dashboard.html").write_text("<html>x</html>", encoding="utf-8")
    seen = {}
    monkeypatch.setattr(sc, "_capture", lambda project, jobs, timeout: seen.setdefault("outs", [j["out"] for j in jobs]) and "stop")
    sc.run_screenshot_check(root, base_url="http://x", capture=True)
    outs = [Path(o).name for o in seen["outs"] if "built" in o]
    assert outs == ["01-01-dashboard.png", "02-01-dashboard.png"]


def test_a_blank_built_screen_fails_even_for_a_sparse_approved_page(tmp_path):
    sparse = blank()
    for y in range(90, 110):
        for x in range(130, 190):
            sparse[y][x] = 60 if (x + y) % 7 == 0 else 250
    root = make_project(tmp_path, routes=[{"mockup": "screens/01-dashboard.html", "route": "/dashboard"},
                                          {"mockup": "screens/02-login.html", "route": "/login"}])
    place(root, "01-01-dashboard", "approved", sparse)
    place(root, "01-01-dashboard", "built", blank())
    place(root, "02-02-login", "approved", login())
    place(root, "02-02-login", "built", login())
    r = run(root)
    assert r["screens"][0]["status"] == "fail" and "blank" in r["screens"][0]["error"]
    assert r["status"] == "fail"


def test_a_package_screen_with_neither_route_nor_upload_is_an_error(tmp_path):
    root = make_project(tmp_path, routes=[{"mockup": "screens/01-dashboard.html", "route": "/dashboard"}])
    (root / ".shipwright" / "designs" / "uploads" / "login-mockup.html").unlink()
    place(root, "01-01-dashboard", "approved", dashboard())
    place(root, "01-01-dashboard", "built", dashboard())
    r = run(root)
    assert r["status"] == "error" and "no approved design screen in uploads/" in r["screens"][-1]["error"]
