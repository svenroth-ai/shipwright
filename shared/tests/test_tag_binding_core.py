"""The test-tag gate's pure verdict and its identity rules (U1, FR-01.11/AC41).

Manifests here are hand-built dicts in the collector's shape; the real collector and real
git are exercised in ``test_tag_binding_gate_integration.py``.
"""

from __future__ import annotations

import pytest

from tools.verifiers._tag_binding_core import evaluate
from tools.verifiers._tag_binding_identity import body_digests, would_collect

F = "tests/test_mod.py"


def _manifest(untagged=(), links=(), orphans=(), invalid=()):
    tests = {"unit": [{"id": t, "path": t} for t in links]}
    return {
        "requirements": {"01::FR-01.11": {"tests": tests, "acs": {}}},
        "untagged_tests": sorted(untagged), "orphans": list(orphans), "invalid_tags": list(invalid),
    }


def _reader(base: dict[str, str], head: dict[str, str]):
    return lambda path, side: (base if side == "base" else head).get(path, "")


def _run(base_m, head_m, base_files, head_files, exemptions=(), expected=frozenset()):
    changed = set(base_files) | set(head_files)
    return evaluate(base_m, head_m, changed, _reader(base_files, head_files), list(exemptions), set(expected))


def _ex(scope, code):
    return {"kind": "test_exemption", "scope": scope, "reason_code": code}


_OLD = "def test_old():\n    assert 1 + 1 == 2\n"


@pytest.mark.covers("FR-01.11/AC41")
def test_untagged_added_test_is_named_file_and_test():
    head_src = _OLD + "\n\ndef test_new():\n    assert True\n"
    v = _run(_manifest([f"{F}::test_old"]), _manifest([f"{F}::test_old", f"{F}::test_new"]),
             {F: _OLD}, {F: head_src})
    assert [(k, t) for k, t, _ in v.findings] == [("untagged-added", f"{F}::test_new")]


@pytest.mark.covers("FR-01.11/AC41")
def test_docstring_and_comment_only_edit_is_not_a_modification():
    head_src = 'def test_old():\n    """Now documented."""\n    # a comment\n    assert 1 + 1 == 2\n'
    v = _run(_manifest([f"{F}::test_old"]), _manifest([f"{F}::test_old"]), {F: _OLD}, {F: head_src})
    assert v.findings == []


@pytest.mark.covers("FR-01.11/AC41")
def test_editing_a_legacy_untagged_test_body_stops():
    head_src = "def test_old():\n    assert 1 + 2 == 3\n"
    v = _run(_manifest([f"{F}::test_old"]), _manifest([f"{F}::test_old"]), {F: _OLD}, {F: head_src})
    assert [k for k, _t, _w in v.findings] == ["untagged-modified"]


@pytest.mark.covers("FR-01.11/AC42")
def test_parametrize_case_addition_is_an_edit_not_a_new_test():
    """A new case adds no test id (function-level identity) but it does change what the legacy
    untagged test runs, so it reads as a modification - not as an added test."""
    base_src = '@pytest.mark.parametrize("x", [1])\ndef test_old(x):\n    assert x\n'
    head_src = '@pytest.mark.parametrize("x", [1, 2])\ndef test_old(x):\n    assert x\n'
    v = _run(_manifest([f"{F}::test_old"]), _manifest([f"{F}::test_old"]), {F: base_src}, {F: head_src})
    assert [(k, t) for k, t, _w in v.findings] == [("untagged-modified", f"{F}::test_old")]


@pytest.mark.covers("FR-01.11/AC41")
def test_move_to_another_file_with_unchanged_body_is_matched_by_digest():
    other = "tests/test_other.py"
    v = _run(_manifest([f"{F}::test_old"]), _manifest([f"{other}::test_renamed"]),
             {F: _OLD}, {F: "", other: _OLD.replace("test_old", "test_renamed")})
    assert v.findings == [] and v.moved == [(f"{F}::test_old", f"{other}::test_renamed")]


@pytest.mark.covers("FR-01.11/AC41")
def test_stripping_a_tag_stops_and_cannot_be_exempted():
    tid = f"{F}::test_old"
    v = _run(_manifest(links=[tid]), _manifest([tid]), {F: _OLD}, {F: _OLD},
             exemptions=[_ex(tid, "mechanical-refactor")])
    assert [k for k, _t, _w in v.findings] == ["tag-removed"]


@pytest.mark.covers("FR-01.11/AC41")
def test_fixture_and_production_test_modules_are_not_tests():
    fixture = "plugins/x/tests/fixtures/repo/tests/test_fake.py::test_fake"
    production = "shared/scripts/tools/verifiers/test_checks.py::test_like_helper"
    v = _run(_manifest(), _manifest([fixture, production]), {}, {})
    assert v.findings == []


@pytest.mark.covers("FR-01.11/AC41")
def test_valid_per_test_fixture_or_helper_exemption_passes():
    src = _OLD + "\n\nclass Helpers:\n    def test_data(self):\n        return 1\n"
    tid = f"{F}::test_data"
    v = _run(_manifest([f"{F}::test_old"]), _manifest([f"{F}::test_old", tid]), {F: _OLD}, {F: src},
             exemptions=[_ex(tid, "fixture-or-helper")])
    assert v.findings == [] and v.exempted == [(tid, "fixture-or-helper")]


@pytest.mark.covers("FR-01.11/AC41")
def test_fixture_or_helper_on_a_collected_test_is_refused():
    head_src = _OLD + "\n\ndef test_new():\n    assert True\n"
    tid = f"{F}::test_new"
    v = _run(_manifest([f"{F}::test_old"]), _manifest([f"{F}::test_old", tid]), {F: _OLD}, {F: head_src},
             exemptions=[_ex(tid, "fixture-or-helper")])
    assert [k for k, _t, _w in v.findings] == ["bad-exemption"]


@pytest.mark.covers("FR-01.11/AC41")
@pytest.mark.parametrize("scope", ["tests/test_mod.py", "tests/*::test_new", "*"])
def test_per_diff_or_blanket_exemption_stops(scope):
    head_src = _OLD + "\n\ndef test_new():\n    assert True\n"
    v = _run(_manifest([f"{F}::test_old"]), _manifest([f"{F}::test_old", f"{F}::test_new"]),
             {F: _OLD}, {F: head_src}, exemptions=[_ex(scope, "mechanical-refactor")])
    kinds = sorted(k for k, _t, _w in v.findings)
    assert kinds == ["bad-exemption", "untagged-added"]


@pytest.mark.covers("FR-01.11/AC41")
def test_mechanical_rename_of_200_legacy_tests_passes_with_per_test_exemptions():
    names = [f"test_case_{i:03d}" for i in range(200)]
    base_src = "".join(f"def {n}(old_fixture):\n    assert old_fixture.value == {i}\n\n" for i, n in enumerate(names))
    head_src = base_src.replace("old_fixture", "new_fixture")
    ids = [f"{F}::{n}" for n in names]
    v = _run(_manifest(ids), _manifest(ids), {F: base_src}, {F: head_src},
             exemptions=[_ex(t, "mechanical-refactor") for t in ids])
    assert v.findings == [] and len(v.exempted) == 200


@pytest.mark.covers("FR-01.11/AC41")
def test_mechanical_refactor_is_refused_when_the_body_really_changed():
    tid = f"{F}::test_old"
    v = _run(_manifest([tid]), _manifest([tid]), {F: _OLD}, {F: "def test_old():\n    assert 1 + 1 == 3\n"},
             exemptions=[_ex(tid, "mechanical-refactor")])
    assert [k for k, _t, _w in v.findings] == ["bad-exemption"]


@pytest.mark.covers("FR-01.11/AC41")
def test_new_malformed_and_unresolvable_tags_stop_but_legacy_ones_do_not():
    legacy = {"test": f"{F}::test_a", "raw": "FR-1.1", "reason": "non_canonical_fr_id"}
    fresh = {"test": f"{F}::test_b", "raw": "FR-2.2", "reason": "non_canonical_fr_id"}
    orphan = {"test": f"{F}::test_c", "tagged_fr": "FR-99.99", "reason": "fr_absent"}
    v = _run(_manifest(invalid=[legacy]), _manifest(invalid=[legacy, fresh], orphans=[orphan]), {}, {})
    assert sorted((k, t) for k, t, _w in v.findings) == [
        ("invalid-tag", f"{F}::test_b"), ("unresolved-tag", f"{F}::test_c")]


@pytest.mark.covers("FR-01.11/AC41")
def test_new_tag_outside_the_expected_frs_warns_and_inside_does_not():
    tid = f"{F}::test_new"
    v = _run(_manifest(), _manifest(links=[tid]), {}, {}, expected={"FR-01.03"})
    assert v.findings == [] and v.tagged_new == [tid] and "outside" in v.warnings[0]
    assert _run(_manifest(), _manifest(links=[tid]), {}, {}, expected={"FR-01.11"}).warnings == []


@pytest.mark.covers("FR-01.11/AC41")
def test_ts_body_digest_ignores_comments_whitespace_and_the_title():
    a = "test('one', async ({ page }) => {\n  // note\n  await page.goto('/');\n});\n"
    b = "test(\n  'two',\n  async ({ page }) => {\n    await page.goto('/');   /* moved */\n  },\n);\n"
    assert body_digests(a, "e2e/x.spec.ts", "one") == body_digests(b, "e2e/x.spec.ts", "two") != ()


@pytest.mark.covers("FR-01.11/AC41")
def test_would_collect_follows_pytest_rules():
    src = ("import pytest\n\n@pytest.fixture\ndef test_data():\n    return 1\n\n"
           "def test_real():\n    pass\n\nclass TestA:\n    def test_m(self):\n        pass\n")
    assert would_collect(src, F, "test_real") and would_collect(src, F, "test_m")
    assert not would_collect(src, F, "test_data")
    assert would_collect("test('x', () => {});", "e2e/a.spec.ts", "x")


@pytest.mark.covers("FR-01.11/AC41")
@pytest.mark.parametrize("head_body", [
    "    assert combine(a, b) == combine(b, a) + 1\n",     # one call site swapped
    "    assert combine(a, a) == combine(b, a)\n",         # renamed onto a name already in use
    "    assert other(a, b) == combine(b, a)\n",           # one call replaced, not renamed throughout
])
def test_mechanical_refactor_refuses_anything_but_a_consistent_rename(head_body):
    base_src = "def test_x(a, b):\n    assert combine(a, b) == combine(b, a)\n"
    tid = f"{F}::test_x"
    v = _run(_manifest([tid]), _manifest([tid]), {F: base_src}, {F: "def test_x(a, b):\n" + head_body},
             exemptions=[_ex(tid, "mechanical-refactor")])
    assert [k for k, _t, _w in v.findings] == ["bad-exemption"], head_body


@pytest.mark.covers("FR-01.11/AC41")
def test_one_vanished_test_explains_only_one_moved_copy():
    other = "tests/test_other.py"
    head_src = _OLD + "\n\n" + _OLD.replace("test_old", "test_copy")
    v = _run(_manifest([f"{F}::test_old"]), _manifest([f"{other}::test_old", f"{other}::test_copy"]),
             {F: _OLD}, {F: "", other: head_src})
    assert v.moved == [(f"{F}::test_old", f"{other}::test_old")]
    assert [(k, t) for k, t, _w in v.findings] == [("untagged-added", f"{other}::test_copy")]


@pytest.mark.covers("FR-01.11/AC41")
def test_a_test_class_with_an_init_is_not_collected_so_its_methods_are_helpers():
    src = "class TestBuilder:\n    def __init__(self):\n        self.x = 1\n\n    def test_make(self):\n        return 1\n"
    assert not would_collect(src, F, "test_make")


@pytest.mark.covers("FR-01.11/AC41")
def test_a_name_made_ambiguous_inside_one_file_stops():
    head_src = "class TestA:\n    def test_x(self):\n        assert 1\n\n\nclass TestB:\n    def test_x(self):\n        assert 2\n"
    tid = f"{F}::test_x"
    v = _run(_manifest(), _manifest(links=[tid]), {F: ""}, {F: head_src})
    assert [(k, t) for k, t, _w in v.findings] == [("ambiguous-name", tid)]


@pytest.mark.covers("FR-01.11/AC41")
def test_fixture_repo_malformed_and_orphan_tags_are_not_findings():
    fx = "plugins/x/tests/fixtures/repo/tests/test_fake.py::test_fake"
    v = _run(_manifest(), _manifest(invalid=[{"test": fx, "raw": "FR-1", "reason": "x"}],
                                     orphans=[{"test": fx, "tagged_fr": "FR-99.99", "reason": "fr_absent"}]), {}, {})
    assert v.findings == []


@pytest.mark.covers("FR-01.11/AC41")
def test_touched_counts_edited_tagged_tests_so_the_share_denominator_is_honest():
    tagged = f"{F}::test_tagged"
    base_src = "def test_tagged():\n    assert 1\n"
    v = _run(_manifest(links=[tagged]), _manifest(links=[tagged]), {F: base_src}, {F: base_src.replace("1", "2")})
    assert v.touched == {tagged} and v.findings == []


@pytest.mark.covers("FR-01.11/AC41")
def test_a_new_binding_on_an_existing_test_outside_the_expected_frs_warns():
    tid = f"{F}::test_old"
    base_m = _manifest(links=[tid])
    head_m = _manifest(links=[tid])
    head_m["requirements"]["01::FR-01.03"] = {"tests": {"unit": [{"id": tid, "path": tid}]}, "acs": {}}
    v = _run(base_m, head_m, {F: _OLD}, {F: _OLD}, expected={"FR-01.11"})
    assert any("FR-01.03" in w for w in v.warnings)


@pytest.mark.covers("FR-01.11/AC41")
def test_a_bom_does_not_hide_a_test_from_the_digest():
    assert body_digests("\ufeff" + _OLD, F, "test_old") == body_digests(_OLD, F, "test_old") != ()
    assert not would_collect("\ufeffclass Helpers:\n    def test_x(self):\n        pass\n", F, "test_x")
