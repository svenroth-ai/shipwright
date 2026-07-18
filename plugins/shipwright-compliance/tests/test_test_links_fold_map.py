"""End-to-end: the TT1 collector resolves a tagged FR through the ``## FR-Fold-Map``.

The defect these pin: a spec clean-up that folds fine-grained FRs into capability FRs
used to turn every test tagged with a folded id into a ``confirmed_orphan``, failing
D-orphan (shipwright-webui #287 → 419 orphans). A tag on a folded id must now count as
coverage of the surviving FR, while everything that CANNOT be safely resolved still
orphans exactly as before.

@FR-01.10
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts.audit._group_d_traceability import check_orphan  # noqa: E402
from scripts.lib.collectors.test_links import build_manifest  # noqa: E402

_SCHEMA = json.loads(
    (_HERE.parent / "scripts" / "lib" / "traceability_schema.json").read_text(encoding="utf-8"))

_SPEC_HEAD = """# Spec

## Functional Requirements

| FR | Description | Priority | Layers |
|----|-------------|----------|--------|
| FR-01.28 | Embedded terminal | Must | unit |
| FR-01.30 | Something else | Must | unit |
"""

_FOLD_SECTION = """
## FR-Fold-Map

| Folded ID | → Survivor | Reason | Was |
|-----------|-----------|--------|-----|
{rows}
"""


def _repo(tmp_path: Path, *, fold_rows: str | None = None, tests: str) -> Path:
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    spec = _SPEC_HEAD
    if fold_rows is not None:
        spec += _FOLD_SECTION.format(rows=fold_rows)
    (root / "spec.md").write_text(spec, encoding="utf-8")
    (root / "tests" / "test_thing.py").write_text(tests, encoding="utf-8")
    return root


def _build(root: Path) -> dict:
    return build_manifest(
        root, spec_files=[root / "spec.md"], test_roots=[root],
        evidence={}, enumerate_untagged=False,
        generated_at="2026-07-18T00:00:00+00:00", source_commit="a" * 40,
    )


def _links(manifest: dict, fr: str) -> list[dict]:
    for node in manifest["requirements"].values():
        if node["id"] == fr:
            return [l for links in (node.get("tests") or {}).values() for l in links]
    return []


_TAGGED_FOLDED = '''import pytest


@pytest.mark.covers("FR-01.44")
def test_terminal_look():
    assert True
'''


# --------------------------------------------------------------------------
# AC1 — a folded tag becomes coverage of the survivor
# --------------------------------------------------------------------------


def test_folded_tag_binds_to_survivor_and_produces_no_orphan(tmp_path):
    m = _build(_repo(tmp_path, fold_rows="| `FR-01.44` | `FR-01.28` | delta | look |",
                     tests=_TAGGED_FOLDED))
    assert m["orphans"] == []
    links = _links(m, "FR-01.28")
    assert len(links) == 1
    assert links[0]["resolved_from"] == "FR-01.44"
    assert m["fold_map"] == {"FR-01.44": "FR-01.28"}


def test_D_orphan_passes_on_a_fold_resolved_tag(tmp_path):
    """The regression in one assertion: this manifest used to FAIL D-orphan."""
    m = _build(_repo(tmp_path, fold_rows="| `FR-01.44` | `FR-01.28` | delta | look |",
                     tests=_TAGGED_FOLDED))
    status, _, detail, _, _ = check_orphan(m)
    assert status == "pass", detail


def test_without_the_fold_map_the_same_tag_still_orphans(tmp_path):
    """Control: the rescue comes from the fold-map, not from having relaxed the rule."""
    m = _build(_repo(tmp_path, fold_rows=None, tests=_TAGGED_FOLDED))
    assert [o["category"] for o in m["orphans"]] == ["confirmed_orphan"]
    assert check_orphan(m)[0] == "fail"


# --------------------------------------------------------------------------
# AC2 — fallback, never override
# --------------------------------------------------------------------------


def test_a_live_fr_tag_is_not_redirected_by_a_fold_map(tmp_path):
    """FR-01.30 is active AND folded; the live row must win and keep its own coverage."""
    tests = '''import pytest


@pytest.mark.covers("FR-01.30")
def test_live():
    assert True
'''
    m = _build(_repo(tmp_path, fold_rows="| `FR-01.30` | `FR-01.28` | delta | x |",
                     tests=tests))
    assert len(_links(m, "FR-01.30")) == 1
    assert _links(m, "FR-01.28") == []
    assert "resolved_from" not in _links(m, "FR-01.30")[0]
    # ...and the self-contradicting spec is surfaced as hygiene.
    assert [d["kind"] for d in m["fold_defects"]] == ["folded_id_still_active"]


def test_a_test_tagged_with_BOTH_folded_and_survivor_yields_exactly_one_link(tmp_path):
    """No double-counting: the survivor gets one link, carrying the DIRECT provenance."""
    tests = '''import pytest


@pytest.mark.covers("FR-01.44")
@pytest.mark.covers("FR-01.28")
def test_both():
    assert True
'''
    m = _build(_repo(tmp_path, fold_rows="| `FR-01.44` | `FR-01.28` | delta | x |",
                     tests=tests))
    links = _links(m, "FR-01.28")
    assert len(links) == 1
    assert "resolved_from" not in links[0]
    assert m["orphans"] == []


# --------------------------------------------------------------------------
# AC3 — every broken edge still fails closed
# --------------------------------------------------------------------------


@pytest.mark.parametrize("rows,kinds", [
    ("| `FR-01.44` | `FR-01.45` | d | a |\n| `FR-01.45` | `FR-01.44` | d | b |",
     ["cycle"]),
    ("| `FR-01.44` | `FR-01.77` | d | a |", ["dangling_survivor"]),
    ("| `FR-01.44` | `FR-01.44` | d | a |", ["self_fold"]),
    ("| `FR-01.44` | `FR-01.28` | d | a |\n| `FR-01.44` | `FR-01.30` | d | b |",
     ["conflicting_survivor"]),
])
def test_unsafe_edges_keep_the_orphan_and_record_a_defect(tmp_path, rows, kinds):
    m = _build(_repo(tmp_path, fold_rows=rows, tests=_TAGGED_FOLDED))
    assert [o["category"] for o in m["orphans"]] == ["confirmed_orphan"]
    assert [d["kind"] for d in m["fold_defects"]] == kinds
    status, severity, _, _, _ = check_orphan(m)
    assert status == "fail" and severity == "MEDIUM"


def test_fold_defects_alone_are_LOW_hygiene_not_a_medium_failure(tmp_path):
    """A broken edge nobody tags is still surfaced — silent under-resolution is the risk —
    but it is hygiene, not the MEDIUM reserved for a genuinely orphaned test."""
    m = _build(_repo(tmp_path, fold_rows="| `FR-01.44` | `FR-01.77` | d | a |",
                     tests="def test_untagged():\n    assert True\n"))
    assert m["orphans"] == []
    status, severity, detail, evidence, _ = check_orphan(m)
    assert (status, severity) == ("fail", "LOW")
    assert "FR-Fold-Map defect" in detail
    assert any("[fold_map]" in e for e in evidence)


# --------------------------------------------------------------------------
# AC5 — artifact contract
# --------------------------------------------------------------------------


def test_manifest_with_fold_data_is_v2_schema_valid(tmp_path):
    m = _build(_repo(
        tmp_path,
        fold_rows=("| `FR-01.44` | `FR-01.28` | d | a |\n"
                   "| `FR-1.9` | `FR-01.28` | d | bad |"),
        tests=_TAGGED_FOLDED))
    jsonschema.Draft202012Validator(_SCHEMA).validate(m)
    assert m["fold_defects"]


def test_a_repo_without_a_fold_map_emits_NO_new_keys(tmp_path):
    """Byte-identical regression: this artifact is committed churn, so an empty
    ``fold_map: {}`` would diff on every regen for every project that has no folds."""
    m = _build(_repo(tmp_path, fold_rows=None, tests=_TAGGED_FOLDED))
    assert "fold_map" not in m
    assert "fold_defects" not in m
    assert all("resolved_from" not in l
               for node in m["requirements"].values()
               for links in (node.get("tests") or {}).values() for l in links)
    jsonschema.Draft202012Validator(_SCHEMA).validate(m)


def test_manifest_round_trips_through_json_unchanged(tmp_path):
    """Boundary probe: write → read → still schema-valid and equal."""
    m = _build(_repo(tmp_path, fold_rows="| `FR-01.44` | `FR-01.28` | delta | x |",
                     tests=_TAGGED_FOLDED))
    out = tmp_path / "manifest.json"
    out.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    reloaded = json.loads(out.read_text(encoding="utf-8"))
    assert reloaded == m
    jsonschema.Draft202012Validator(_SCHEMA).validate(reloaded)


# --------------------------------------------------------------------------
# AC4 — the fold table is never read as live requirements
# --------------------------------------------------------------------------


@pytest.mark.parametrize("rows", [
    "| `FR-01.44` | `FR-01.28` | delta | backticked |",
    "| FR-01.44 | FR-01.28 | delta | UNbackticked |",
])
def test_fold_rows_never_become_active_requirements(tmp_path, rows):
    """The unbackticked case is the dangerous one: it would otherwise resurrect every
    folded id as an active FR demanding its own coverage."""
    m = _build(_repo(tmp_path, fold_rows=rows, tests=_TAGGED_FOLDED))
    ids = {node["id"] for node in m["requirements"].values()}
    assert ids == {"FR-01.28", "FR-01.30"}
