"""TT-EV execution-evidence JOIN + waiver + finalization-wiring tests (Spec §11 R1).

The reader-core half lives in ``test_execution_evidence.py``. This half pins the
consequences of the evidence: AC2 coverage[layer]=ok requires enabled+executed=pass
(a green-but-skipped required-layer test yields MISSING — the core R1 regression);
AC3 a missing evidence file resolves to not_run (fail-closed, never pass) and the
expiring waiver is honored while valid, fails when expired; plus the fail-closed
finalization wiring (refresh_index is non-destructive, freshness-stamped).
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import date
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts.lib.collectors._execution_evidence_io import refresh_index  # noqa: E402
from scripts.lib.collectors.execution_evidence import (  # noqa: E402
    build_index,
    layer_satisfied,
    normalize_index,
    waiver_state,
)
from scripts.lib.collectors.test_links import _cov_status, build_manifest, generate_file  # noqa: E402

_FIX = _HERE / "fixtures" / "traceability"
_EV = _FIX / "evidence"
_APP = _FIX / "mini_repos" / "app"
_SKIPPED_E2E = "e2e/auth.spec.ts::signs in and lands on dashboard"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def raw_index() -> dict:
    return build_index(
        junit=(_EV / "junit.xml").read_text(encoding="utf-8"),
        playwright=_load(_EV / "playwright.json"),
        vitest=_load(_EV / "vitest.json"),
    )


@pytest.fixture(scope="module")
def manifest_from_raw(raw_index) -> dict:
    return build_manifest(
        _APP, spec_files=[_APP / "spec.md"], test_roots=[_APP],
        evidence=raw_index["results"], enumerate_untagged=True,
    )


# --- AC2: coverage[layer]=ok requires enabled + executed=pass (core R1) ------

def test_green_but_skipped_required_layer_is_MISSING_not_ok(manifest_from_raw):
    # THE regression this campaign exists to catch: FR-03.01's only e2e test is
    # skipped -> coverage.e2e MUST be MISSING even though the run was "green".
    fr = manifest_from_raw["requirements"]["app::FR-03.01"]
    assert fr["coverage"]["e2e"] == "MISSING"
    assert fr["coverage"]["unit"] == "ok"          # its unit test really passed
    assert fr["tests"]["e2e"][0]["executed"] == "not_run"


def test_executed_pass_required_layer_is_ok(manifest_from_raw):
    fr = manifest_from_raw["requirements"]["app::FR-03.02"]
    assert fr["coverage"]["e2e"] == "ok"           # dashboard e2e enabled + pass


@pytest.mark.parametrize("links,expected", [
    ([], "MISSING"),                                                     # no test at all
    ([{"status": "skipped", "executed": "not_run"}], "MISSING"),         # skipped != covered
    ([{"status": "enabled", "executed": "fail"}], "MISSING"),            # failing != covered
    ([{"status": "enabled", "executed": "not_run"}], "MISSING"),         # never run
    ([{"status": "quarantined", "executed": "pass"}], "MISSING"),        # quarantined != enabled
    ([{"status": "only", "executed": "pass"}], "MISSING"),               # a focused .only != enabled
    ([{"status": "enabled", "executed": "pass"}], "ok"),                 # the only ok case
    ([{"status": "skipped", "executed": "not_run"},
      {"status": "enabled", "executed": "pass"}], "ok"),                 # one real pass suffices
])
def test_cov_status_predicate_only_enabled_pass_is_ok(links, expected):
    assert _cov_status(links) == expected


# --- AC3: missing evidence is fail-closed not_run; expiring waiver -----------

def test_missing_evidence_file_resolves_not_run_never_pass():
    # No evidence at all -> every executed is not_run and no coverage is ok (R1
    # fail-closed: an absent evidence file is NEVER read as a pass).
    manifest = build_manifest(
        _APP, spec_files=[_APP / "spec.md"], test_roots=[_APP],
        evidence={}, enumerate_untagged=True,
    )
    for req in manifest["requirements"].values():
        for links in req["tests"].values():
            assert all(l["executed"] == "not_run" for l in links)
        assert "ok" not in req["coverage"].values()


def test_partial_evidence_omitting_a_required_test_stays_missing(raw_index):
    # A report that EXISTS but omits one tagged required-layer test (e.g. filtered
    # out) must leave that test not_run -> MISSING, never a stale/assumed pass.
    partial = {k: v for k, v in raw_index["results"].items()
               if k != "e2e/dashboard.spec.ts::dashboard shows live orders"}
    manifest = build_manifest(
        _APP, spec_files=[_APP / "spec.md"], test_roots=[_APP],
        evidence=partial, enumerate_untagged=True,
    )
    fr = manifest["requirements"]["app::FR-03.02"]
    assert fr["coverage"]["e2e"] == "MISSING"
    assert fr["tests"]["e2e"][0]["executed"] == "not_run"


_WAIVER = {
    "layer": "e2e", "reason": "no browser in the CI sandbox",
    "owner": "platform", "ticket": "SHIP-42", "expires": "2026-07-16",
}
_NOW = date(2026, 7, 15)


def test_waiver_valid_while_unexpired_expired_after():
    assert waiver_state(_WAIVER, now=_NOW) == "valid"                       # expires tomorrow
    assert waiver_state({**_WAIVER, "expires": "2026-07-14"}, now=_NOW) == "expired"


def test_incomplete_or_malformed_waiver_is_invalid_not_honored():
    assert waiver_state({"layer": "e2e", "expires": "2999-01-01"}, now=_NOW) == "invalid"
    assert waiver_state({**_WAIVER, "layer": "smoke"}, now=_NOW) == "invalid"
    assert waiver_state({**_WAIVER, "expires": "not-a-date"}, now=_NOW) == "invalid"


def test_layer_satisfied_honors_valid_waiver_fails_expired():
    skipped = [{"status": "skipped", "executed": "not_run"}]
    assert layer_satisfied(skipped, waiver=_WAIVER, now=_NOW) is True                     # honored
    assert layer_satisfied(skipped, waiver={**_WAIVER, "expires": "2026-07-14"}, now=_NOW) is False
    assert layer_satisfied(skipped) is False                                              # no waiver -> fail-closed
    assert layer_satisfied([{"status": "enabled", "executed": "pass"}]) is True           # a real pass needs no waiver


# --- finalization wiring: non-destructive + freshness-stamped ---------------

def test_refresh_index_noop_leaves_existing_index_untouched(tmp_path):
    idx = tmp_path / ".shipwright" / "compliance" / "test-evidence-index.json"
    idx.parent.mkdir(parents=True)
    payload = '{"schema_version": 2, "results": {"x::y": {"status": "enabled", "executed": "pass"}}}\n'
    idx.write_text(payload, encoding="utf-8")
    assert refresh_index(tmp_path) is None          # no raw reports -> non-destructive no-op
    assert idx.read_text(encoding="utf-8") == payload


def test_refresh_index_emits_and_stamps_freshness(tmp_path):
    drop = tmp_path / ".shipwright" / "compliance" / "evidence"
    drop.mkdir(parents=True)
    for name in ("junit.xml", "playwright.json", "vitest.json"):
        shutil.copy(_EV / name, drop / name)
    out = refresh_index(tmp_path)
    assert out is not None and out.is_file()
    index = _load(out)
    assert index["schema_version"] == 2
    assert index["results"][_SKIPPED_E2E]["executed"] == "not_run"
    assert index["generated_at"].endswith("Z")
    assert ".shipwright/compliance/evidence/junit.xml" in index["source_reports"]


def test_stale_index_is_not_trusted_when_no_fresh_reports(tmp_path):
    # A prior run's index marks a test pass, but THIS regen produced no raw report;
    # generate_file must fall back to not_run/MISSING, never self-report the stale
    # pass (review H1 — the AC3 fail-closed contract at the wiring level).
    split = tmp_path / ".shipwright" / "planning" / "01-demo"
    split.mkdir(parents=True)
    split.joinpath("spec.md").write_text(
        "# Spec\n## Functional Requirements\n| FR | Description | Priority | Layers |\n"
        "|----|-------------|----------|--------|\n| FR-08.01 | Health | Must | unit |\n",
        encoding="utf-8",
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    tests.joinpath("test_h.py").write_text(
        'import pytest\n\n@pytest.mark.covers("FR-08.01")\ndef test_h():\n    assert True\n',
        encoding="utf-8",
    )
    idx = tmp_path / ".shipwright" / "compliance" / "test-evidence-index.json"
    idx.parent.mkdir(parents=True)
    idx.write_text(json.dumps({"schema_version": 2, "results": {
        "tests/test_h.py::test_h": {"status": "enabled", "executed": "pass"},
    }}), encoding="utf-8")

    manifest = _load(generate_file(tmp_path))
    fr = manifest["requirements"]["01-demo::FR-08.01"]
    assert fr["coverage"]["unit"] == "MISSING"                 # stale pass NOT trusted
    assert fr["tests"]["unit"][0]["executed"] == "not_run"


def test_operator_waiver_survives_a_machine_results_refresh(tmp_path):
    drop = tmp_path / ".shipwright" / "compliance" / "evidence"
    drop.mkdir(parents=True)
    shutil.copy(_EV / "junit.xml", drop / "junit.xml")
    idx = tmp_path / ".shipwright" / "compliance" / "test-evidence-index.json"
    idx.parent.mkdir(parents=True, exist_ok=True)
    idx.write_text(json.dumps({"schema_version": 2, "results": {}, "waivers": [_WAIVER]}), encoding="utf-8")
    index = _load(refresh_index(tmp_path))
    assert index["waivers"] == [_WAIVER]      # operator policy carried forward, not dropped
    assert index["results"]                    # AND fresh machine results present


def test_normalize_index_preserves_waivers():
    raw = {"schema_version": 2,
           "results": {"a::b": {"status": "enabled", "executed": "pass"}},
           "waivers": [_WAIVER]}
    assert normalize_index(raw)["waivers"] == [_WAIVER]
