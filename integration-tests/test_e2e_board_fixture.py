"""E6 (campaign e2e-run-findings): the Brief package for the skill-backed board app and the answer key the operator
harness (`integration-tests/e2e-webui/`) evaluates. No model, no browser: CI checks that the package is a valid,
warning-free input for the pipeline and that every checklist item has an evaluator in the harness."""

import json
import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
FIXTURES = _REPO / "integration-tests" / "fixtures"
FIXTURE = FIXTURES / "social-engagement-board"
EXPECTED = FIXTURES / "social-engagement-board-expected-result.md"
SRC = _REPO / "integration-tests" / "e2e-webui" / "src"
BRIEF_REL = "integration-tests/fixtures/social-engagement-board"


def _shared(name: str):
    sys.path.insert(0, str(_REPO / "shared" / "scripts"))
    try:
        mod = __import__(f"lib.{name}", fromlist=[name]) if name.startswith("brief_") else None
    finally:
        sys.path.remove(str(_REPO / "shared" / "scripts"))
    return mod


def _items():
    return re.findall(r"^- \[(hard|soft)\] ([A-Z]\d+): (.+)$", EXPECTED.read_text(encoding="utf-8"), re.M)


@pytest.mark.covers("FR-01.06")
def test_package_declares_the_skill_app_class_values():
    brief = json.loads((FIXTURE / "brief.json").read_text(encoding="utf-8"))
    assert (brief["profile"], brief["ux_shape"], brief["ui_host"]) == ("skill-companion-app", "classic", "served-board")
    assert not (FIXTURE / "chat-map.json").exists(), "the chat is the Claude app: no chat map for this app class"
    assert (_REPO / "shared" / "profiles" / f"{brief['profile']}.json").is_file()


@pytest.mark.covers("FR-01.06")
def test_package_passes_the_intake_content_check_and_declares_every_kit_token():
    """The decided target of the second run is the kit look with the package's own tokens: prose or table forms
    would only warn at intake, so the fixture must come back with no issues and no warnings at all."""
    checks = _shared("brief_intake_checks")
    assert checks.check_content(_REPO, BRIEF_REL) == []
    assert checks.token_warnings(FIXTURE / "visual-guidelines.md") == []


@pytest.mark.covers("FR-01.06")
def test_screen_map_requirements_are_headings_of_brief_md():
    brief = (FIXTURE / "brief.md").read_text(encoding="utf-8")
    slugs = {re.sub(r"[^a-z0-9]+", "-", m.lower()).strip("-") for m in re.findall(r"^## (.+)$", brief, re.M)}
    screens = json.loads((FIXTURE / "screen-map.json").read_text(encoding="utf-8"))["screens"]
    mapped = {r for s in screens for r in s["requirements"]}
    assert mapped <= slugs, mapped - slugs
    assert slugs - {"glossary"} <= mapped, "a requirement without a screen would turn the fr-coverage gate red"


@pytest.mark.covers("FR-01.06")
def test_mockups_are_a_board_without_chat_and_share_one_tab_strip():
    mockups = sorted((FIXTURE / "mockups").glob("*.html"))
    assert len(mockups) == 5
    strips = set()
    for m in mockups:
        text = m.read_text(encoding="utf-8")
        assert not re.search(r"chat|composer|message-log|msg-", text, re.I), m.name
        assert not re.search(r"(src|href)=\"https?://|@import", text), f"{m.name} must be self-contained"
        strips.add(re.search(r'<div class="tabs".*?</div>', re.sub(r" active", "", text), re.S).group(0))
    assert len(strips) == 1, "the chrome gate needs one navigation across all mockups"


@pytest.mark.covers("FR-01.06")
def test_brief_md_documents_every_route_the_harness_calls():
    """The answer key is outside the package, so the building agent only knows the API from brief.md."""
    brief = (FIXTURE / "brief.md").read_text(encoding="utf-8")
    api = (SRC / "board-api.ts").read_text(encoding="utf-8")
    routes = set(re.findall(r'["`](/api/[a-z/${}A-Za-z-]+)', api)) - {"/api/no-such-route"}
    assert routes, "board-api.ts calls no route?"
    for route in routes:
        stem = re.sub(r"\$\{[^}]+\}", "<id>", route)
        assert stem in brief, f"{route} is called by the harness but not documented in brief.md"


@pytest.mark.covers("FR-01.06")
def test_every_checklist_item_has_an_evaluator_and_only_s03_is_soft():
    items = _items()
    assert {i for k, i, _ in items if k == "soft"} == {"S03"}
    assert len({i for _, i, _ in items}) == len(items)
    sources = "\n".join(p.read_text(encoding="utf-8") for p in SRC.glob("*.ts")) + "\n" + (
        _REPO / "integration-tests" / "e2e-webui" / "tests" / "e2e.spec.ts").read_text(encoding="utf-8")
    for _, item, _ in items:
        assert re.search(rf'["\']{item}["\']', sources), f"no harness module records {item}"


@pytest.mark.covers("FR-01.06")
def test_harness_reads_the_new_fixture_not_the_chat_first_one():
    fixture_ts = (SRC / "fixture.ts").read_text(encoding="utf-8")
    assert 'FIXTURE_NAME = "social-engagement-board"' in fixture_ts
    assert 'PROFILE = "skill-companion-app"' in fixture_ts
    assert not (SRC / "chat.ts").exists()
    assert "chat-first-json" not in (_REPO / "integration-tests" / "e2e-webui" / "tests" / "e2e.spec.ts").read_text(encoding="utf-8")
