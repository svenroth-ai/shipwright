"""The test-tag gate's third class: a harness test declared as infrastructure (FR-01.11/AC55).

Hand-built manifests, like ``test_tag_binding_core.py``; the catalog is passed in as the set the gate
read at the merge-base.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.verifiers._tag_binding_core import evaluate
from tools.verifiers._tag_binding_identity import body_digests
from tools.verifiers._tag_binding_infra import py_infra_info
from tools.verifiers._tag_binding_infra_pass import CATALOG_PATH, parse_catalog
from tools.verifiers._tag_binding_py import _is_exact_covers_none

pytestmark = pytest.mark.covers("FR-01.11/AC55")

F = "shared/tests/test_harness.py"
TID = f"{F}::test_probe"
OLD = "def test_old():\n    assert 1 + 1 == 2\n"
MARK = '@pytest.mark.covers_none("tooling")\n'
PROBE = "def test_probe():\n    assert True\n"


def _manifest(untagged=(), links=(), acs=None):
    tests = {"unit": [{"id": t, "path": t} for t in links]}
    ac_nodes = {ac: {"tests": {"unit": [{"id": t, "path": t} for t in ts]}} for ac, ts in (acs or {}).items()}
    return {"requirements": {"01::FR-01.11": {"tests": tests, "acs": ac_nodes}},
            "untagged_tests": sorted(untagged), "orphans": [], "invalid_tags": []}


def _run(base_m, head_m, base_files, head_files, catalog=frozenset({F}), exemptions=()):
    changed = set(base_files) | set(head_files)

    def read(path, side):
        return (base_files if side == "base" else head_files).get(path, "")

    return evaluate(base_m, head_m, changed, read, list(exemptions), set(), catalog)


def _added(src: str, catalog=frozenset({F})):
    return _run(_manifest([f"{F}::test_old"]), _manifest([f"{F}::test_old", TID]),
                {F: OLD}, {F: OLD + "\n\n" + src}, catalog)


def _kinds(v):
    return [(k, t) for k, t, _w in v.findings]


def test_marked_test_in_a_catalog_file_is_infrastructure():
    v = _added(MARK + PROBE)
    assert v.findings == [] and v.infra == {TID}
    assert TID not in v.touched  # out of the exemption-share denominator


@pytest.mark.parametrize("deco", [
    '@pytest.mark.covers_none("compliance")\n',
    '@pytest.mark.covers_none("tooling", "infra")\n',
    '@pytest.mark.covers_none(label="tooling")\n',
    '@pytest.mark.covers_none(LABEL)\n',
    "@pytest.mark.covers_none()\n",
    '@mark.covers_none("tooling")\n',
    '@helpers.covers_none("tooling")\n',
])
def test_only_the_literal_marker_with_one_valid_label_is_granted(deco):
    v = _added(deco + PROBE)
    assert _kinds(v) == [("bad-infra-class", TID)] and v.infra == set()


@pytest.mark.parametrize("catalog", [frozenset(), frozenset({"shared/tests/other.py"}), None])
def test_a_file_outside_the_base_catalog_is_refused(catalog):
    v = _added(MARK + PROBE, catalog)
    assert _kinds(v) == [("bad-infra-class", TID)]


def test_the_failure_names_the_next_step_for_a_new_file():
    v = _added(MARK + PROBE, frozenset())
    assert "earlier merge" in v.findings[0][2]


def test_same_name_siblings_must_all_carry_the_marker():
    src = MARK + PROBE + "\n\nclass TestA:\n    def test_probe(self):\n        assert True\n"
    v = _added(src)
    assert _kinds(v) == [("bad-infra-class", TID)]


@pytest.mark.parametrize("head", [
    'pytestmark = pytest.mark.covers("FR-01.11/AC01")\n',
    'pytestmark = [pytest.mark.covers("FR-01.11/AC01")]\n',
    'pytestmark: list = [pytest.mark.covers("FR-01.11/AC01")]\n',
    'pytestmark = []\npytestmark += [pytest.mark.covers("FR-01.11/AC01")]\n',
    'reqs = [pytest.mark.covers("FR-01.11/AC01")]\npytestmark = reqs\n',
])
def test_a_covers_mark_in_any_module_form_contradicts_the_marker(head):
    v = _run(_manifest([f"{F}::test_old"]), _manifest([f"{F}::test_old"], links=[TID]),
             {F: OLD}, {F: head + OLD + "\n\n" + MARK + PROBE})
    assert ("bad-infra-class", TID) in _kinds(v)


def test_a_covers_mark_on_the_class_or_the_function_contradicts_the_marker():
    src = MARK + '@pytest.mark.covers("FR-01.11/AC01")\n' + PROBE
    v = _run(_manifest([f"{F}::test_old"]), _manifest([f"{F}::test_old"], links=[TID]),
             {F: OLD}, {F: OLD + "\n\n" + src})
    assert ("bad-infra-class", TID) in _kinds(v)


_CLS_BODY = "    def test_probe(self):\n        assert True\n"


@pytest.mark.parametrize("src", [
    '@pytest.mark.covers("FR-01.11/AC01")\nclass TestA:\n    ' + MARK + _CLS_BODY,
    'class TestA:\n    pytestmark = [pytest.mark.covers("FR-01.11/AC01")]\n    ' + MARK + _CLS_BODY,
    '@mark.covers("FR-01.11/AC01")\n' + MARK + PROBE,
    'class TestA:\n    pytestmark = tags\n    ' + MARK + _CLS_BODY,
])
def test_class_level_covers_forms_and_unresolved_class_marks_contradict_the_marker(src):
    [info] = py_infra_info(src, "test_probe")
    assert info.has_covers or info.bad


def test_covers_none_is_never_read_as_a_requirement_tag():
    from tools.verifiers._tag_binding_py import py_tag_sets
    assert py_tag_sets(MARK + PROBE, "test_probe") == [frozenset()]


def test_module_level_marker_classes_the_tests_already_in_the_file():
    src = 'pytestmark = pytest.mark.covers_none("infra")\n' + OLD
    v = _run(_manifest([f"{F}::test_old"]), _manifest([f"{F}::test_old"]), {F: OLD}, {F: src})
    assert v.findings == [] and v.infra == {f"{F}::test_old"}


def test_a_test_added_beside_a_module_level_marker_needs_its_own_marker():
    src = 'pytestmark = pytest.mark.covers_none("infra")\n' + OLD + "\n\n" + PROBE
    v = _run(_manifest([f"{F}::test_old"]), _manifest([f"{F}::test_old", TID]), {F: OLD}, {F: src})
    assert _kinds(v) == [("bad-infra-class", TID)] and "its own" in v.findings[0][2]


def test_an_untouched_infra_test_is_not_refused_for_an_unrelated_retirement():
    """A harness file that already declares infra tests, edited next to a retired requirement test."""
    gone = "tests/test_x.py::test_fr"
    base_files = {F: MARK + PROBE, "tests/test_x.py": "def test_fr():\n    pass\n"}
    head_files = {F: MARK + PROBE + "\n\n# edited\n", "tests/test_x.py": ""}
    v = _run(_manifest([TID], links=[gone]), _manifest([TID]), base_files, head_files)
    assert "bad-infra-class" not in [k for k, _t, _w in v.findings]
    assert v.infra == {TID}


def test_every_committed_test_that_declares_covers_none_is_in_the_catalog():
    import ast
    import subprocess
    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(["git", "-C", str(root), "ls-files", "*.py"], capture_output=True, text=True)
    if proc.returncode != 0:
        pytest.skip("not a git checkout")
    declaring = set()
    for rel in proc.stdout.splitlines():
        path = root / rel
        if not path.is_file() or not any(part in ("tests", "integration-tests") for part in Path(rel).parts):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        if any(isinstance(n, ast.Call) and _is_exact_covers_none(n) for n in ast.walk(tree)):
            declaring.add(rel.replace("\\", "/"))
    catalog_file = root / CATALOG_PATH
    listed = parse_catalog(catalog_file.read_text(encoding="utf-8"))[0] if catalog_file.exists() else frozenset()
    assert declaring <= (listed or frozenset()), sorted(declaring - (listed or frozenset()))


def _corrected(extra_links=(), acs=None, base_catalog=frozenset({F})):
    base_files, head_files = {F: PROBE}, {F: MARK + PROBE}
    return _run(_manifest(links=[TID, *extra_links], acs=acs), _manifest([TID], links=list(extra_links), acs=acs),
                base_files, head_files, base_catalog)


def test_a_stand_in_correction_is_accepted_when_the_requirement_keeps_a_test():
    other = "tests/test_real.py::test_real"
    v = _corrected(extra_links=[other])
    assert v.findings == [] and v.infra == {TID}
    assert any("drops stand-in tag" in w for w in v.warnings)


def test_a_correction_that_orphans_the_requirement_is_refused():
    v = _corrected()
    assert _kinds(v) == [("bad-infra-class", TID)] and "no other linked test" in v.findings[0][2]


def test_a_correction_that_orphans_one_criterion_is_refused():
    other = "tests/test_real.py::test_real"
    v = _corrected(extra_links=[other], acs={"AC01": [TID]})
    assert _kinds(v) == [("bad-infra-class", TID)] and "AC01" in v.findings[0][2]


def test_a_plain_tag_removal_still_fails():
    v = _run(_manifest(links=[TID]), _manifest([TID]), {F: PROBE}, {F: PROBE})
    assert _kinds(v) == [("tag-removed", TID)]


def test_a_tagged_test_moved_into_a_catalog_file_with_the_marker_is_a_correction():
    other = "tests/test_real.py::test_real"
    old_file = "shared/tests/test_old_home.py"
    old_id = f"{old_file}::test_probe"
    v = _run(_manifest(links=[old_id, other]), _manifest([TID], links=[other]),
             {old_file: PROBE}, {old_file: "", F: MARK + PROBE}, frozenset({F, old_file}))
    assert v.findings == [] and v.infra == {TID}


def test_a_moved_tagged_test_whose_old_path_is_outside_the_catalog_is_refused():
    other = "tests/test_real.py::test_real"
    old_file = "shared/tests/test_old_home.py"
    old_id = f"{old_file}::test_probe"
    v = _run(_manifest(links=[old_id, other]), _manifest([TID], links=[other]),
             {old_file: PROBE}, {old_file: "", F: MARK + PROBE})
    assert _kinds(v) == [("bad-infra-class", TID)]


def test_the_digest_ignores_the_exact_marker_but_not_an_alias():
    plain = body_digests(PROBE, F, "test_probe")
    assert body_digests(MARK.replace("tooling", "infra") + PROBE, F, "test_probe") == plain
    assert body_digests('@mark.covers_none("tooling")\n' + PROBE, F, "test_probe") != plain
    assert body_digests('@helpers.covers_none("tooling")\n' + PROBE, F, "test_probe") != plain


def test_adding_the_marker_to_a_legacy_test_is_not_an_edit():
    v = _run(_manifest([TID]), _manifest([TID]), {F: PROBE}, {F: MARK + PROBE})
    assert v.findings == [] and v.touched == set()


def test_an_unrelated_untagged_test_still_stops_beside_an_infra_one():
    src = MARK + PROBE + "\n\ndef test_other():\n    assert True\n"
    v = _run(_manifest([f"{F}::test_old"]), _manifest([f"{F}::test_old", TID, f"{F}::test_other"]),
             {F: OLD}, {F: OLD + "\n\n" + src})
    assert _kinds(v) == [("untagged-added", f"{F}::test_other")]
    assert v.touched == {f"{F}::test_other"} and v.infra == {TID}


def test_a_per_test_exemption_beside_the_marker_changes_nothing():
    ex = {"kind": "test_exemption", "scope": TID, "reason_code": "fixture-or-helper"}
    v = _run(_manifest([f"{F}::test_old"]), _manifest([f"{F}::test_old", TID]),
             {F: OLD}, {F: OLD + "\n\n" + MARK + PROBE}, exemptions=[ex])
    assert v.findings == [] and v.exempted == [] and v.infra == {TID}


def test_a_ts_test_cannot_carry_the_marker():
    spec = "e2e/flow.spec.ts"
    tid = f"{spec}::flow works"
    v = _run(_manifest(), _manifest([tid]), {}, {spec: "test('flow works', async () => {});\n"},
             frozenset({spec}))
    assert [k for k, _t, _w in v.findings] == ["untagged-added"] and v.infra == set()


def test_py_infra_info_reads_marker_labels_and_contradictions():
    [info] = py_infra_info(MARK + PROBE, "test_probe")
    assert info.labels == {"tooling"} and info.declared and not info.has_covers and info.bad == ()
    [info] = py_infra_info("pytestmark = requirement_marks\n" + MARK + PROBE, "test_probe")
    assert info.bad and info.declared


def test_catalog_absent_empty_unreadable_and_malformed():
    assert parse_catalog("") == (frozenset(), None)
    assert parse_catalog(None) == (None, None)
    assert parse_catalog(json.dumps([F])) == (frozenset({F}), None)
    for bad in ("not json", json.dumps({"a": 1}), json.dumps(["shared/tests/*.py"]),
                json.dumps(["../x.py"]), json.dumps(["/abs/x.py"]), json.dumps(["C:/x.py"]),
                json.dumps(["a\\b.py"]), json.dumps(["shared/tests"]), json.dumps([3]),
                json.dumps(["shared/scripts/example.py"]), json.dumps(["shared/tests/conftest.py"])):
        paths, warning = parse_catalog(bad)
        assert paths == frozenset() and warning and CATALOG_PATH in warning, bad


def test_the_head_catalog_is_valid_and_names_existing_files():
    """Runs against this checkout; vacuous while the catalog does not exist yet."""
    root = Path(__file__).resolve().parents[2]
    path = root / CATALOG_PATH
    if not path.exists():
        pytest.skip("no catalog in this tree yet")
    paths, warning = parse_catalog(path.read_text(encoding="utf-8"))
    assert warning is None and paths
    assert [p for p in paths if not (root / p).is_file()] == []


def test_a_renamed_and_edited_stand_in_cannot_slip_the_correction_rule():
    """The tagged test vanishes and a differently named, differently bodied marked test appears: identity
    matching finds no origin, so the lost requirement is what refuses it."""
    marked = MARK + "def test_probe2():\n    assert 1\n"
    v = _run(_manifest(links=[TID]), _manifest([f"{F}::test_probe2"]), {F: PROBE}, {F: marked})
    assert _kinds(v) == [("bad-infra-class", f"{F}::test_probe2")] and v.infra == set()
    assert "no linked test left" in v.findings[0][2]


def test_retiring_a_stand_in_beside_a_covered_requirement_is_not_blocked():
    other = "tests/test_real.py::test_real"
    marked = MARK + "def test_probe2():\n    assert 1\n"
    v = _run(_manifest(links=[TID, other]), _manifest([f"{F}::test_probe2"], links=[other]),
             {F: PROBE}, {F: marked})
    assert v.findings == [] and v.infra == {f"{F}::test_probe2"}


def test_a_test_the_manifest_links_to_a_requirement_is_never_infrastructure():
    """Defence beyond the parser: whatever form the collector counted, a linked test is not classed."""
    v = _run(_manifest(links=[TID]), _manifest(links=[TID]), {F: PROBE}, {F: MARK + PROBE})
    assert ("bad-infra-class", TID) in _kinds(v) and v.infra == set()


def test_a_real_requirement_test_cannot_live_in_a_file_with_a_module_marker():
    src = ('pytestmark = pytest.mark.covers_none("infra")\n' + OLD
           + '\n\n@pytest.mark.covers("FR-01.11/AC01")\ndef test_real():\n    assert True\n')
    real = f"{F}::test_real"
    v = _run(_manifest([f"{F}::test_old"]), _manifest([f"{F}::test_old"], links=[real]), {F: OLD}, {F: src})
    assert ("bad-infra-class", real) in _kinds(v)


@pytest.mark.parametrize("head", [
    'pytestmark, unused = ([pytest.mark.covers("FR-01.11/AC01")], None)\n',
    'pytestmark[0] = pytest.mark.covers("FR-01.11/AC01")\n',
    'if True:\n    pytestmark = [pytest.mark.covers("FR-01.11/AC01")]\n',
    'Holder.pytestmark = [pytest.mark.covers("FR-01.11/AC01")]\n',
])
def test_a_pytestmark_in_a_form_the_gate_cannot_read_refuses_the_grant(head):
    v = _run(_manifest([f"{F}::test_old"]), _manifest([f"{F}::test_old", TID]),
             {F: OLD}, {F: head + OLD + "\n\n" + MARK + PROBE})
    assert ("bad-infra-class", TID) in _kinds(v) and TID not in v.infra


def test_a_class_covers_decorator_contradicts_the_marker_through_evaluate():
    src = '@pytest.mark.covers("FR-01.11/AC01")\nclass TestA:\n    ' + MARK + _CLS_BODY
    tid = f"{F}::test_probe"
    v = _run(_manifest([f"{F}::test_old"]), _manifest([f"{F}::test_old"], links=[tid]), {F: OLD}, {F: OLD + "\n\n" + src})
    assert ("bad-infra-class", tid) in _kinds(v)
