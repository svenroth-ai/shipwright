"""BP unit BL0 - the touched-set library: T-spec, T-test, 'moved', static attribution, scope rule.

Real git throughout (the library's only input is a diff). Seeded cases follow the brief's
section 4: S1 (assertion edit held), S2 (in scope passes), S3/S3b/S3c (move, move+edit,
parametrize case), S4 (module-level covers), S5 (fixture), S8 (marker-only spec edits pass).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _baseline_repo import SPEC, SPEC_TEXT, commit, make_repo  # noqa: E402
from verifiers._baseline_touch_core import evaluate_hold, touched_set  # noqa: E402
from verifiers._baseline_touch_git import GitRev  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")

TEST_A = '''import pytest


@pytest.mark.covers("FR-01.09/AC01")
def test_price():
    assert round(1.005, 2) == 1.0


@pytest.mark.covers("FR-01.10")
def test_other():
    assert 1 == 1


def test_untagged():
    assert True
'''

BASE = {SPEC: SPEC_TEXT, "pkg/tests/test_a.py": TEST_A}


def _two(tmp_path, base_files, head_files):
    root = make_repo(tmp_path, base_files)
    base = commit(root, {"README.md": "x"}, "pad")
    head = commit(root, head_files, "change")
    return touched_set(GitRev(root, base, head))


def test_assertion_edit_touches_its_fr(tmp_path):  # S1, S2
    t = _two(tmp_path, BASE, {"pkg/tests/test_a.py": TEST_A.replace("== 1.0", "== 1.01")})
    assert t.sources() == {"FR-01.09": {"test"}}
    assert evaluate_hold(t)["held"]
    assert not evaluate_hold(t, frozenset({"FR-01.09"}))["held"]


def test_untagged_test_edit_touches_nothing(tmp_path):
    t = _two(tmp_path, BASE, {"pkg/tests/test_a.py": TEST_A.replace("assert True", "assert 2")})
    assert not t.sources() and not evaluate_hold(t)["held"]


def test_docstring_and_comment_edits_are_not_modifications(tmp_path):
    new = TEST_A.replace("def test_price():\n", 'def test_price():\n    """doc."""\n    # note\n')
    t = _two(tmp_path, BASE, {"pkg/tests/test_a.py": new})
    assert not t.sources()


def test_pure_move_is_listed_not_touched(tmp_path):  # S3
    moved = TEST_A.replace("def test_price", "def test_price_renamed")
    t = _two(tmp_path, BASE, {"pkg/tests/test_a.py": None, "pkg/tests/test_b.py": moved})
    assert t.moved and not t.sources()


def test_move_with_changed_expected_value_is_touched(tmp_path):  # S3b
    changed = TEST_A.replace("== 1.0", "== 9.9")
    t = _two(tmp_path, BASE, {"pkg/tests/test_a.py": None, "pkg/tests/test_b.py": changed})
    assert "FR-01.09" in t.sources()


def test_changed_parametrize_case_is_a_modification(tmp_path):  # S3c
    base = TEST_A.replace("def test_price():", '@pytest.mark.parametrize("x", [1, 2])\ndef test_price(x):')
    t = _two(tmp_path, {SPEC: SPEC_TEXT, "pkg/tests/test_a.py": base},
             {"pkg/tests/test_a.py": base.replace("[1, 2]", "[1, 3]")})
    assert "FR-01.09" in t.sources()


def test_deleted_test_touches_its_fr(tmp_path):
    cut = TEST_A.split('@pytest.mark.covers("FR-01.10")')[0]
    t = _two(tmp_path, BASE, {"pkg/tests/test_a.py": cut})
    assert "FR-01.10" in t.sources()


def test_module_level_covers_binds_every_test_of_the_module(tmp_path):  # S4
    mod = 'import pytest\n\npytestmark = pytest.mark.covers("FR-01.10")\n\n\ndef test_x():\n    assert 1\n'
    t = _two(tmp_path, {SPEC: SPEC_TEXT, "pkg/tests/test_m.py": mod},
             {"pkg/tests/test_m.py": mod.replace("assert 1", "assert 2")})
    assert set(t.sources()) == {"FR-01.10"}


def test_fixture_change_touches_only_the_requesting_tests_frs(tmp_path):  # S5
    base = TEST_A + "\n\n@pytest.fixture\ndef rate():\n    return 1\n"
    base = base.replace("def test_other():", "def test_other(rate):")
    t = _two(tmp_path, {SPEC: SPEC_TEXT, "pkg/tests/test_a.py": base},
             {"pkg/tests/test_a.py": base.replace("return 1", "return 2")})
    assert t.sources() == {"FR-01.10": {"static"}}


def test_conftest_fixture_reaches_tests_in_its_directory_scope(tmp_path):
    conf = "import pytest\n\n\n@pytest.fixture\ndef rate():\n    return 1\n"
    test = 'import pytest\n\n\n@pytest.mark.covers("FR-01.09")\ndef test_a(rate):\n    assert rate\n'
    files = {SPEC: SPEC_TEXT, "pkg/tests/conftest.py": conf, "pkg/tests/test_a.py": test}
    t = _two(tmp_path, files, {"pkg/tests/conftest.py": conf.replace("return 1", "return 2")})
    assert set(t.sources()) == {"FR-01.09"}


def test_marker_only_spec_edits_pass(tmp_path):  # S8
    edited = SPEC_TEXT.replace("unit (inferred) |", "unit |").replace("[AC01] Given work", "[AC07] Given work")
    assert not _two(tmp_path, BASE, {SPEC: edited}).sources()


def test_reordered_criteria_are_not_a_change(tmp_path):
    a = "- (E) [AC01] Given work, when release, then a note exists.\n"
    b = "- (E) [AC02] Given nothing, when release, then it stops.\n"
    assert not _two(tmp_path, BASE, {SPEC: SPEC_TEXT.replace(a + b, b + a)}).sources()


def test_reworded_criterion_and_description_touch_their_fr(tmp_path):
    t = _two(tmp_path / "a", BASE, {SPEC: SPEC_TEXT.replace("then it stops", "then it carries on")})
    assert set(t.sources()) == {"FR-01.09"}
    t2 = _two(tmp_path / "b", BASE, {SPEC: SPEC_TEXT.replace("Keep evidence.", "Keep all evidence.")})
    assert set(t2.sources()) == {"FR-01.10"}


def test_new_fr_is_never_existing(tmp_path):
    added = SPEC_TEXT + "\n### FR-01.30 — New\n\n- (E) [AC01] Given x, when y, then z.\n"
    t = _two(tmp_path, BASE, {SPEC: added})
    assert "FR-01.30" in t.new_frs and not t.sources()


def test_digest_depends_on_the_touched_set_only(tmp_path):
    a = _two(tmp_path / "a", BASE, {"pkg/tests/test_a.py": TEST_A.replace("== 1.0", "== 2.0")})
    b = _two(tmp_path / "b", BASE, {"pkg/tests/test_a.py": TEST_A.replace("== 1.0", "== 3.0"), "x.md": "y"})
    assert a.digest() == b.digest()


def test_broad_changes_are_listed_not_held(tmp_path):
    t = _two(tmp_path, BASE, {"x.md": "y"})
    t.code = {"FR-01.09": {"s.py::helper"}, "FR-01.10": {"s.py::helper"}}
    t.fan_out = {"s.py::helper": {"FR-01.09", "FR-01.10"}}
    broad = evaluate_hold(t, n=1)
    assert broad["listed_broad"] == ["FR-01.09", "FR-01.10"] and not broad["held"]
    assert evaluate_hold(t, n=5)["held"]


def test_unreadable_evidence_fails_closed(tmp_path):
    t = _two(tmp_path, BASE, {"x.md": "y"})
    t.incomplete.append("unreadable test file pkg/tests/test_a.py@head")
    assert evaluate_hold(t)["held"]


def test_conftest_hook_and_deletion_reach_every_test_in_scope(tmp_path):
    conf = "def pytest_configure(config):\n    pass\n\n\ndef helper():\n    return 1\n"
    test = 'import pytest\n\n\n@pytest.mark.covers("FR-01.09")\ndef test_a():\n    assert 1\n'
    files = {SPEC: SPEC_TEXT, "pkg/tests/conftest.py": conf, "pkg/tests/test_a.py": test}
    hook = _two(tmp_path / "a", files, {"pkg/tests/conftest.py": conf.replace("pass", "config.x = 1")})
    gone = _two(tmp_path / "b", files, {"pkg/tests/conftest.py": None})
    assert set(hook.sources()) == {"FR-01.09"} and set(gone.sources()) == {"FR-01.09"}


def test_helper_module_change_reaches_every_importing_test_module(tmp_path):
    helper = "def b():\n    return 1\n\n\ndef a():\n    return b()\n"
    test = ('import pytest\nfrom pkg.tests.helpers import a\n\n\n@pytest.mark.covers("FR-01.10")\n'
            "def test_a():\n    assert a()\n")
    files = {SPEC: SPEC_TEXT, "pkg/tests/helpers.py": helper, "pkg/tests/test_a.py": test}
    t = _two(tmp_path, files, {"pkg/tests/helpers.py": helper.replace("return 1", "return 2")})
    assert set(t.sources()) == {"FR-01.10"}  # b changed, the test only calls a: still attributed


def test_fixture_chain_is_followed_to_the_requesting_tests(tmp_path):
    base = TEST_A + "\n\n@pytest.fixture\ndef inner():\n    return 1\n\n\n@pytest.fixture\ndef outer(inner):\n    return inner\n"
    base = base.replace("def test_other():", "def test_other(outer):")
    t = _two(tmp_path, {SPEC: SPEC_TEXT, "pkg/tests/test_a.py": base},
             {"pkg/tests/test_a.py": base.replace("return 1", "return 2")})
    assert set(t.sources()) == {"FR-01.10"}


def test_fixture_requested_by_string_is_attributed(tmp_path):
    base = TEST_A + "\n\n@pytest.fixture\ndef rate():\n    return 1\n"
    base = base.replace('@pytest.mark.covers("FR-01.10")', '@pytest.mark.covers("FR-01.10")\n@pytest.mark.usefixtures("rate")')
    t = _two(tmp_path, {SPEC: SPEC_TEXT, "pkg/tests/test_a.py": base},
             {"pkg/tests/test_a.py": base.replace("return 1", "return 2")})
    assert set(t.sources()) == {"FR-01.10"}


def test_setup_method_change_touches_every_test_of_the_class(tmp_path):
    cls = ('import pytest\n\n\nclass TestX:\n    def setup_method(self):\n        self.v = 1\n\n'
           '    @pytest.mark.covers("FR-01.09")\n    def test_a(self):\n        assert self.v\n')
    t = _two(tmp_path, {SPEC: SPEC_TEXT, "pkg/tests/test_c.py": cls},
             {"pkg/tests/test_c.py": cls.replace("self.v = 1", "self.v = 0")})
    assert set(t.sources()) == {"FR-01.09"}


def test_unparsable_test_file_fails_closed(tmp_path):
    t = _two(tmp_path, BASE, {"pkg/tests/test_a.py": "def test_x(:\n"})
    assert evaluate_hold(t)["held"] and any("test_a.py" in r for r in evaluate_hold(t)["incomplete"])


def test_unparsable_conftest_fails_closed(tmp_path):
    files = {SPEC: SPEC_TEXT, "pkg/tests/conftest.py": "X = 1\n", "pkg/tests/test_a.py": TEST_A}
    t = _two(tmp_path, files, {"pkg/tests/conftest.py": "def broken(:\n"})
    assert evaluate_hold(t)["held"]


def test_invalid_manifest_json_raises_rather_than_shrinking_the_catalog(tmp_path):
    root = make_repo(tmp_path, {SPEC: SPEC_TEXT, ".shipwright/compliance/test-traceability.json": "{not json"})
    base = commit(root, {"a.md": "1"}, "pad")
    head = commit(root, {"a.md": "2"}, "change")
    with pytest.raises(RuntimeError):
        touched_set(GitRev(root, base, head))


def test_newly_anchored_block_for_an_existing_fr_is_a_touch(tmp_path):
    extra = "\n### FR-01.10 - again\n\n- (E) [AC09] Given x, when y, then z.\n"
    t = _two(tmp_path, BASE, {SPEC: SPEC_TEXT + extra})
    assert "FR-01.10" in t.sources() and "FR-01.10" not in t.new_frs


def test_module_level_skip_call_touches_the_modules_frs(tmp_path):
    skipped = TEST_A.replace("import pytest\n", 'import pytest\n\npytest.skip("later", allow_module_level=True)\n', 1)
    t = _two(tmp_path, BASE, {"pkg/tests/test_a.py": skipped})
    assert {"FR-01.09", "FR-01.10"} <= set(t.sources())


def test_import_swap_in_a_test_module_touches_its_frs(tmp_path):
    base = "import pytest\nfrom pkg import impl\n\n\n" + TEST_A.split("\n\n\n", 1)[1]
    t = _two(tmp_path, {SPEC: SPEC_TEXT, "pkg/tests/test_a.py": base},
             {"pkg/tests/test_a.py": base.replace("from pkg import impl", "from pkg import impl_v2 as impl")})
    assert "FR-01.09" in t.sources()


def test_conftest_plugin_list_change_is_scope_wide(tmp_path):
    conf = 'pytest_plugins = ["a"]\n'
    test = 'import pytest\n\n\n@pytest.mark.covers("FR-01.09")\ndef test_a():\n    assert 1\n'
    files = {SPEC: SPEC_TEXT, "pkg/tests/conftest.py": conf, "pkg/tests/test_a.py": test}
    t = _two(tmp_path, files, {"pkg/tests/conftest.py": 'pytest_plugins = ["b"]\n'})
    assert set(t.sources()) == {"FR-01.09"}


def test_new_conftest_with_autouse_fixture_reaches_existing_tests(tmp_path):
    conf = "import pytest\n\n\n@pytest.fixture(autouse=True)\ndef env():\n    return 1\n"
    t = _two(tmp_path, BASE, {"pkg/tests/conftest.py": conf})
    assert {"FR-01.09", "FR-01.10"} <= set(t.sources())


def test_moved_and_retagged_test_touches_both_bindings(tmp_path):
    moved = TEST_A.replace('covers("FR-01.09/AC01")', 'covers("FR-01.10")').replace("test_price", "test_price_renamed")
    t = _two(tmp_path, BASE, {"pkg/tests/test_a.py": None, "pkg/tests/test_b.py": moved})
    assert {"FR-01.09", "FR-01.10"} <= set(t.sources())

