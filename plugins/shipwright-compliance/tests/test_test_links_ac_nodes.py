"""v4 AC-node manifest tests (campaign req3-04c-ac-identity-wave2 P3.2, D9).

Split out of ``test_test_links_collector.py``, which the LOC cap left no room in.
Same sibling relationship as ``test_group_d_provenance_hardening.py`` /
``test_group_d_hardening.py``: a self-contained fixture, not a slice of the golden
mini-repo — ``@pytest.mark.covers("FR-XX.YY/ACnn")`` is Python-only for this grammar
version, so a small in-repo pytest fixture (mirroring the AC2 ``suite_manifest``
pattern in the sibling file) is the natural answer key here, not a TS/JS-heavy one.
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


def _by_id(manifest: dict, fr_id: str) -> dict:
    for req in manifest["requirements"].values():
        if req["id"] == fr_id:
            return req
    raise AssertionError(fr_id)


@pytest.fixture(scope="module")
def validator() -> jsonschema.Draft202012Validator:
    schema = json.loads((_LIB / "traceability_schema.json").read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


_AC_SPEC = """# Spec
## Functional Requirements
| FR | Description | Priority | Layers |
|----|-------------|----------|--------|
| FR-06.01 | Sign in | Must | unit |
"""

_AC_TESTS = (
    'import pytest\n\n'
    '@pytest.mark.covers("FR-06.01/AC99")\n'
    'def test_rejects_bad_password():\n    assert True\n\n'
    '@pytest.mark.covers("FR-06.01/AC100")\n'
    'def test_locks_after_five_attempts():\n    assert True\n\n'
    '@pytest.mark.covers("FR-06.01")\n'                 # bare — FR-level only, no AC node
    'def test_generic_sign_in():\n    assert True\n'
)


@pytest.fixture(scope="module")
def ac_manifest(tmp_path_factory) -> dict:
    root = tmp_path_factory.mktemp("ac_nodes")
    (root / "spec.md").write_text(_AC_SPEC, encoding="utf-8")
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_auth.py").write_text(_AC_TESTS, encoding="utf-8")
    evidence = {
        "tests/test_auth.py::test_rejects_bad_password": {"status": "enabled", "executed": "pass"},
        "tests/test_auth.py::test_locks_after_five_attempts": {"status": "enabled", "executed": "not_run"},
    }
    return build_manifest(
        root, spec_files=[root / "spec.md"], test_roots=[tests_dir.parent],
        evidence=evidence, enumerate_untagged=True,
    )


def test_ac_scoped_tag_produces_an_acs_node(ac_manifest, validator):
    assert not list(validator.iter_errors(ac_manifest))
    fr = _by_id(ac_manifest, "FR-06.01")
    assert set(fr["acs"]) == {"AC99", "AC100"}
    ac99_link = fr["acs"]["AC99"]["tests"]["unit"][0]
    assert ac99_link["path"] == "tests/test_auth.py::test_rejects_bad_password"
    assert ac99_link["ac_id"] == "AC99"


def test_ac_node_coverage_is_ok_only_when_a_link_passed(ac_manifest):
    fr = _by_id(ac_manifest, "FR-06.01")
    assert fr["acs"]["AC99"]["coverage"]["unit"] == "ok"          # executed=pass
    assert fr["acs"]["AC100"]["coverage"]["unit"] == "MISSING"    # executed=not_run


def test_bare_fr_tag_creates_no_ac_node_but_still_covers_the_fr(ac_manifest):
    fr = _by_id(ac_manifest, "FR-06.01")
    unit_paths = {link["path"] for link in fr["tests"]["unit"]}
    assert "tests/test_auth.py::test_generic_sign_in" in unit_paths
    bare_link = next(l for l in fr["tests"]["unit"]
                      if l["path"] == "tests/test_auth.py::test_generic_sign_in")
    assert "ac_id" not in bare_link                                # E1: AC unspecified
    assert not any("test_generic_sign_in" in link["path"]
                   for ac in fr["acs"].values() for link in ac["tests"].get("unit", []))


def test_acs_are_sorted_by_ac_number_not_lexically(ac_manifest):
    """AC99/AC100 diverge under lexical vs numeric sort — lexically "AC100" <
    "AC99" (external code review, glm/medium: the original AC07/AC09 fixture
    sorted identically either way and could not catch a regression to plain
    ``sorted()``); numeric sort correctly keeps AC99 before AC100."""
    fr = _by_id(ac_manifest, "FR-06.01")
    assert list(fr["acs"]) == ["AC99", "AC100"]
    assert sorted(fr["acs"]) != list(fr["acs"]), (
        "fixture no longer distinguishes lexical from numeric order"
    )


def test_bare_and_ac_scoped_tags_on_the_same_test_merge_not_duplicate(tmp_path):
    """A test carrying BOTH a bare and an AC-scoped tag for the same FR (external
    plan review, openai/low + glm/low: link cardinality) must not double-count in
    the parent's ``tests`` bucket — the bare hit's link gets its ``ac_id``
    backfilled by the AC-scoped hit, one link, filed once under the AC bucket too."""
    (tmp_path / "spec.md").write_text(_AC_SPEC, encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_both.py").write_text(
        'import pytest\n\n'
        '@pytest.mark.covers("FR-06.01")\n'
        '@pytest.mark.covers("FR-06.01/AC07")\n'
        'def test_x():\n    assert True\n', encoding="utf-8",
    )
    manifest = build_manifest(
        tmp_path, spec_files=[tmp_path / "spec.md"], test_roots=[tests_dir],
        evidence={}, enumerate_untagged=True,
    )
    fr = _by_id(manifest, "FR-06.01")
    unit_links = fr["tests"]["unit"]
    assert len(unit_links) == 1, "one test, one link — not one per tag"
    assert unit_links[0]["ac_id"] == "AC07", "the bare hit's link is backfilled, not duplicated"
    assert fr["acs"]["AC07"]["tests"]["unit"][0]["path"] == unit_links[0]["path"]


def test_two_different_acs_on_the_same_test_do_not_pick_one_at_the_parent(tmp_path):
    """A test bound to TWO DIFFERENT ACs of the same FR (external code review,
    openai/medium: the parent bucket's dedup silently kept whichever ac_id was
    filed first). The parent's singular ``ac_id`` field cannot represent both,
    so the fix drops it there rather than guess — while each AC's OWN bucket
    still carries its own correct, unambiguous link."""
    (tmp_path / "spec.md").write_text(_AC_SPEC, encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_multi.py").write_text(
        'import pytest\n\n'
        '@pytest.mark.covers("FR-06.01/AC07")\n'
        '@pytest.mark.covers("FR-06.01/AC99")\n'
        'def test_x():\n    assert True\n', encoding="utf-8",
    )
    manifest = build_manifest(
        tmp_path, spec_files=[tmp_path / "spec.md"], test_roots=[tests_dir],
        evidence={}, enumerate_untagged=True,
    )
    fr = _by_id(manifest, "FR-06.01")
    unit_links = fr["tests"]["unit"]
    assert len(unit_links) == 1, "one test, one link — not one per AC tag"
    assert "ac_id" not in unit_links[0], "ambiguous across two ACs — must not guess one"
    assert fr["acs"]["AC07"]["tests"]["unit"][0]["ac_id"] == "AC07"
    assert fr["acs"]["AC99"]["tests"]["unit"][0]["ac_id"] == "AC99"


def test_a_third_repeated_ac_tag_does_not_un_ambiguate_the_parent(tmp_path):
    """PR-review (openai/medium): AC07, AC99, AC07 -- the repeat of AC07 must NOT
    backfill ``ac_id`` back onto the parent link. The parent became ambiguous the
    moment AC99 conflicted with AC07; a later tag repeating either AC does not
    change that the test covers two different ACs. Guards the ``_ac_ambiguous``
    sentinel (never un-set once tripped) and that it never leaks into the
    shipped manifest."""
    (tmp_path / "spec.md").write_text(_AC_SPEC, encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_triple.py").write_text(
        'import pytest\n\n'
        '@pytest.mark.covers("FR-06.01/AC07")\n'
        '@pytest.mark.covers("FR-06.01/AC99")\n'
        '@pytest.mark.covers("FR-06.01/AC07")\n'
        'def test_x():\n    assert True\n', encoding="utf-8",
    )
    manifest = build_manifest(
        tmp_path, spec_files=[tmp_path / "spec.md"], test_roots=[tests_dir],
        evidence={}, enumerate_untagged=True,
    )
    fr = _by_id(manifest, "FR-06.01")
    unit_links = fr["tests"]["unit"]
    assert len(unit_links) == 1, "one test, one link — not one per AC tag"
    assert "ac_id" not in unit_links[0], "still ambiguous — the repeat must not restore it"
    assert "_ac_ambiguous" not in unit_links[0], "internal sentinel must never ship"
    assert fr["acs"]["AC07"]["tests"]["unit"][0]["ac_id"] == "AC07"
    assert fr["acs"]["AC99"]["tests"]["unit"][0]["ac_id"] == "AC99"


def test_malformed_ac_suffix_is_invalid_not_a_bare_fr_hit(tmp_path):
    (tmp_path / "spec.md").write_text(_AC_SPEC, encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_bad.py").write_text(
        'import pytest\n\n@pytest.mark.covers("FR-06.01/AC7")\n'
        'def test_x():\n    assert True\n', encoding="utf-8",
    )
    manifest = build_manifest(
        tmp_path, spec_files=[tmp_path / "spec.md"], test_roots=[tests_dir],
        evidence={}, enumerate_untagged=True,
    )
    fr = _by_id(manifest, "FR-06.01")
    assert fr["tests"] == {} and "acs" not in fr
    assert manifest["invalid_tags"][0]["raw"] == "FR-06.01/AC7"
    assert manifest["invalid_tags"][0]["reason"] == "non_canonical_ac_id"
