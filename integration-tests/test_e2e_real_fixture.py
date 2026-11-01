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
    assert "activeFixture({ SHIPWRIGHT_E2E_FIXTURE: cfg.fixture })" in spec and "variantFor(FIXTURE_NAME)" in spec
    env_ts = (SRC / "env.ts").read_text(encoding="utf-8")  # the env file is read like the other inputs (trg-cbf58cba)
    assert "SHIPWRIGHT_E2E_FIXTURE" in env_ts


# --- the shipped recorded answers, the summary rule and the draft template (trg-5da1201c) -------------------------------

_SENTENCE = re.compile(r"^(.+?[.!?])(?:\s|$)", re.S)
_ANGLE = "Answer the question plainly, share what worked for us and ask what they tried."
_DRAFT = 'Hi {author}, thanks for asking about "{title}". We ran into the same question. Happy to share what worked for us - what have you tried so far?'


def _collapse(value) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text.rfind(" ", 0, limit - 1)
    return (text[:cut] if cut > 0 else text[: limit - 1]).rstrip() + "…"


def _summarize(item: dict) -> dict:
    """The rule of brief.md 'Read a thread', written out once more so the package text and the mockups are held to it."""
    text = _collapse(item["text"])
    if text:
        m = _SENTENCE.match(text)
        question = _shorten(m.group(1) if m else text, 300)
    else:
        question = _shorten(_collapse(item["title"]), 300)
    joined = " ".join(t for t in (_collapse(c["text"]) for c in item["comments"]) if t)
    return {"question": question, "others": _shorten(joined, 400) if joined else "No comments yet.", "angle": _ANGLE}


def _recorded():
    rec = FIXTURE / "seed" / "recorded"
    syften = json.loads((rec / "syften.json").read_text(encoding="utf-8"))
    apify = json.loads((rec / "apify_linkedin.json").read_text(encoding="utf-8"))
    return syften, apify


@pytest.mark.covers("FR-01.06")
def test_shipped_recordings_are_valid_four_per_platform_with_old_items_and_no_real_hosts():
    from datetime import datetime, timedelta  # noqa: PLC0415

    syften, apify = _recorded()
    stamps, per = [], {"reddit": 0, "hackernews": 0, "linkedin": 0}
    urls = []
    for rec in syften:
        item = rec["item"]
        assert {"item_url", "backend", "timestamp", "title", "author", "text", "comments"} <= set(item), rec["id"]
        per[item["backend"]] += 1
        stamps.append(datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")))
        urls.append(item["item_url"])
        for c in item["comments"]:
            assert {"author", "text"} <= set(c) and 0 <= c["depth"] <= 2
    for rec in apify:
        assert {"id", "linkedinUrl", "author", "content", "postedAt", "comments"} <= set(rec), rec["id"]
        assert rec["author"]["name"]
        per["linkedin"] += 1
        stamps.append(datetime.fromisoformat(rec["postedAt"]["date"].replace("Z", "+00:00")))
        urls.append(rec["linkedinUrl"])
        for c in rec["comments"]:
            assert {"author", "text"} <= set(c) and 0 <= c["depth"] <= 2
    assert per == {"reddit": 4, "hackernews": 4, "linkedin": 4}
    assert all(s.tzinfo is not None for s in stamps)
    newest = max(stamps)
    assert sum(1 for s in stamps if newest - s > timedelta(days=14)) == 3
    # the app expires a thread one day earlier (the replay shifts the newest item to 1 day old): no item may sit in that window
    assert sum(1 for s in stamps if newest - s > timedelta(days=13)) == 3
    assert len(set(urls)) == 12
    assert all(re.match(r"https?://[^/]*\.example/", u) for u in urls), "recordings must use invented hosts"


@pytest.mark.covers("FR-01.06")
def test_brief_md_states_the_rule_the_angle_the_template_and_the_copy_of_the_recordings_verbatim():
    brief = (FIXTURE / "brief.md").read_text(encoding="utf-8")
    assert _ANGLE in brief and _DRAFT in brief
    assert r"^(.+?[.!?])(?:\s|$)" in brief and "`No comments yet.`" in brief
    assert "the build copies both byte for byte to `seed/recorded/` of the project it builds" in brief
    assert "adds no further recorded data" in brief
    syften, _ = _recorded()
    thread = next(r["item"] for r in syften if r["item"]["author"] == "copper_fieldmouse")
    assert _DRAFT.format(author=_collapse(thread["author"]), title=_collapse(thread["title"])) in brief, "named-thread fit criterion"
    onboarding = next(r["item"] for r in syften if r["item"]["author"] == "quiet_lantern_42")
    assert f"`{_summarize(onboarding)['question']}`" in brief


@pytest.mark.covers("FR-01.06")
def test_mockup_text_equals_what_the_shipped_recordings_the_rule_and_the_template_produce():
    import html  # noqa: PLC0415

    syften, _ = _recorded()
    by_title = {r["item"]["title"]: r["item"] for r in syften}
    checked = drafts = 0
    for name in ("02-thread", "03-reply-draft", "04-thread-posted"):
        text = html.unescape((FIXTURE / "mockups" / f"{name}.html").read_text(encoding="utf-8"))
        title = re.search(r'<article class="card post">.*?<h2>(.*?)</h2>', text, re.S).group(1)
        item = by_title[title]
        s = _summarize(item)
        assert re.findall(r"<dd>(.*?)</dd>", text) == [s["question"], s["others"], s["angle"]], name
        assert re.search(r"<h2>.*?</h2><p>" + re.escape(item["text"]) + "</p>", text), name
        n = item["points"]
        assert f" · {n} point{'' if n == 1 else 's'} · " in text, name
        shown = re.findall(r'<div class="comment(?: d(\d))?"><div class="meta">u/(.*?) · (\d+) points?</div>(.*?)</div>', text)
        assert [(int(d or 0), a, int(pt), tx) for d, a, pt, tx in shown] == [(c["depth"], c["author"], c["points"], c["text"]) for c in item["comments"]], name
        draft_cards = re.findall(r'<section class="card draft">.*?<p>(.*?)</p>', text, re.S)
        assert len(draft_cards) == (1 if name == "03-reply-draft" else 0), name
        for d in draft_cards:
            assert d == _DRAFT.format(author=item["author"], title=item["title"]), name
            drafts += 1
        checked += 1
    assert (checked, drafts) == (3, 1)
    # The list on every screen is the same four recorded Reddit threads, in recorded order, with the same status labels.
    order = [r["item"] for r in syften if r["item"]["backend"] == "reddit"]
    expected = [(re.search(r"/r/([^/]+)/", i["item_url"]).group(1), i["author"], i["title"]) for i in order]
    rows_by_screen = {}
    for m in sorted((FIXTURE / "mockups").glob("*.html")):
        text = html.unescape(m.read_text(encoding="utf-8"))
        rows = re.findall(r'<div class="w"><span>r/(.*?)</span><span>u/(.*?)</span></div><div class="t">(.*?)</div><span class="badge badge-(\w+)">(\w+)</span>', text)
        assert [r[:3] for r in rows] == expected, m.name
        assert all(r[3] == r[4] for r in rows), m.name
        rows_by_screen[m.name] = [r[3] for r in rows]
    assert len(rows_by_screen) == 5
    assert all(v == ["new", "drafted", "posted", "expired"] for v in rows_by_screen.values()), rows_by_screen
