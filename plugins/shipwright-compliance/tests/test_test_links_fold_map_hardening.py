"""Collector-level hardening for FR-Fold-Map resolution — every case here traces to a
finding from this iterate's adversarial + spec review.

The headline one is `test_removing_an_fr_and_folding_it_...`: fold resolution must NOT be
able to dismiss the tests of a *removed* feature. Without that guard, moving an FR into
`## Removed Requirements` and adding one fold row in the same commit would file a test
still carrying the dead tag as a link on the survivor, and the F11 removal gate
(`_layer_coverage_removal._classify_at_head`) would read that as "retargeted to a live
FR" — repealing its load-bearing invariant with a two-line markdown edit.

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

from scripts.lib.collectors.test_links import build_manifest  # noqa: E402

_SCHEMA = json.loads(
    (_HERE.parent / "scripts" / "lib" / "traceability_schema.json").read_text(encoding="utf-8"))

_TAGGED = '''import pytest


@pytest.mark.covers("FR-01.44")
def test_thing():
    assert True
'''


def _repo(tmp_path: Path, spec: str, tests: str = _TAGGED) -> Path:
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "spec.md").write_text(spec, encoding="utf-8")
    (root / "tests" / "test_thing.py").write_text(tests, encoding="utf-8")
    return root


def _build(root: Path) -> dict:
    return build_manifest(
        root, spec_files=[root / "spec.md"], test_roots=[root], evidence={},
        enumerate_untagged=False, generated_at="2026-07-18T00:00:00+00:00",
        source_commit="b" * 40)


def _links(m: dict, fr: str) -> list[dict]:
    for node in m["requirements"].values():
        if node["id"] == fr:
            return [l for ls in (node.get("tests") or {}).values() for l in ls]
    return []


_ACTIVE_ONLY = """# Spec

## Functional Requirements

| FR | Description | Priority | Layers |
|----|-------------|----------|--------|
| FR-01.28 | Survivor capability | Must | unit |
"""

_FOLD = """
## FR-Fold-Map

| Folded ID | → Survivor | Reason | Was |
|-----------|-----------|--------|-----|
{rows}
"""


# --------------------------------------------------------------------------
# Retirement beats folding — the F11 removal-gate false-green
# --------------------------------------------------------------------------


def test_removing_an_fr_and_folding_it_does_NOT_rescue_its_dead_tags(tmp_path):
    """The false-green, pinned. FR-01.44 is explicitly retired AND folded; a test still
    carrying `@covers("FR-01.44")` must remain an orphan so the removal gate stays HARD."""
    spec = _ACTIVE_ONLY + """
## Removed Requirements

| FR | Description | Priority | Layers |
|----|-------------|----------|--------|
| FR-01.44 | Retired thing | Must | unit |
""" + _FOLD.format(rows="| `FR-01.44` | `FR-01.28` | delta | x |")

    m = _build(_repo(tmp_path, spec))
    assert [o["category"] for o in m["orphans"]] == ["confirmed_orphan"]
    assert m["orphans"][0]["reason"] == "fr_removed"
    assert _links(m, "FR-01.28") == []               # survivor gains NOTHING
    assert [d["kind"] for d in m["fold_defects"]] == ["folded_id_removed"]


def test_a_genuinely_folded_id_absent_from_the_table_is_still_rescued(tmp_path):
    """Control — the real webui pattern drops a folded id from the FR table entirely, so
    it is ABSENT (not removed) and the rescue must still work."""
    spec = _ACTIVE_ONLY + _FOLD.format(rows="| `FR-01.44` | `FR-01.28` | delta | x |")
    m = _build(_repo(tmp_path, spec))
    assert m["orphans"] == []
    assert [l["resolved_from"] for l in _links(m, "FR-01.28")] == ["FR-01.44"]


# --------------------------------------------------------------------------
# Orphan reason must name what the tag points AT
# --------------------------------------------------------------------------


def test_a_chain_ending_at_a_REMOVED_survivor_reports_fr_removed(tmp_path):
    """`fr_absent` would tell the operator "this FR never existed" about a requirement
    that was deliberately retired."""
    spec = _ACTIVE_ONLY + """
## Removed Requirements

| FR | Description | Priority | Layers |
|----|-------------|----------|--------|
| FR-01.50 | Retired survivor | Must | unit |
""" + _FOLD.format(rows="| `FR-01.44` | `FR-01.50` | delta | x |")

    m = _build(_repo(tmp_path, spec))
    (orphan,) = m["orphans"]
    assert orphan["tagged_fr"] == "FR-01.44"
    assert orphan["reason"] == "fr_removed"
    assert [d["kind"] for d in m["fold_defects"]] == ["removed_survivor"]


def test_a_chain_to_nowhere_still_reports_fr_absent(tmp_path):
    """Control for the above — a survivor in no table at all is genuinely absent."""
    spec = _ACTIVE_ONLY + _FOLD.format(rows="| `FR-01.44` | `FR-01.77` | delta | x |")
    m = _build(_repo(tmp_path, spec))
    assert m["orphans"][0]["reason"] == "fr_absent"


# --------------------------------------------------------------------------
# A healthy chain through a dead intermediate must not report a defect
# --------------------------------------------------------------------------


def test_a_chain_through_a_removed_intermediate_resolves_with_NO_defect(tmp_path):
    """Auditing each edge's immediate target flagged the intermediate as dangling and
    failed D-orphan at LOW for a fold that resolves perfectly."""
    spec = _ACTIVE_ONLY + _FOLD.format(rows=(
        "| `FR-01.44` | `FR-01.45` | delta | a |\n"
        "| `FR-01.45` | `FR-01.28` | delta | b |"))
    m = _build(_repo(tmp_path, spec))
    assert m["orphans"] == []
    assert "fold_defects" not in m
    assert [l["resolved_from"] for l in _links(m, "FR-01.28")] == ["FR-01.44"]


# --------------------------------------------------------------------------
# Link identity: no aliasing across requirement nodes
# --------------------------------------------------------------------------


def test_a_folded_and_a_direct_tag_on_one_test_yield_one_link_with_direct_provenance(tmp_path):
    """The supersede branch mutates the stored link, so each node must own its own dict."""
    tests = '''import pytest


@pytest.mark.covers("FR-01.44")
@pytest.mark.covers("FR-01.28")
def test_thing():
    assert True
'''
    spec = _ACTIVE_ONLY + _FOLD.format(rows="| `FR-01.44` | `FR-01.28` | delta | x |")
    m = _build(_repo(tmp_path, spec, tests))
    links = _links(m, "FR-01.28")
    assert len(links) == 1
    assert "resolved_from" not in links[0]
    jsonschema.Draft202012Validator(_SCHEMA).validate(m)


# --------------------------------------------------------------------------
# Schema still accepts every new defect kind
# --------------------------------------------------------------------------


@pytest.mark.parametrize("rows,kind", [
    ("| `FR-01.44` | `FR-01.44` | d | x |", "self_fold"),
    ("| `FR-1.44` | `FR-1.28` | d | x |", "unparsable_row"),
    ("| `FR-01.44` | `FR-01.77` | d | x |", "dangling_survivor"),
])
def test_every_defect_kind_round_trips_through_the_schema(tmp_path, rows, kind):
    m = _build(_repo(tmp_path, _ACTIVE_ONLY + _FOLD.format(rows=rows)))
    assert [d["kind"] for d in m["fold_defects"]] == [kind]
    jsonschema.Draft202012Validator(_SCHEMA).validate(m)
