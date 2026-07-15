"""TT1 collector tests — ``test_links.build_manifest`` over the traceability fixtures.

RED before TT1 (``build_manifest`` did not exist); green after. AC1 three-runner
FR→layer map == frozen golden; AC2 describe-tag propagation + multi-tag + malformed
tolerated; AC3 untagged bucket + orphan; AC4 v2-schema validity + update_compliance wiring.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts.lib.collectors.test_links import build_manifest  # noqa: E402

_LIB = _HERE.parent / "scripts" / "lib"
_FIX = _HERE / "fixtures" / "traceability"
_APP = _FIX / "mini_repos" / "app"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("rel_path,expected", [
    ("tests/test_auth.py", "unit"),
    ("unit/orders.test.ts", "unit"),
    ("tests/integration/test_orders_db.py", "integration"),
    ("integration-tests/test_fanout.py", "integration"),          # top-level integration-tests dir
    ("src/orders.integration.test.ts", "integration"),            # .integration.test.* filename
    ("e2e/auth.spec.ts", "e2e"),
    ("tests/checkout.spec.ts", "e2e"),                            # Playwright .spec convention
])
def test_layer_detection(rel_path, expected):
    from scripts.lib.collectors._test_links_io import detect_layer
    assert detect_layer(rel_path) == expected


@pytest.fixture(scope="module")
def validator() -> jsonschema.Draft202012Validator:
    schema = _load(_LIB / "traceability_schema.json")
    return jsonschema.Draft202012Validator(schema)


@pytest.fixture(scope="module")
def app_manifest() -> dict:
    evidence = _load(_FIX / "evidence" / "evidence_index.json")["results"]
    return build_manifest(
        _APP,
        spec_files=[_APP / "spec.md"],
        test_roots=[_APP],
        evidence=evidence,
        enumerate_untagged=True,
        generated_at="2026-07-15T00:00:00+00:00",
        source_commit="1" * 40,
    )


def _strip_spec_path(reqs: dict) -> dict:
    # spec_path is rooted at project_root (here "spec.md"); the frozen golden roots it at
    # the fixture package ("mini_repos/app/spec.md"). Everything else is the answer key.
    out = {}
    for key, req in reqs.items():
        node = dict(req)
        node.pop("spec_path")
        out[key] = node
    return out


# --- AC4: schema validity ------------------------------------------------

def test_manifest_validates_against_v2_schema(app_manifest, validator):
    errors = list(validator.iter_errors(app_manifest))
    assert not errors, errors
    assert app_manifest["schema_version"] == 2
    assert app_manifest["collector_version"].startswith("test_links/")
    assert app_manifest["spec_hash"].startswith("sha256:")


# --- AC1: golden answer key (three runners, per-layer join) --------------

def test_manifest_requirements_match_golden(app_manifest):
    golden = _load(_FIX / "golden" / "manifest.json")
    assert _strip_spec_path(app_manifest["requirements"]) == _strip_spec_path(golden["requirements"])


def test_spec_path_is_project_root_relative_posix(app_manifest):
    # Pin the rooting directly (not just normalized away in the snapshot): spec_path is
    # POSIX + relative to the project_root the collector was pointed at (here _APP).
    for req in app_manifest["requirements"].values():
        assert req["spec_path"] == "spec.md"
        assert "\\" not in req["spec_path"]


def test_manifest_orphans_invalid_untagged_match_golden(app_manifest):
    golden = _load(_FIX / "golden" / "manifest.json")
    assert app_manifest["orphans"] == golden["orphans"]
    assert app_manifest["invalid_tags"] == golden["invalid_tags"]
    assert app_manifest["untagged_tests"] == golden["untagged_tests"]


def test_all_three_runners_and_layers_represented(app_manifest):
    sources, layers = set(), set()
    for req in app_manifest["requirements"].values():
        for layer, links in req["tests"].items():
            for link in links:
                sources.add(link["tag_source"])
                layers.add(layer)
    # pytest marker + Playwright native tag + Vitest covers-comment + title-suffix
    assert {"pytest_marker", "native_tag", "covers_comment", "title_suffix"} <= sources
    assert {"unit", "integration", "e2e"} <= layers


# --- AC3: skipped != covered, untagged bucket, orphan --------------------

def test_skipped_e2e_is_missing_not_covered(app_manifest):
    fr = app_manifest["requirements"]["app::FR-03.01"]
    assert fr["coverage"]["e2e"] == "MISSING"          # its only e2e test is skipped (R1)
    assert fr["coverage"]["unit"] == "ok"
    assert fr["tests"]["e2e"][0]["status"] == "skipped"


def test_untagged_test_lands_in_bucket(app_manifest):
    assert "tests/test_auth.py::test_health_endpoint" in app_manifest["untagged_tests"]
    # a malformed-tagged test is NOT untagged (it is a hygiene finding, not silent)
    assert not any("test_sign_in_locale" in t for t in app_manifest["untagged_tests"])


def test_removed_fr_test_is_a_confirmed_orphan(app_manifest):
    orphans = app_manifest["orphans"]
    assert len(orphans) == 1
    assert orphans[0]["tagged_fr"] == "FR-03.09"
    assert orphans[0]["reason"] == "fr_removed"
    assert orphans[0]["category"] == "confirmed_orphan"
    # the removed FR keeps no live tests (they belong in orphans, not coverage)
    assert app_manifest["requirements"]["app::FR-03.09"]["tests"] == {}


# --- AC2: suite propagation + multi-tag + malformed tolerated ------------

_SUITE_SPEC = """# Spec
## Functional Requirements
| FR | Description | Priority | Layers |
|----|-------------|----------|--------|
| FR-05.01 | Widget renders | Must | unit |
| FR-05.02 | Extra behavior | Must | unit |
"""

_SUITE_TESTS = """import { describe, it } from 'vitest';

describe('widget suite', { tag: ['@FR-05.01'] }, () => {
  it('renders default', () => {});
  it('renders with props @FR-05.02', () => {});
});

it('malformed tolerated @FR-5.1', () => {});
"""


def _by_id(manifest: dict, fr_id: str) -> dict:
    for req in manifest["requirements"].values():
        if req["id"] == fr_id:
            return req
    raise AssertionError(fr_id)


@pytest.fixture(scope="module")
def suite_manifest(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("suite")
    (root / "spec.md").write_text(_SUITE_SPEC, encoding="utf-8")
    unit = root / "unit"
    unit.mkdir()
    (unit / "widget.test.ts").write_text(_SUITE_TESTS, encoding="utf-8")
    return build_manifest(
        root, spec_files=[root / "spec.md"], test_roots=[root],
        evidence={}, enumerate_untagged=True,
    )


def test_describe_level_tag_propagates_to_every_inner_test(suite_manifest, validator):
    assert not list(validator.iter_errors(suite_manifest))
    unit_links = _by_id(suite_manifest, "FR-05.01")["tests"].get("unit", [])
    paths = {link["path"] for link in unit_links}
    assert "unit/widget.test.ts::renders default" in paths
    assert "unit/widget.test.ts::renders with props @FR-05.02" in paths


def test_multiple_tags_per_test(suite_manifest):
    # 'renders with props' carries BOTH the suite tag FR-05.01 and its own FR-05.02.
    fr2_unit = _by_id(suite_manifest, "FR-05.02")["tests"].get("unit", [])
    assert any("renders with props" in link["path"] for link in fr2_unit)


def test_malformed_tag_is_recorded_not_crashed(suite_manifest):
    raws = {t["raw"] for t in suite_manifest["invalid_tags"]}
    assert "@FR-5.1" in raws


_MULTILINE_TESTS = """import { describe, it } from 'vitest';

describe('outer suite', { tag: ['@FR-05.01'] },
  () => {
    it('wrapped signature still inherits', () => {});
    describe('inner suite', { tag: ['@FR-05.02'] }, () => {
      it('inherits both outer and inner', () => {});
    });
  });
"""


@pytest.fixture(scope="module")
def multiline_manifest(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("multiline")
    (root / "spec.md").write_text(_SUITE_SPEC, encoding="utf-8")
    unit = root / "unit"
    unit.mkdir()
    (unit / "wrapped.test.ts").write_text(_MULTILINE_TESTS, encoding="utf-8")
    return build_manifest(
        root, spec_files=[root / "spec.md"], test_roots=[root],
        evidence={}, enumerate_untagged=True,
    )


def test_multiline_describe_signature_still_propagates(multiline_manifest):
    # A Prettier-wrapped describe whose callback `{` is on the NEXT line still tags
    # its inner tests (the entered-flag guard against an eager pop).
    fr1_unit = _by_id(multiline_manifest, "FR-05.01")["tests"].get("unit", [])
    assert any("wrapped signature still inherits" in link["path"] for link in fr1_unit)


def test_nested_describes_both_apply(multiline_manifest):
    # A test in a nested describe inherits BOTH the outer and inner suite tags.
    inner = "unit/wrapped.test.ts::inherits both outer and inner"
    fr1 = {link["path"] for link in _by_id(multiline_manifest, "FR-05.01")["tests"].get("unit", [])}
    fr2 = {link["path"] for link in _by_id(multiline_manifest, "FR-05.02")["tests"].get("unit", [])}
    assert inner in fr1 and inner in fr2


# --- AC4: generate_file + update_compliance wiring -----------------------

def test_generate_file_writes_valid_manifest(tmp_path, validator):
    # A spec + a tagged test under a conventional root ("tests/") — generate_file
    # writes the manifest, it validates, and the FR + its link are present.
    split = tmp_path / ".shipwright" / "planning" / "01-demo"
    split.mkdir(parents=True)
    (split / "spec.md").write_text(
        "# Spec\n## Functional Requirements\n"
        "| FR | Description | Priority | Layers |\n"
        "|----|-------------|----------|--------|\n"
        "| FR-07.01 | Health check | Must | unit |\n",
        encoding="utf-8",
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_health.py").write_text(
        'import pytest\n\n@pytest.mark.covers("FR-07.01")\n'
        "def test_health():\n    assert True\n",
        encoding="utf-8",
    )
    # A test OUTSIDE the conventional roots (repo root) is intentionally NOT scanned
    # by generate_file — comprehensive discovery is the backfill engine's job (TT6/TT8).
    (tmp_path / "stray.test.ts").write_text("it('stray @FR-07.01', () => {});\n", encoding="utf-8")

    from scripts.lib.collectors.test_links import generate_file
    out = generate_file(tmp_path)
    assert out.exists()
    manifest = _load(out)
    assert not list(validator.iter_errors(manifest))
    fr = manifest["requirements"]["01-demo::FR-07.01"]
    assert any("tests/test_health.py::test_health" == link["path"] for link in fr["tests"]["unit"])
    # boundary: the stray root-level test is not scanned (bounded discovery, documented)
    assert not any("stray" in u for u in manifest["untagged_tests"])


def test_update_compliance_iterate_phase_emits_manifest(tmp_path):
    # AC4: the manifest regenerates through the real update_compliance CLI wiring.
    (tmp_path / ".shipwright" / "compliance").mkdir(parents=True)
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True)
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "pipeline": []}), encoding="utf-8",
    )
    import subprocess
    script = _HERE.parent / "scripts" / "tools" / "update_compliance.py"
    result = subprocess.run(
        [sys.executable, str(script), "--project-root", str(tmp_path), "--phase", "iterate"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    names = {Path(r).name for r in payload.get("updated_reports", [])}
    assert "test-traceability.json" in names
    assert (tmp_path / ".shipwright" / "compliance" / "test-traceability.json").exists()
