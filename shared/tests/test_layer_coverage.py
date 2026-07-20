"""Tests for the two enforcing F11 traceability gates (TT5, Spec §11 R2/R3).

Two tiers:

* Pure-core (synthetic manifests) — pins the false-green/false-red reasoning precisely:
  bare-tag-removal FAILs, collision ids stay ADVISORY (never a false-red), legacy
  provenance stays advisory, could-not-determine WARNs, a skipped test never satisfies.
* Collector-built (real ``build_manifest`` over on-disk base/head trees) — proves the
  gate composes with the TT1 collector end-to-end, keyed to the same stable ids the
  production regeneration uses (AC1/AC2/AC4).

The three P1 scenarios (removal / behaviour-change / refactor) are exercised through the
real collector so the answer key is the same pipeline production runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from tools.verifiers._layer_coverage_core import evaluate_cross_layer  # noqa: E402
from tools.verifiers._layer_coverage_regen import _load_collector  # noqa: E402
from tools.verifiers._layer_coverage_removal import evaluate_removal  # noqa: E402


# ---------------------------------------------------------------------------
# Collector-built helpers (real build_manifest over an on-disk namespace)
# ---------------------------------------------------------------------------


def _build(side: Path, spec: str, files: dict[str, str], evidence: dict | None = None) -> dict:
    """Build a manifest for one side laid out under a stable ``app`` namespace so base and
    head keys align (production archives both to identical repo paths)."""
    tl, _io, _evio = _load_collector()
    app = side / "app"
    app.mkdir(parents=True, exist_ok=True)
    (app / "spec.md").write_text(spec, encoding="utf-8")
    for rel, content in files.items():
        p = app / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tl.build_manifest(app, spec_files=[app / "spec.md"], test_roots=[app],
                             evidence=evidence or {})


_SPEC_ACTIVE = (
    "# Spec\n\n## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
    "| FR-03.03 | Persist an order | Should | integration |\n"
)
_SPEC_REMOVED = (
    "# Spec\n\n## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n\n"
    "## Removed Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
    "| FR-03.03 | Persist an order | Should | integration |\n"
)
_TEST_TAGGED = (
    "import pytest\n\n\n@pytest.mark.covers(\"FR-03.03\")\n"
    "def test_persist():\n    assert True\n"
)
_TEST_UNTAGGED = "def test_persist():\n    assert True\n"
_TEST_RETARGET = (
    "import pytest\n\n\n@pytest.mark.covers(\"FR-03.05\")\n"
    "def test_persist():\n    assert True\n"
)
_TESTPATH = "tests/integration/test_orders.py"


# ---------------------------------------------------------------------------
# AC1 — removal → orphan (three pinned cases)
# ---------------------------------------------------------------------------


def test_removal_still_tagged_fails(tmp_path):
    base = _build(tmp_path / "b", _SPEC_ACTIVE, {_TESTPATH: _TEST_TAGGED})
    head = _build(tmp_path / "h", _SPEC_REMOVED, {_TESTPATH: _TEST_TAGGED})
    v = evaluate_removal(base, head)
    assert v.removed_frs and v.any_fail
    assert "still tagged" in v.hard[0][2]


def test_removal_retarget_but_keeps_dead_tag_fails(tmp_path):
    # External-review MUST-FIX: a test that ADDS an active tag but KEEPS the removed FR's
    # dead tag is NOT a clean retarget — the lingering dead tag is a HARD finding.
    both = ("import pytest\n\n\n@pytest.mark.covers(\"FR-03.03\", \"FR-03.05\")\n"
            "def test_persist():\n    assert True\n")
    spec_head = _SPEC_REMOVED.replace(
        "|----|----|----|----|\n\n## Removed",
        "|----|----|----|----|\n"
        "| FR-03.05 | Persist v2 | Should | integration |\n\n## Removed",
        1,
    )
    base = _build(tmp_path / "b", _SPEC_ACTIVE, {_TESTPATH: _TEST_TAGGED})
    head = _build(tmp_path / "h", spec_head, {_TESTPATH: both})
    v = evaluate_removal(base, head)
    assert v.any_fail and "dead tag not removed" in v.hard[0][2]


def test_removal_bare_tag_removal_fails(tmp_path):
    # The @FR tag is stripped from an otherwise-unchanged test — it must NOT escape into
    # untagged_tests unnoticed; that is the exact stale-test-escape R3 makes a HARD finding.
    base = _build(tmp_path / "b", _SPEC_ACTIVE, {_TESTPATH: _TEST_TAGGED})
    head = _build(tmp_path / "h", _SPEC_REMOVED, {_TESTPATH: _TEST_UNTAGGED})
    v = evaluate_removal(base, head)
    assert v.any_fail
    assert "bare @FR tag removed" in v.hard[0][2]


def test_removal_retarget_passes(tmp_path):
    spec_head = _SPEC_REMOVED.replace(
        "|----|----|----|----|\n\n## Removed",
        "|----|----|----|----|\n"
        "| FR-03.05 | Persist v2 | Should | integration |\n\n## Removed",
        1,
    )
    base = _build(tmp_path / "b", _SPEC_ACTIVE, {_TESTPATH: _TEST_TAGGED})
    head = _build(tmp_path / "h", spec_head, {_TESTPATH: _TEST_RETARGET})
    v = evaluate_removal(base, head)
    assert v.removed_frs and not v.any_fail
    assert v.retired  # retargeted to a live FR


def test_removal_deleted_test_passes(tmp_path):
    base = _build(tmp_path / "b", _SPEC_ACTIVE, {_TESTPATH: _TEST_TAGGED})
    head = _build(tmp_path / "h", _SPEC_REMOVED, {})  # test file gone
    v = evaluate_removal(base, head)
    assert v.removed_frs and not v.any_fail


def test_removal_rename_plus_tag_strip_fails(tmp_path):
    # External-review MUST-FIX: a base-linked test MOVED to a new path AND stripped of its
    # tag must NOT read as "deleted" — with the git rename map it resurfaces untagged at the
    # new id and is a HARD escape. Base id: tests/integration/test_orders.py::test_persist.
    base = _build(tmp_path / "b", _SPEC_ACTIVE, {_TESTPATH: _TEST_TAGGED})
    head = _build(tmp_path / "h", _SPEC_REMOVED, {"tests/integration/test_moved.py": _TEST_UNTAGGED})
    rename = {"tests/integration/test_orders.py": "tests/integration/test_moved.py"}
    v = evaluate_removal(base, head, rename)
    assert v.any_fail and "escaped into untagged_tests" in v.hard[0][2]


def test_removal_function_rename_strip_same_file_fails(tmp_path):
    # External-review MUST-FIX: a test FUNCTION renamed + tag-stripped WITHIN a surviving
    # file (git sees no file rename) must not silently credit deletion. The file gains a
    # brand-new untagged test absent at base → HARD (fail-closed anti-escape).
    base = _build(tmp_path / "b", _SPEC_ACTIVE,
                  {"tests/test_x.py": _TEST_TAGGED.replace("test_persist", "test_old")})
    head = _build(tmp_path / "h", _SPEC_REMOVED,
                  {"tests/test_x.py": "def test_new():\n    assert True\n"})
    v = evaluate_removal(base, head)
    assert v.any_fail and "escape" in v.hard[0][2]


def test_removal_moved_untagged_same_name_fails_without_rename_map(tmp_path):
    # External-review MUST-FIX: a test moved to a DIFFERENT path + tag-stripped, where git's
    # -M missed the rename (empty rename_map) but the FUNCTION NAME is preserved, is caught by
    # the name-match escape check (a new untagged test with the same name absent at base).
    base = _build(tmp_path / "b", _SPEC_ACTIVE, {"tests/test_old.py": _TEST_TAGGED})
    head = _build(tmp_path / "h", _SPEC_REMOVED,
                  {"tests/sub/test_new.py": _TEST_UNTAGGED})  # moved dir, same fn name, untagged
    v = evaluate_removal(base, head)  # no rename_map
    assert v.any_fail and "escape" in v.hard[0][2]


def test_removal_moved_test_keeps_dead_tag_fails_without_rename_map(tmp_path):
    # External-review MUST-FIX: a test moved to a new path that KEEPS its @FR-03.03 tag is a
    # dead-tag orphan at head. Even when git's -M misses the rename (empty rename_map), the
    # git-diff-INDEPENDENT sweep over the regenerated head manifest's orphans catches it.
    old = _TEST_TAGGED.replace("test_persist", "test_x")
    base = _build(tmp_path / "b", _SPEC_ACTIVE, {"tests/test_old.py": old})
    head = _build(tmp_path / "h", _SPEC_REMOVED, {"tests/test_new.py": old})  # moved, tag kept
    v = evaluate_removal(base, head)  # no rename_map (git missed it)
    assert v.any_fail and "dead tag standing" in v.hard[0][2]


def test_removal_no_removed_fr_is_noop(tmp_path):
    base = _build(tmp_path / "b", _SPEC_ACTIVE, {_TESTPATH: _TEST_TAGGED})
    head = _build(tmp_path / "h", _SPEC_ACTIVE, {_TESTPATH: _TEST_TAGGED})
    v = evaluate_removal(base, head)
    assert not v.removed_frs and not v.any_fail


# ---------------------------------------------------------------------------
# AC2 — behaviour change → cross-layer (executed-passing)
# ---------------------------------------------------------------------------

_SPEC_E2E = (
    "# Spec\n\n## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
    "| FR-03.02 | Dashboard shows live orders | Must | e2e |\n"
)
_SPEC_E2E_CHANGED = _SPEC_E2E.replace("live orders", "live orders with running totals")
_E2E_TEST = (
    "import { test } from '@playwright/test';\n"
    "test('dashboard shows orders', { tag: ['@FR-03.02'] }, async () => {});\n"
)
_E2E_ID = "e2e/dashboard.spec.ts::dashboard shows orders"


def test_cross_layer_executed_passing_is_green(tmp_path):
    ev = {_E2E_ID: {"status": "enabled", "executed": "pass", "runner": "playwright"}}
    base = _build(tmp_path / "b", _SPEC_E2E, {"e2e/dashboard.spec.ts": _E2E_TEST})
    head = _build(tmp_path / "h", _SPEC_E2E_CHANGED, {"e2e/dashboard.spec.ts": _E2E_TEST}, ev)
    v = evaluate_cross_layer(base, head)
    assert v.changed_keys and not v.any_fail and not v.advisory


def test_cross_layer_skipped_test_fails(tmp_path):
    # R1: enabled-but-skipped (not executed=pass) is MISSING, never a pass.
    ev = {_E2E_ID: {"status": "skipped", "executed": "not_run", "runner": "playwright"}}
    base = _build(tmp_path / "b", _SPEC_E2E, {"e2e/dashboard.spec.ts": _E2E_TEST})
    head = _build(tmp_path / "h", _SPEC_E2E_CHANGED, {"e2e/dashboard.spec.ts": _E2E_TEST}, ev)
    v = evaluate_cross_layer(base, head)
    assert v.any_fail and v.hard[0].layer == "e2e" and v.hard[0].source == "explicit"


def test_cross_layer_no_evidence_fails(tmp_path):
    base = _build(tmp_path / "b", _SPEC_E2E, {"e2e/dashboard.spec.ts": _E2E_TEST})
    head = _build(tmp_path / "h", _SPEC_E2E_CHANGED, {"e2e/dashboard.spec.ts": _E2E_TEST}, {})
    v = evaluate_cross_layer(base, head)
    assert v.any_fail  # no execution evidence → fail-closed MISSING


_SPEC_TWO_LAYER = (
    "# Spec\n\n## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
    "| FR-03.02 | Dashboard shows live orders | Must | unit, e2e |\n"
)
_SPEC_TWO_LAYER_CHANGED = _SPEC_TWO_LAYER.replace("live orders", "live orders with totals")
_UNIT_TEST = (
    "import pytest\n\n\n@pytest.mark.covers(\"FR-03.02\")\n"
    "def test_orders_unit():\n    assert True\n"
)
_UNIT_ID = "tests/test_orders_unit.py::test_orders_unit"


def test_cross_layer_requires_all_layers_missing_one_blocks(tmp_path):
    # AC2: an FR requiring [unit, e2e] must be executed-passing at BOTH. Only unit passing
    # (e2e absent) → the e2e layer blocks (a per-layer check that can't stop at the first).
    ev = {_UNIT_ID: {"status": "enabled", "executed": "pass", "runner": "pytest"}}
    files = {"tests/test_orders_unit.py": _UNIT_TEST, "e2e/dashboard.spec.ts": _E2E_TEST}
    base = _build(tmp_path / "b", _SPEC_TWO_LAYER, files)
    head = _build(tmp_path / "h", _SPEC_TWO_LAYER_CHANGED, files, ev)
    v = evaluate_cross_layer(base, head)
    assert v.any_fail and {g.layer for g in v.hard} == {"e2e"}


def test_cross_layer_requires_all_layers_both_passing_is_green(tmp_path):
    ev = {
        _UNIT_ID: {"status": "enabled", "executed": "pass", "runner": "pytest"},
        _E2E_ID: {"status": "enabled", "executed": "pass", "runner": "playwright"},
    }
    files = {"tests/test_orders_unit.py": _UNIT_TEST, "e2e/dashboard.spec.ts": _E2E_TEST}
    base = _build(tmp_path / "b", _SPEC_TWO_LAYER, files)
    head = _build(tmp_path / "h", _SPEC_TWO_LAYER_CHANGED, files, ev)
    v = evaluate_cross_layer(base, head)
    assert v.changed_keys and not v.any_fail and not v.advisory


def test_cross_layer_pure_refactor_does_not_fire(tmp_path):
    # Identical spec both sides (source changed elsewhere) → no changed FR → no gate.
    base = _build(tmp_path / "b", _SPEC_E2E, {"e2e/dashboard.spec.ts": _E2E_TEST})
    head = _build(tmp_path / "h", _SPEC_E2E, {"e2e/dashboard.spec.ts": _E2E_TEST}, {})
    v = evaluate_cross_layer(base, head)
    assert not v.changed_keys and not v.any_fail and not v.could_not_determine


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
