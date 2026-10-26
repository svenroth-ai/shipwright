"""Chat-first planning (B3b): ``tools/brief_chat_plan.py`` and the chip rule of ``design_gate_html``."""

from __future__ import annotations

import json
import time

import pytest

from lib.design_gate_html import chip_nav_class_violations
from tools.brief_chat_plan import chat_map_issues, flow_page, plan_flows

SCREEN_MAP = {"screens": [
    {"id": "board", "mockup": "01-board.html", "requirements": ["fetch-new-matches", "view-the-board"]},
    {"id": "detail", "mockup": "02-detail.html", "requirements": ["show-a-thread"]},
]}


def _chat_map() -> dict:
    return {"version": 1,
            "capabilities": [{"id": "fetch", "command": "fetch new matches", "requirements": ["fetch-new-matches"], "screen": "board"},
                             {"id": "show", "command": "show thread N", "requirements": ["Show a thread"], "screen": "detail"}],
            "golden_paths": [{"id": "triage", "title": "Triage", "steps": [{"say": "fetch new matches", "screen": "board"},
                                                                         {"say": "show thread 1", "screen": "detail"}]}]}


@pytest.mark.covers("FR-01.04")
def test_a_consistent_chat_map_has_no_issues():
    assert chat_map_issues(_chat_map(), SCREEN_MAP) == []


@pytest.mark.covers("FR-01.04")
@pytest.mark.parametrize("change,needle", [
    (lambda d: d["capabilities"][0].update(screen="gone"), "pane-state screen"),
    (lambda d: d["capabilities"][0].update(requirements=["show-a-thread"]), "does not list"),
    (lambda d: d["capabilities"][0].update(requirements=[]), "requirements must be"),
    (lambda d: d["capabilities"][0].update(command=" "), "command must be"),
    (lambda d: d["capabilities"][1].update(id="fetch"), "repeated"),
    (lambda d: d["golden_paths"][0]["steps"][1].update(say=""), "say must be"),
    (lambda d: d["golden_paths"][0].update(title=3), "title must be"),
    (lambda d: d.update(capabilities="x"), "capabilities must be"),
])
def test_each_defect_is_named(change, needle):
    data = _chat_map()
    change(data)
    assert any(needle in i["message"] for i in chat_map_issues(data, SCREEN_MAP)), chat_map_issues(data, SCREEN_MAP)


@pytest.mark.covers("FR-01.04")
def test_a_screen_map_entry_that_is_malformed_never_crashes_the_chat_check():
    broken = {"screens": ["x", {"id": "board", "requirements": "no-list"}]}
    issues = chat_map_issues(_chat_map(), broken)  # issues, not an exception
    assert issues and all(i["code"] == "bad_chat_map" for i in issues)
    assert not any("golden_paths" in i["screen"] and "version" in i["message"] for i in issues)


@pytest.mark.covers("FR-01.04")
def test_a_dangling_screen_is_reported_even_when_requirements_are_malformed():
    data = _chat_map()
    data["capabilities"][0].update(requirements="x", screen="gone")
    messages = [i["message"] for i in chat_map_issues(data, SCREEN_MAP)]
    assert any("requirements must be" in m for m in messages) and any("pane-state screen" in m for m in messages)


@pytest.mark.covers("FR-01.04")
def test_the_flow_shows_the_pane_state_mockup_standalone(tmp_path):
    from lib.design_gate_html import standalone_html_violations

    (tmp_path / "mockups").mkdir()
    (tmp_path / "mockups" / "01-board.html").write_text('<p class="x">HELLO "q"</p><a href="https://evil.example">x</a>', encoding="utf-8")
    (tmp_path / "chat-map.json").write_text(json.dumps(_chat_map()), encoding="utf-8")
    page = plan_flows(tmp_path, SCREEN_MAP)[0][0]["html"]
    assert 'srcdoc="&lt;p class=&quot;x&quot;&gt;HELLO &quot;q&quot;&lt;/p&gt;' in page and "<iframe sandbox" in page
    assert standalone_html_violations(page) == []  # the inlined mockup is an attribute value, not a reference of the flow page


@pytest.mark.covers("FR-01.04")
def test_flow_pages_are_escaped_standalone_and_numbered(tmp_path):
    data = _chat_map()
    data["golden_paths"][0]["title"] = "<script>alert(1)</script> & co"
    (tmp_path / "chat-map.json").write_text(json.dumps(data), encoding="utf-8")
    flows, issues = plan_flows(tmp_path, SCREEN_MAP)
    assert issues == [] and [f["file"] for f in flows] == ["01-triage.html"]
    page = flows[0]["html"]
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "http" not in page and "nav-item" not in page and "href" not in page
    assert "Pane: detail (02-detail.html)" in page
    assert flow_page(data["golden_paths"][0], {}) == flow_page(data["golden_paths"][0], {})  # deterministic


@pytest.mark.covers("FR-01.04")
def test_a_missing_or_broken_chat_map_file_is_an_issue_not_a_crash(tmp_path):
    flows, issues = plan_flows(tmp_path, SCREEN_MAP)
    assert flows == [] and issues[0]["code"] == "bad_chat_map"
    (tmp_path / "chat-map.json").write_text("{not json", encoding="utf-8")
    assert plan_flows(tmp_path, SCREEN_MAP)[1][0]["code"] == "bad_chat_map"


@pytest.mark.covers("FR-01.04")
def test_chip_rule():
    assert chip_nav_class_violations('<button class="chip">go</button>') == []
    assert chip_nav_class_violations('<a class="nav-item" href="/a">go</a>') == []  # plain nav is the chrome gate's business
    assert chip_nav_class_violations('<a class="chip nav-item" href="/a">go</a>') == ["chip nav-item"]
    assert chip_nav_class_violations('<a class="chip-row topnav-link">go</a>') == ["chip-row topnav-link"]
    assert chip_nav_class_violations('<a class="chipper nav-item">go</a>') == []  # only chip / chip-*
    assert chip_nav_class_violations('<!-- <a class="chip nav-item"> -->') == ["chip nav-item"]  # the scanner also reads comments


@pytest.mark.covers("FR-01.04")
def test_chip_rule_is_fast_on_hostile_markup():
    hostile = '<a class="' + "chip " * 20000 + '">' + "<a " * 20000
    start = time.perf_counter()
    chip_nav_class_violations(hostile)
    assert time.perf_counter() - start < 5
