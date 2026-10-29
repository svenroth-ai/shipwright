"""The real-skill variant of the E2E fixture (`social-engagement-real`): a master-detail board whose hits come from an
exchangeable source adapter with recorded Syften/Apify answers. Like test_e2e_board_fixture.py this needs no model and
no browser: CI checks that the package is a valid, warning-free pipeline input, that the mockups follow the
master-detail structure, and that the answer key, the brief and the harness agree on routes, items and variants."""

import json
import re
import sys
from pathlib import Path

import pytest

import _brief_harness as h

_REPO = Path(__file__).resolve().parents[1]
FIXTURES = _REPO / "integration-tests" / "fixtures"
NAME = "social-engagement-real"
FIXTURE = FIXTURES / NAME
EXPECTED = FIXTURES / f"{NAME}-expected-result.md"
SRC = _REPO / "integration-tests" / "e2e-webui" / "src"
BRIEF_REL = f"integration-tests/fixtures/{NAME}"


def _shared(name: str):
    sys.path.insert(0, str(_REPO / "shared" / "scripts"))
    try:
        return __import__(f"lib.{name}", fromlist=[name])
    finally:
        sys.path.remove(str(_REPO / "shared" / "scripts"))


def _items():
    return re.findall(r"^- \[(hard|soft)\] ([A-Z]\d+): (.+)$", EXPECTED.read_text(encoding="utf-8"), re.M)


@pytest.mark.covers("FR-01.06")
def test_package_declares_the_skill_app_class_and_the_hash_matches():
    brief = json.loads((FIXTURE / "brief.json").read_text(encoding="utf-8"))
    assert (brief["profile"], brief["ux_shape"], brief["ui_host"]) == ("skill-companion-app", "classic", "served-board")
    ok, issues = _shared("brief_package").verify_package(FIXTURE, expected=brief["package_sha256"])
    assert ok, issues
    assert not (FIXTURE / "chat-map.json").exists()
    assert not (FIXTURE / "expected-result.md").exists(), "the answer key must stay outside the hashed package"


@pytest.mark.covers("FR-01.06")
def test_package_is_warning_free_at_intake_and_brief_md_passes_the_project_content_check():
    checks = _shared("brief_intake_checks")
    assert checks.check_content(_REPO, BRIEF_REL) == []
    assert checks.token_warnings(FIXTURE / "visual-guidelines.md") == []
    sys.path.insert(0, str(_REPO / "shared" / "scripts"))
    try:
        from tools import brief_project_mode as bpm  # noqa: PLC0415
    finally:
        sys.path.remove(str(_REPO / "shared" / "scripts"))
    text = (FIXTURE / "brief.md").read_text(encoding="utf-8")
    assert bpm.check_capabilities(*bpm.parse_brief_md(text)) == []
    assert bpm.glossary_unparsed(text) == []


@pytest.mark.covers("FR-01.06")
def test_package_passes_the_dry_harness(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIPWRIGHT_ACCEPT_FIXTURE_APPROVAL", "1")
    project = h.prepare_scratch_project(tmp_path / "proj", FIXTURE)
    report = h.run_harness(project, fixture=NAME, report_path=tmp_path / "report.json")
    assert report["outcome"] == "dry-ok", report


@pytest.mark.covers("FR-01.06")
def test_screen_map_requirements_are_headings_of_brief_md():
    brief = (FIXTURE / "brief.md").read_text(encoding="utf-8")
    slugs = {re.sub(r"[^a-z0-9]+", "-", m.lower()).strip("-") for m in re.findall(r"^## (.+)$", brief, re.M)}
    screens = json.loads((FIXTURE / "screen-map.json").read_text(encoding="utf-8"))["screens"]
    mapped = {r for s in screens for r in s["requirements"]}
    assert mapped <= slugs, mapped - slugs
    assert slugs - {"glossary"} <= mapped, "a requirement without a screen would turn the fr-coverage gate red"
    assert {s["mockup"] for s in screens} == {p.name for p in (FIXTURE / "mockups").glob("*.html")}


@pytest.mark.covers("FR-01.06")
def test_mockups_are_master_detail_boards_without_chat_and_without_a_keywords_tab():
    mockups = sorted((FIXTURE / "mockups").glob("*.html"))
    assert len(mockups) == 5
    headers = set()
    for m in mockups:
        text = m.read_text(encoding="utf-8")
        assert not re.search(r"chat|composer|message-log|msg-", text, re.I), m.name
        assert not re.search(r"keywords", text, re.I), f"{m.name}: keywords are sources, not a tab"
        assert not re.search(r"(src|href)=\"https?://|@import", text), f"{m.name} must be self-contained"
        assert 'class="list"' in text and 'class="detail"' in text, f"{m.name} is not master-detail"
        for status in ("new", "drafted", "posted", "expired"):
            assert f"badge-{status}" in text, (m.name, status)
        assert "Inter" in text and "Geist Mono" in text, f"{m.name} must carry the brand fonts"
        headers.add(re.search(r'<header class="bar">.*?</header>', text.replace('class="active"', 'class=""'), re.S).group(0))
    assert len(headers) == 1, "the chrome gate needs one header (title, platform switcher, filter) across all mockups"
    draft = (FIXTURE / "mockups" / "03-reply-draft.html").read_text(encoding="utf-8")
    assert "Copy reply" in draft and "Feedback" in draft


@pytest.mark.covers("FR-01.06")
def test_brief_md_documents_every_route_the_real_harness_calls():
    """The answer key is outside the package, so the building agent only knows the API from brief.md."""
    brief = (FIXTURE / "brief.md").read_text(encoding="utf-8")
    api = (SRC / "board-api-real.ts").read_text(encoding="utf-8")
    routes = set(re.findall(r'["`](/api/[A-Za-z/${}-]+)', api)) - {"/api/no-such-route"}
    assert routes, "board-api-real.ts calls no route?"
    for route in routes:
        stem = re.sub(r"\$\{[^}]+\}", "<id>", route)
        assert stem in brief, f"{route} is called by the harness but not documented in brief.md"


@pytest.mark.covers("FR-01.06")
def test_adapter_contract_and_recorded_answers_are_spelled_out_in_brief_md():
    """S05 reads `backend/sources/`, `fetch_items` and `seed/recorded/*.json`; the building agent can only learn them here."""
    brief = (FIXTURE / "brief.md").read_text(encoding="utf-8")
    checks = (SRC / "project-checks-adapter.ts").read_text(encoding="utf-8")
    for needle in re.findall(r'"((?:backend|seed)/[A-Za-z_/.]+)"', checks):
        assert needle in brief or needle.replace("backend/sources", "`backend/sources/`") in brief, needle
    assert "fetch_items" in brief and "never touches the network" in brief
    assert "SYFTEN_TOKEN" in brief and "APIFY_TOKEN" in brief
    for statuses in ("skipped", "expired"):
        assert statuses in brief


@pytest.mark.covers("FR-01.06")
def test_answer_key_has_an_evaluator_per_item_and_only_s03_and_s09_are_soft():
    items = _items()
    assert {i for k, i, _ in items if k == "soft"} == {"S03", "S09"}
    assert len({i for _, i, _ in items}) == len(items)
    spec = (_REPO / "integration-tests" / "e2e-webui" / "tests" / "e2e.spec.ts").read_text(encoding="utf-8")
    sources = "\n".join(p.read_text(encoding="utf-8") for p in SRC.glob("*.ts")) + "\n" + spec
    for _, item, _ in items:
        assert re.search(rf'["\']{item}["\']', sources), f"no harness module records {item}"
    # The default fixture's key must be a subset of this one's ids, so every shared module still finds its item.
    base = {i for _, i, _ in re.findall(r"^- \[(hard|soft)\] ([A-Z]\d+): (.+)$",
                                      (FIXTURES / "social-engagement-board-expected-result.md").read_text(encoding="utf-8"), re.M)}
    assert base <= {i for _, i, _ in items}


@pytest.mark.covers("FR-01.06")
def test_harness_selects_the_fixture_by_name_and_defaults_to_the_tabs_one():
    fixture_ts = (SRC / "fixture.ts").read_text(encoding="utf-8")
    assert 'FIXTURE_NAME = "social-engagement-board"' in fixture_ts
    assert 'REAL_FIXTURE_NAME = "social-engagement-real"' in fixture_ts
    assert "SHIPWRIGHT_E2E_FIXTURE" in fixture_ts
    spec = (_REPO / "integration-tests" / "e2e-webui" / "tests" / "e2e.spec.ts").read_text(encoding="utf-8")
    assert "activeFixture()" in spec and "variantFor(FIXTURE_NAME)" in spec
