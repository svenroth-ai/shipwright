"""screenshot_viewport: each screen is compared at its own viewport (default 1280x800), recorded per screen.

A screen designed for a phone width compared at 1280x800 measured a desktop render against a phone design
(run 20: 0.58 for a faithful phone screen). Both shots of a screen get the same size; the size and where it came
from are in the result. A declaration that is not a viewport is an `error`, never a silent default.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import screenshot_check as sc  # noqa: E402
import screenshot_viewport as sv  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.06")

PAGE = "<!doctype html><html><head>{head}</head><body>{body}</body></html>"
PHONE_CSS = "<style>:root{--phone-width: 360px} .phone-frame{max-width:var(--phone-width)}</style>"


@pytest.mark.parametrize("value,expected", [
    ([390, 800], (390, 800)), ({"width": 390, "height": 700}, (390, 700)), ("390x844", (390, 844)),
    ("390×844", (390, 844)), (390, (390, 800)), ({"width": 390}, (390, 800)),
    ("wide", None), ([390], None), ([10, 800], None), ([390, 99999], None), (True, None), (None, None), ([390.5, 800], None),
])
def test_parse_viewport(value, expected):
    assert sv._parse_viewport(value) == expected


def test_a_desktop_mockup_declares_nothing():
    html = PAGE.format(head='<meta name="viewport" content="width=device-width, initial-scale=1">' + PHONE_CSS,
                       body='<div class="app">desktop</div>')
    assert sv._mockup_viewport(html) is None  # the kit's CSS rule for .phone-frame alone is not a phone screen


def test_a_phone_frame_in_the_markup_is_a_phone_screen_at_its_own_width():
    html = PAGE.format(head=PHONE_CSS, body='<div class="app-topnav phone-frame">x</div>')
    assert sv._mockup_viewport(html) == ((360, 800), "mockup-phone-frame")
    no_var = PAGE.format(head="", body="<div class='phone-frame'>x</div>")
    assert sv._mockup_viewport(no_var) == ((390, 800), "mockup-phone-frame")


def test_a_phone_frame_inside_a_comment_or_script_does_not_count():
    html = PAGE.format(head="", body='<!-- <div class="phone-frame"> --><script>var s = \'<div class="phone-frame">\'</script>')
    assert sv._mockup_viewport(html) is None


@pytest.mark.parametrize("width", ["390.5", "99", "10000", "abc"])
def test_an_invalid_meta_width_is_an_error_never_the_default(width):
    out = sv._mockup_viewport(PAGE.format(head=f'<meta name="viewport" content="width={width}">', body=""))
    assert isinstance(out, str) and width in out


def test_device_width_declares_nothing():
    assert sv._mockup_viewport(PAGE.format(head='<meta name="viewport" content="width=device-width, initial-scale=1">', body="")) is None


def test_only_the_approved_side_decides_the_viewport(tmp_path, monkeypatch):
    desktop = PAGE.format(head="", body="desktop")
    phone = PAGE.format(head=PHONE_CSS, body="<div class='phone-frame'>x</div>")
    root = _project(tmp_path, [{"mockup": "01-a.html", "route": "/"}], {"01-a.html": desktop})
    (root / ".shipwright" / "designs" / "screens" / "01-a.html").write_text(phone, encoding="utf-8")  # the built-side copy claims a phone
    seen = {}
    monkeypatch.setattr(sc, "_capture", lambda project, jobs, timeout: seen.setdefault("jobs", jobs) and "stop")
    r = sc.run_screenshot_check(root, base_url="http://x", capture=True)
    assert r["screens"][0]["viewport"] == [1280, 800] and r["screens"][0]["viewport_source"] == "default"


def test_a_phone_frame_after_a_script_end_tag_with_attributes_still_counts_as_markup_only_outside_it():
    html = PAGE.format(head="", body="<script>var x = 1;</script foo><div class='phone-frame'>x</div>")
    assert sv._mockup_viewport(html) == ((390, 800), "mockup-phone-frame")
    assert sv._mockup_viewport(PAGE.format(head="", body="<script>'<div class=\"phone-frame\">'</script bar>")) is None


def test_meta_declarations():
    assert sv._mockup_viewport(PAGE.format(head='<meta name="shipwright-viewport" content="414x896">', body="")) == ((414, 896), "mockup-meta")
    assert sv._mockup_viewport(PAGE.format(head='<meta name="viewport" content="width=390, initial-scale=1">', body="")) == ((390, 800), "mockup-meta")
    bad = sv._mockup_viewport(PAGE.format(head='<meta name="shipwright-viewport" content="nonsense">', body=""))
    assert isinstance(bad, str) and "nonsense" in bad  # declared but not a viewport: an error text, never a silent default
    assert isinstance(sv._mockup_viewport(PAGE.format(head='<meta name="viewport" content="width=5000">', body="")), str)
    assert sv._mockup_viewport(PAGE.format(head="<style>:root{--phone-width: 999px}</style>", body="<div class='phone-frame'>")) == ((999, 800), "mockup-phone-frame")
    assert isinstance(sv._mockup_viewport(PAGE.format(head="<style>:root{--phone-width: 100px}</style>", body="<div class='phone-frame'>")), str)


def test_leading_comment_naming_the_phone_width():
    html = "<!doctype html>\n<!-- Static mockup: state 7, phone width 390px: the list becomes a picker -->\n" + PAGE.format(head="", body="x")
    assert sv._mockup_viewport(html) == ((390, 800), "mockup-comment")
    later = "<!doctype html>\n<!-- Static mockup: desktop -->\n" + PAGE.format(head="", body="<!-- phone width 390px -->x")
    assert sv._mockup_viewport(later) is None  # only the FIRST comment, the mockup's own header


def test_precedence_screen_map_then_mockup_then_default_and_routes_entry_is_an_error(tmp_path):
    phone = tmp_path / "p.html"
    phone.write_text(PAGE.format(head=PHONE_CSS, body="<div class='phone-frame'>x</div>"), encoding="utf-8")
    plain = tmp_path / "d.html"
    plain.write_text(PAGE.format(head="", body="x"), encoding="utf-8")
    assert sv.screen_viewport({}, {"viewport": [500, 600]}, [phone]) == ((500, 600), "screen-map")
    assert sv._mockup_viewport(PAGE.format(head="", body="<main><div class='phone-frame'>a preview widget</div></main>")) is None  # not the root
    assert "not accepted" in sv.screen_viewport({"viewport": "600x700"}, {"viewport": [500, 600]}, [phone])  # test wiring cannot pick it
    assert sv.screen_viewport({}, {}, [phone]) == ((360, 800), "mockup-phone-frame")
    assert sv.screen_viewport({}, None, [plain, phone]) == ((360, 800), "mockup-phone-frame")  # the approved upload may declare it
    assert sv.screen_viewport({}, {}, [plain]) == ((1280, 800), "default")
    assert sv.screen_viewport({}, {}, [tmp_path / "missing.html"]) == ((1280, 800), "default")
    assert "screen-map.json" in sv.screen_viewport({}, {"viewport": "huge"}, [plain])  # an error text, not a default


def _project(tmp_path, entries, mockups):
    root = tmp_path / "proj"
    designs = root / ".shipwright" / "designs"
    (designs / "uploads").mkdir(parents=True)
    (designs / "screens").mkdir()
    for name, html in mockups.items():
        (designs / "uploads" / name).write_text(html, encoding="utf-8")
        (designs / "screens" / name).write_text(html, encoding="utf-8")
    (designs / sc.MARKER).write_text(json.dumps({"package_sha256": "0" * 64}), encoding="utf-8")
    (designs / "screen-routes.json").write_text(json.dumps({"screens": entries}), encoding="utf-8")
    return root


def test_jobs_carry_the_screens_own_viewport_and_the_result_records_it(tmp_path, monkeypatch):
    desktop = PAGE.format(head="", body="desktop")
    phone = PAGE.format(head=PHONE_CSS, body="<div class='phone-frame'>x</div>")
    root = _project(tmp_path, [{"mockup": "01-home.html", "route": "/"}, {"mockup": "02-phone.html", "route": "/"},
                               {"mockup": "03-wiring.html", "route": "/", "viewport": [768, 1024]}],  # test wiring may NOT pick the size
                    {"01-home.html": desktop, "02-phone.html": phone, "03-wiring.html": desktop})
    seen = {}
    monkeypatch.setattr(sc, "_capture", lambda project, jobs, timeout: seen.setdefault("jobs", jobs) and "stop")
    r = sc.run_screenshot_check(root, base_url="http://x", capture=True)
    sizes = [j["viewport"] for j in seen["jobs"] if "/built/" in j["out"].replace("\\", "/")]
    assert sizes == [{"width": 1280, "height": 800}, {"width": 360, "height": 800}]
    for approved, built in zip(seen["jobs"][0::2], seen["jobs"][1::2]):  # both shots of a screen share one size
        assert approved["viewport"] == built["viewport"]
    got = [(s.get("viewport"), s.get("viewport_source")) for s in r["screens"]]
    assert got[:2] == [([1280, 800], "default"), ([360, 800], "mockup-phone-frame")]
    assert r["screens"][2]["status"] == "error" and "not accepted" in r["screens"][2]["error"]
    assert r["default_viewport"] == [1280, 800] and "viewport" not in r  # screens carry their own size


def test_an_invalid_viewport_declaration_is_an_error_for_that_screen_only(tmp_path, monkeypatch):
    html = PAGE.format(head="", body="x")
    root = _project(tmp_path, [{"mockup": "01-a.html", "route": "/"}, {"mockup": "02-b.html", "route": "/"}],
                    {"01-a.html": html, "02-b.html": html})
    (root / "brief").mkdir()
    (root / "brief" / "screen-map.json").write_text(json.dumps({"screens": [{"id": "a", "mockup": "01-a.html", "viewport": "tiny"}]}), encoding="utf-8")
    (root / "shipwright_run_config.json").write_text(json.dumps({"brief_dir": "brief"}), encoding="utf-8")
    seen = {}
    monkeypatch.setattr(sc, "_capture", lambda project, jobs, timeout: seen.setdefault("jobs", jobs) and "stop")
    r = sc.run_screenshot_check(root, base_url="http://x", capture=True)
    assert r["screens"][0]["status"] == "error" and "viewport" in r["screens"][0]["error"]
    assert len(seen["jobs"]) == 2 and all("02-02-b" in j["out"] for j in seen["jobs"])


def test_the_capture_script_honours_a_jobs_viewport():
    mjs = (Path(__file__).resolve().parent.parent / "scripts" / "lib" / "screenshot_capture.mjs").read_text(encoding="utf-8")
    assert "job.viewport" in mjs and "viewport: jobViewport" in mjs


def test_an_invalid_mockup_declaration_reaches_screen_viewport_as_an_error(tmp_path):
    bad = tmp_path / "b.html"
    bad.write_text(PAGE.format(head='<meta name="shipwright-viewport" content="nonsense">', body="x"), encoding="utf-8")
    assert "not a viewport" in sv.screen_viewport({}, {}, [bad])


def test_review_hardening():
    # a class that merely contains the token ("-phone-frame-preview") is not a phone screen
    assert sv._mockup_viewport(PAGE.format(head="", body='<div class="x-phone-frame-preview">p</div>')) is None
    # a phone width that is not a plain NNNpx value is an error, not a silent 390
    assert isinstance(sv._mockup_viewport(PAGE.format(head="<style>:root{--phone-width: 24rem}</style>", body="<div class='phone-frame'>")), str)
    assert sv._mockup_viewport(PAGE.format(head="<style>:root{--phone-width: 1024px}</style>", body="<div class='phone-frame'>")) == ((1024, 800), "mockup-phone-frame")
    # only the header comment counts, and the explicit shipwright meta beats the numeric viewport meta
    assert sv._mockup_viewport("<!doctype html>\n<html><body><!-- phone width 390px -->x</body></html>") is None
    both = PAGE.format(head='<meta name="viewport" content="width=500"><meta name="shipwright-viewport" content="414x896">', body="")
    assert sv._mockup_viewport(both) == ((414, 896), "mockup-meta")


def test_a_meta_without_name_or_content_is_skipped():
    html = PAGE.format(head='<meta charset="utf-8"><meta content="x"><meta name="shipwright-viewport" content="390x800">', body="")
    assert sv._mockup_viewport(html) == ((390, 800), "mockup-meta")
