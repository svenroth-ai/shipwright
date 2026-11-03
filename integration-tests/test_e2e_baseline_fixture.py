"""The baseline fixture of the E2E harness (`social-engagement-baseline`): the finished Briefing package of the skill companion
app, derived from the real social-engagement skill, with its own answer key and its own checks (`e2e-webui/src/baseline/`).
Like the other fixture tests this needs no model and no browser: the package is a valid, warning-free pipeline input that the
delivered files never changed, the approval is recorded by the harness in a COPY, and the answer key, the package and the
harness agree on ids, routes and the fake-server index."""

import json
import re
import sys
from pathlib import Path

import pytest

import _brief_harness as h

_REPO = Path(__file__).resolve().parents[1]
FIXTURES = _REPO / "integration-tests" / "fixtures"
NAME = "social-engagement-baseline"
FIXTURE = FIXTURES / NAME
EXPECTED = FIXTURES / f"{NAME}-expected-result.md"
E2E = _REPO / "integration-tests" / "e2e-webui"
SRC = E2E / "src"
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
def test_package_is_the_delivered_one_valid_and_unapproved():
    brief = json.loads((FIXTURE / "brief.json").read_text(encoding="utf-8"))
    assert (brief["profile"], brief["ux_shape"], brief["ui_host"]) == ("skill-companion-app", "classic", "served-board")
    ok, issues = _shared("brief_package").verify_package(FIXTURE, expected=brief["package_sha256"])
    assert ok, issues
    # approval is the harness's job (in the run's copy); the delivered package must not carry a hand-written one
    assert "approved_by" not in brief and "approved_at" not in brief
    assert (FIXTURE / "OPEN.md").exists() and (FIXTURE / "provenance.md").exists()
    assert not (FIXTURE / "evidence").exists() and not (FIXTURE / "expected-result.md").exists()
    assert len(list((FIXTURE / "mockups").glob("*.html"))) == 7 == len(list((FIXTURE / "mockups").glob("*.png")))


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
def test_package_with_the_harness_approval_in_its_copy_passes_the_dry_harness(tmp_path, monkeypatch):
    """The e2e spec stamps `approved_by: fixture:<name>` into `<project>/brief/brief.json` (src/baseline/approval.ts)."""
    monkeypatch.setenv("SHIPWRIGHT_ACCEPT_FIXTURE_APPROVAL", "1")
    project = h.prepare_scratch_project(tmp_path / "proj", FIXTURE)
    copy = project / "brief" / "brief.json"
    brief = json.loads(copy.read_text(encoding="utf-8"))
    brief["approved_by"], brief["approved_at"] = f"fixture:{NAME}", "2026-11-03T00:00:00Z"
    copy.write_text(json.dumps(brief, indent=2) + "\n", encoding="utf-8")
    report = h.run_harness(project, fixture=NAME, report_path=tmp_path / "report.json")
    assert report["outcome"] == "dry-ok", report


@pytest.mark.covers("FR-01.06")
def test_screen_map_requirements_are_headings_of_brief_md_and_mockups_match():
    brief = (FIXTURE / "brief.md").read_text(encoding="utf-8")
    slugs = {re.sub(r"[^a-z0-9]+", "-", m.lower()).strip("-") for m in re.findall(r"^## (.+)$", brief, re.M)}
    screens = json.loads((FIXTURE / "screen-map.json").read_text(encoding="utf-8"))["screens"]
    assert {r for s in screens for r in s["requirements"]} <= slugs
    assert {s["mockup"] for s in screens} == {p.name for p in (FIXTURE / "mockups").glob("*.html")}
    recipes = (SRC / "baseline" / "tour-baseline.ts").read_text(encoding="utf-8")
    for s in screens:
        assert re.search(rf'["\']?{re.escape(s["id"])}["\']?\s*:\s*async', recipes), f"no state-reaching recipe for screen {s['id']}"


@pytest.mark.covers("FR-01.06")
def test_answer_key_has_an_evaluator_per_item_and_only_s03_and_s09_are_soft():
    items = _items()
    assert {i for k, i, _ in items if k == "soft"} == {"S03", "S09"}
    ids = [i for _, i, _ in items]
    assert len(ids) == len(set(ids))
    spec = (E2E / "tests" / "e2e.spec.ts").read_text(encoding="utf-8")
    sources = "\n".join(p.read_text(encoding="utf-8") for p in [*SRC.glob("*.ts"), *(SRC / "baseline").glob("*.ts")]) + "\n" + spec
    for item in ids:
        assert re.search(rf'["\']{item}["\']', sources), f"no harness module records {item}"
    # the baseline items B01.. are recorded only by src/baseline/, so a rename there cannot leave one unevaluated
    baseline = "\n".join(p.read_text(encoding="utf-8") for p in (SRC / "baseline").glob("*.ts"))
    for item in [i for i in ids if i.startswith("B")]:
        assert re.search(rf'["\']{item}["\']', baseline), f"{item} is not recorded in src/baseline/"


@pytest.mark.covers("FR-01.06")
def test_harness_selects_the_fixture_by_name_and_leaves_the_other_two_alone():
    fixture_ts = (SRC / "fixture.ts").read_text(encoding="utf-8")
    assert 'BASELINE_FIXTURE_NAME = "social-engagement-baseline"' in fixture_ts
    assert 'FIXTURE_NAME = "social-engagement-board"' in fixture_ts and 'REAL_FIXTURE_NAME = "social-engagement-real"' in fixture_ts
    spec = (E2E / "tests" / "e2e.spec.ts").read_text(encoding="utf-8")
    assert "FIXTURE_NAME === BASELINE_FIXTURE_NAME" in spec and "runBaselineSuite" in spec and "recordFixtureApproval" in spec
    assert "checklist.describe(" in spec, "the report must print which checklist ran"
    # the real-skill variant keeps its own wiring
    variant_ts = (SRC / "variant.ts").read_text(encoding="utf-8")
    assert "masterDetailVariant" in variant_ts and "REAL_FIXTURE_NAME" in variant_ts


@pytest.mark.covers("FR-01.06")
def test_recorded_index_maps_every_request_to_an_existing_file():
    rec = FIXTURE / "seed" / "recorded"
    index = json.loads((rec / "index.json").read_text(encoding="utf-8"))
    assert {r["service"] for r in index["routes"]} == {"syften", "apify", "hn_algolia"}
    for route in index["routes"]:
        assert (rec / route["file"]).exists(), route
    synthetic = json.loads((FIXTURE / "seed" / "agent" / "run-synthetic.json").read_text(encoding="utf-8"))
    assert len(synthetic["items"]) == 11


@pytest.mark.covers("FR-01.06")
def test_every_api_route_the_checks_call_is_documented_in_brief_md():
    brief = (FIXTURE / "brief.md").read_text(encoding="utf-8")
    called = set()
    for p in (SRC / "baseline").glob("checks-*.ts"):
        called |= set(re.findall(r'"(/api/[a-z_/]+)', p.read_text(encoding="utf-8")))
    called -= {"/api/nope", "/api/feedback/fb_nope/resolve", "/api/threads/"}
    for route in called:
        assert route.rstrip("/") in brief, f"{route} is called by the harness but not documented in brief.md"
