"""Traceability contract + fixture-package smoke tests (P1 AC1 + AC3).

AC1 — the manifest v2 JSON Schema + golden example/manifest validate; malformed
instances are rejected. AC3 — every fixture class loads (mini-repo, base/head
diffs incl. refactor, execution evidence incl. a skipped sample, the record/replay
LLM adapter, predeclared decisions, golden snapshots), each with a smoke test.

Runs in the compliance plugin env (jsonschema is a declared dependency).
"""

from __future__ import annotations

import json
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

import jsonschema
import pytest

_HERE = Path(__file__).resolve().parent
_LIB = _HERE.parent / "scripts" / "lib"
_SCHEMA_PATH = _LIB / "traceability_schema.json"
_EXAMPLE_PATH = _LIB / "traceability_schema.example.json"
_FIX = _HERE / "fixtures" / "traceability"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schema() -> dict:
    return _load(_SCHEMA_PATH)


@pytest.fixture(scope="module")
def validator(schema) -> jsonschema.Draft202012Validator:
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


# --- AC1: schema + goldens validate --------------------------------------

def test_schema_is_valid_draft2020(schema):
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema["properties"]["schema_version"]["const"] == 2


def test_golden_example_validates(validator):
    assert not list(validator.iter_errors(_load(_EXAMPLE_PATH)))


def test_golden_manifest_validates(validator):
    assert not list(validator.iter_errors(_load(_FIX / "golden" / "manifest.json")))


def test_schema_rejects_malformed(validator):
    good = _load(_EXAMPLE_PATH)

    bad_version = json.loads(json.dumps(good))
    bad_version["schema_version"] = 1
    assert list(validator.iter_errors(bad_version))

    bad_id = json.loads(json.dumps(good))
    bad_id["requirements"]["01-adopted::FR-01.03"]["id"] = "FR-1.3"
    assert list(validator.iter_errors(bad_id))

    bad_exec = json.loads(json.dumps(good))
    bad_exec["requirements"]["01-adopted::FR-01.03"]["tests"]["unit"][0]["executed"] = "passed"
    assert list(validator.iter_errors(bad_exec))

    extra = json.loads(json.dumps(good))
    extra["unexpected"] = True
    assert list(validator.iter_errors(extra))


def test_schema_enforces_skipped_not_covered(validator):
    # coverage 'ok' with a skipped/not_run test at that layer MUST fail (R1, structural).
    bad = _load(_FIX / "golden" / "manifest.json")
    bad["requirements"]["app::FR-03.01"]["coverage"]["e2e"] = "ok"   # its e2e is skipped/not_run
    assert list(validator.iter_errors(bad))


def test_schema_enforces_removed_has_no_live_tests(validator):
    # a removed FR keeping live tests MUST fail (its tests belong in orphans[]).
    bad = _load(_FIX / "golden" / "manifest.json")
    bad["requirements"]["app::FR-03.09"]["tests"] = {
        "e2e": [{
            "id": "x", "path": "x::y", "layer": "e2e",
            "status": "enabled", "executed": "pass", "tag_source": "native_tag",
        }]
    }
    assert list(validator.iter_errors(bad))


def test_schema_requires_coverage_for_every_required_layer(validator):
    # a required layer cannot be silently omitted from coverage.
    bad = _load(_FIX / "golden" / "manifest.json")
    del bad["requirements"]["app::FR-03.02"]["coverage"]["e2e"]   # FR-03.02 requires e2e
    assert list(validator.iter_errors(bad))


def test_schema_enforces_test_link_layer_matches_its_group(validator):
    # unit coverage cannot be claimed from a test link whose own layer is e2e.
    bad = _load(_FIX / "golden" / "manifest.json")
    bad["requirements"]["app::FR-03.03"]["tests"]["unit"][0]["layer"] = "e2e"
    assert list(validator.iter_errors(bad))


def test_schema_orphan_null_fr_rules(validator):
    good = _load(_FIX / "golden" / "manifest.json")
    # unmapped orphan with null tagged_fr is valid
    ok = json.loads(json.dumps(good))
    ok["orphans"].append({
        "test": "e2e/u.spec.ts::x", "tagged_fr": None, "reason": "fr_absent", "category": "unmapped",
    })
    assert not list(validator.iter_errors(ok))
    # confirmed_orphan with null tagged_fr MUST fail
    bad = json.loads(json.dumps(good))
    bad["orphans"][0]["tagged_fr"] = None      # orphans[0] is a confirmed_orphan
    assert list(validator.iter_errors(bad))


# --- AC3: fixture package loads ------------------------------------------

def test_minirepo_loads():
    spec = (_FIX / "mini_repos" / "app" / "spec.md").read_text(encoding="utf-8")
    assert "FR-03.01" in spec and "## Removed Requirements" in spec and "FR-03.09" in spec
    for rel in (
        "tests/test_auth.py",
        "tests/integration/test_orders_db.py",
        "e2e/auth.spec.ts",
        "e2e/dashboard.spec.ts",
        "e2e/legacy.spec.ts",
        "unit/orders.test.ts",
    ):
        assert (_FIX / "mini_repos" / "app" / rel).is_file()


def test_diffs_load_with_expected_verdicts():
    verdicts = {}
    for scenario in ("removal", "behavior_change", "refactor"):
        base = _FIX / "diffs" / scenario / "base"
        head = _FIX / "diffs" / scenario / "head"
        patch = _FIX / "diffs" / scenario / "change.patch"
        expected = _load(_FIX / "diffs" / scenario / "expected.json")
        assert base.is_dir() and head.is_dir()
        assert patch.is_file() and patch.read_text(encoding="utf-8").strip()
        verdicts[scenario] = expected["expected_blocked"]
    assert verdicts["removal"] is True           # removal -> orphan gate BLOCKS
    assert verdicts["refactor"] is False         # pure refactor must NOT block
    assert verdicts["behavior_change"] is False  # covered at the required layer

    # The expected verdicts are tied to the actual base/head content, not just asserted:
    rm_base = (_FIX / "diffs" / "removal" / "base" / "spec.md").read_text(encoding="utf-8")
    rm_head = (_FIX / "diffs" / "removal" / "head" / "spec.md").read_text(encoding="utf-8")
    assert "## Removed Requirements" not in rm_base and "FR-03.03" in rm_base
    assert "## Removed Requirements" in rm_head and "FR-03.03" in rm_head   # moved to removed

    bc_base = (_FIX / "diffs" / "behavior_change" / "base" / "spec.md").read_text(encoding="utf-8")
    bc_head = (_FIX / "diffs" / "behavior_change" / "head" / "spec.md").read_text(encoding="utf-8")
    assert bc_base != bc_head and "FR-03.02" in bc_base and "FR-03.02" in bc_head  # a real spec/AC delta

    # A pure refactor touches source only — no spec.md, so no behavior-change signal.
    refactor_files = {p.name for p in (_FIX / "diffs" / "refactor").rglob("*") if p.is_file()}
    assert "spec.md" not in refactor_files and "orders.py" in refactor_files

    # The referenced base-linked / required-layer tests actually EXIST in both trees,
    # so the scenarios are self-contained answer keys for a base/head gate (R3).
    removal_expected = _load(_FIX / "diffs" / "removal" / "expected.json")
    for tree in ("base", "head"):
        for linked in removal_expected["base_linked_tests"]:
            src = linked.split("::")[0]
            assert (_FIX / "diffs" / "removal" / tree / src).is_file(), (tree, src)
        # behavior-change keeps its required-layer test present + enabled in both trees
        assert (_FIX / "diffs" / "behavior_change" / tree / "e2e" / "dashboard.spec.ts").is_file()


def test_evidence_loads_including_skipped():
    ET.parse(_FIX / "evidence" / "junit.xml")            # well-formed XML
    playwright = _load(_FIX / "evidence" / "playwright.json")
    _load(_FIX / "evidence" / "vitest.json")
    index = _load(_FIX / "evidence" / "evidence_index.json")["results"]
    skipped = index["e2e/auth.spec.ts::signs in and lands on dashboard"]
    assert skipped["status"] == "skipped" and skipped["executed"] == "not_run"
    # no skipped/not_run test may ever read as an executed pass
    assert all(
        not (r["status"] == "skipped" and r["executed"] == "pass")
        for r in index.values()
    )

    # The normalized index must agree with the RAW Playwright report, so a raw
    # status change cannot silently diverge from the answer key (R1 boundary).
    raw_status = {
        spec["title"]: spec["tests"][0]["status"]
        for suite in playwright["suites"]
        for spec in suite["specs"]
    }
    assert raw_status["signs in and lands on dashboard"] == "skipped"
    for title, raw in raw_status.items():
        norm = index[f"e2e/{_pw_file(playwright, title)}::{title}"]
        if raw == "skipped":
            assert norm["executed"] == "not_run"     # skipped raw -> never a pass
        else:
            assert norm["executed"] == "pass"


def _pw_file(playwright: dict, title: str) -> str:
    for suite in playwright["suites"]:
        for spec in suite["specs"]:
            if spec["title"] == title:
                return suite["file"].split("/")[-1]
    raise AssertionError(title)


def test_predeclared_decisions_load():
    adopt = _load(_FIX / "decisions" / "adopt_ambiguity.json")
    retire = _load(_FIX / "decisions" / "orphan_retirement.json")
    assert adopt["answers"]["app::FR-03.02"]["decision"] == "inferred_legacy"
    # an unmapped orphan is filed for review, never auto-deleted (R4/§7)
    unmapped = retire["choices"]["e2e/unmapped.spec.ts::renders a legacy widget"]
    assert unmapped["decision"] == "file_triage"


def _markers(pyproject: Path) -> list[str]:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return data["tool"]["pytest"]["ini_options"]["markers"]


def test_covers_marker_registered():
    # Spec D1: the pytest `covers` marker must be registered so @pytest.mark.covers
    # is a first-class marker, not an unknown-mark warning. Registered in the
    # compliance plugin (its testpaths) AND the root (shared / integration-tests).
    repo_root = _HERE.parents[2]
    for pyproject in (_HERE.parent / "pyproject.toml", repo_root / "pyproject.toml"):
        assert any(m.startswith("covers:") for m in _markers(pyproject)), pyproject


def test_golden_report_snapshot_present():
    report = (_FIX / "golden" / "report.md").read_text(encoding="utf-8")
    assert "MISSING" in report and "confirmed_orphan" in report


def test_catalog_paths_all_resolve():
    catalog = _load(_FIX / "catalog.json")
    for rel in catalog["contracts"].values():
        assert (_FIX / rel).resolve().is_file(), rel
    for entry in catalog["fixtures"]:
        paths = entry["path"] if isinstance(entry["path"], list) else [entry["path"]]
        for p in paths:
            assert (_FIX / p).exists(), p
    assert set(catalog["key_properties"]) == {
        "skipped_not_covered", "removal_flagged", "refactor_not_blocked", "golden_correct",
    }
