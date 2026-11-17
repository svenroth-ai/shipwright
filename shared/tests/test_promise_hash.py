"""The promise fingerprint (``shared/testkit/promise_hash.py``): what it ignores, what it must notice, how AC ids resolve."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest


pytestmark = pytest.mark.covers("FR-01.09/AC14")  # test support for the changelog pilot (programme P2p); same tag as the P2a harness tests, see the P2p FINDINGS note
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "shared" / "testkit"))

import promise_hash as ph  # noqa: E402

BASE = textwrap.dedent('''
    import json
    import pytest

    LIMIT = 3


    def helper(value):
        """Says what it does."""
        assert value < LIMIT, "too large"


    @pytest.fixture
    def thing(tmp_path):
        return tmp_path / "x"


    @pytest.mark.covers("FR-01.09/AC04")
    def test_it(thing):
        """A promise."""
        helper(1)  # fine
        assert thing.name == "x"
''')


def fp(source: str, conftests=()) -> str:
    return ph.fingerprint("test_it", source, conftests)


def test_formatting_comments_docstrings_imports_and_markers_do_not_change_it():
    reformatted = BASE.replace("import json\nimport pytest", "import pytest\nimport json\nimport os")
    reformatted = reformatted.replace('"""A promise."""', '"""Another sentence."""').replace("# fine", "# changed")
    reformatted = reformatted.replace('assert thing.name == "x"', "assert (\n        thing.name\n        ==\n        'x'\n    )")
    reformatted = reformatted.replace('@pytest.mark.covers("FR-01.09/AC04")', '@pytest.mark.covers("FR-01.09/AC05")')
    assert fp(reformatted) == fp(BASE)


def test_the_tests_own_name_is_not_part_of_it():
    assert ph.fingerprint("test_other", BASE.replace("def test_it", "def test_other")) == fp(BASE)


def test_an_asserted_value_or_a_deleted_assertion_changes_it():
    assert fp(BASE.replace('== "x"', '== "y"')) != fp(BASE)
    assert fp(BASE.replace('    assert thing.name == "x"\n', "")) != fp(BASE)


def test_an_assertion_inside_a_helper_changes_it():
    assert fp(BASE.replace("value < LIMIT", "value <= LIMIT")) != fp(BASE)
    assert fp(BASE.replace('"too large"', '"too big"')) != fp(BASE)


def test_a_constant_the_test_reaches_through_a_helper_changes_it_and_an_unused_one_does_not():
    assert fp(BASE.replace("LIMIT = 3", "LIMIT = 4")) != fp(BASE)
    assert fp(BASE + "\nUNUSED = 1\n\n\ndef unused():\n    assert False\n") == fp(BASE)


def test_a_fixture_the_test_requests_is_included_and_a_parametrize_is_kept():
    assert fp(BASE.replace('tmp_path / "x"', 'tmp_path / "z"')) != fp(BASE)
    param = BASE.replace('@pytest.mark.covers("FR-01.09/AC04")', '@pytest.mark.parametrize("n", [1, 2])')
    assert fp(param) != fp(BASE)
    assert fp(param.replace("[1, 2]", "[1, 3]")) != fp(param)


def test_a_conftest_fixture_is_included_but_a_plain_conftest_function_is_not():
    source = "def test_it(shared):\n    assert shared == 1\n"
    plain = "import pytest\n\n\n@pytest.fixture\ndef shared():\n    return 1\n"
    assert fp(source, [plain]) != fp(source, [plain.replace("return 1", "return 2")])
    assert fp(source, [plain]) != fp(source)
    unrelated = plain + "\n\ndef helper():\n    return 5\n"
    assert fp(source, [unrelated]) == fp(source, [plain])


def test_a_helper_chain_is_followed_to_its_end():
    chain = "def a():\n    return b()\n\n\ndef b():\n    assert 1 == 1\n\n\ndef test_it():\n    a()\n"
    assert fp(chain.replace("1 == 1", "1 == 2")) != fp(chain)


def test_the_serialization_does_not_carry_interpreter_specific_fields():
    parts = ph.closure("test_it", BASE)
    assert "type_params" not in str(ph._canon(parts["helper"]))


def test_a_missing_test_is_named():
    with pytest.raises(ValueError, match="test_gone"):
        ph.closure("test_gone", BASE)


def test_covers_ids_come_from_the_test_and_the_module_mark():
    source = "import pytest\n\npytestmark = pytest.mark.covers('FR-01.09/AC01')\n\n\n@pytest.mark.covers('FR-01.09/AC02', 'FR-01.09/AC03')\ndef test_it():\n    pass\n"
    assert sorted(ph.covers_of("test_it", source)) == ["FR-01.09/AC01", "FR-01.09/AC02", "FR-01.09/AC03"]


SPEC = "# Spec\n\n## AC-Move-Map\n\n| Old id | New id |\n|---|---|\n| `FR-01.11/AC21` | `FR-01.22/AC21` |\n| `FR-01.22/AC21` | `FR-01.23/AC21` |\n\n## Other\n\n| `FR-01.09/AC01` | `FR-01.99/AC01` |\n"


def test_ac_ids_resolve_through_the_move_map_to_the_end_of_a_chain():
    moves = ph.parse_move_map(SPEC)
    assert moves == {"FR-01.11/AC21": "FR-01.22/AC21", "FR-01.22/AC21": "FR-01.23/AC21"}  # the row under another heading is not a move
    assert ph.resolve_acs(["FR-01.11/AC21", "FR-01.09/AC01"], moves) == ["FR-01.09/AC01", "FR-01.23/AC21"]
    assert ph.resolve_ac("FR-01.11/AC21", {"FR-01.11/AC21": "FR-01.11/AC21"}) == "FR-01.11/AC21"  # a loop ends


def test_the_lock_entry_keeps_the_ac_id_outside_the_hash():
    source = BASE.replace("FR-01.09/AC04", "FR-01.11/AC21")
    moved = ph.lock_entry("test_it", source, SPEC)
    assert moved["acs"] == ["FR-01.23/AC21"]
    assert moved["hash"] == ph.lock_entry("test_it", BASE, "")["hash"]  # a re-anchor is an id change, never a body change


def test_it_reads_the_same_move_map_as_the_repository_parser():
    from lib import ac_move_map
    assert ph.parse_move_map(SPEC) == ac_move_map.parse_move_map(SPEC)
    assert ph.resolve_ac("FR-01.11/AC21", ph.parse_move_map(SPEC)) == ac_move_map.resolve_ac("FR-01.11/AC21", ac_move_map.parse_move_map(SPEC))


def test_any_mark_but_covers_changes_it():
    for weaker in ('@pytest.mark.skip(reason="later")', '@pytest.mark.xfail', '@pytest.mark.skipif(True, reason="x")'):
        assert fp(BASE.replace('@pytest.mark.covers("FR-01.09/AC04")', weaker)) != fp(BASE.replace('@pytest.mark.covers("FR-01.09/AC04")', ""))
    assert fp(BASE.replace('@pytest.mark.covers("FR-01.09/AC04")', "@pytest.mark.slow")) != fp(BASE.replace('@pytest.mark.covers("FR-01.09/AC04")', ""))  # CI deselects slow
    assert fp(BASE.replace('@pytest.mark.covers("FR-01.09/AC04")', '@pytest.mark.covers("FR-01.09/AC09")')) == fp(BASE)


def test_an_autouse_fixture_is_part_of_every_test_and_a_malformed_or_missing_ac_id_is_refused():
    source = "def test_it():\n    pass\n"
    auto = "import pytest\n\n\n@pytest.fixture(autouse=True)\ndef guard():\n    return 1\n"
    assert fp(source, [auto]) != fp(source) and fp(source, [auto]) != fp(source, [auto.replace("return 1", "return 2")])
    with pytest.raises(ValueError):
        ph.lock_entry("test_it", source)  # no covers id
    with pytest.raises(ValueError):
        ph.lock_entry("test_it", "import pytest\n\n\n@pytest.mark.covers('AC4')\ndef test_it():\n    pass\n")


def test_a_plain_helper_inside_a_conftest_is_followed_once_a_fixture_reaches_it():
    source = "def test_it(shared):\n    assert shared == 1\n"
    conftest = "import pytest\n\nLIMIT = 1\n\n\ndef build():\n    assert LIMIT == 1\n    return 1\n\n\n@pytest.fixture\ndef shared():\n    return build()\n"
    assert fp(source, [conftest]) != fp(source, [conftest.replace("LIMIT == 1", "LIMIT >= 1")])
    assert fp(source, [conftest]) != fp(source, [conftest.replace("LIMIT = 1", "LIMIT = 2")])


def test_a_module_level_skip_or_xfail_changes_every_test_but_covers_does_not():
    plain = "import pytest\n\n\ndef test_it():\n    assert 1\n"
    assert fp("import pytest\n\npytestmark = pytest.mark.skip(reason='later')\n\n\ndef test_it():\n    assert 1\n") != fp(plain)
    assert fp("import pytest\n\npytestmark = [pytest.mark.xfail]\n\n\ndef test_it():\n    assert 1\n") != fp(plain)
    assert fp("import pytest\n\npytestmark = pytest.mark.covers('FR-01.09/AC01')\n\n\ndef test_it():\n    assert 1\n") == fp(plain)


def test_a_fixture_named_by_usefixtures_is_followed_by_its_string_name():
    source = "import pytest\n\n\n@pytest.mark.usefixtures('guard')\ndef test_it():\n    pass\n"
    conftest = "import pytest\n\n\n@pytest.fixture\ndef guard():\n    assert True\n"
    assert fp(source, [conftest]) != fp(source, [conftest.replace("True", "False")])


def test_the_same_name_in_the_test_module_and_a_conftest_is_hashed_in_both_places():
    source = "LIMIT = 1\n\n\ndef test_it(shared):\n    assert LIMIT == shared\n"
    conftest = "import pytest\n\nLIMIT = 5\n\n\n@pytest.fixture\ndef shared():\n    return LIMIT\n"
    assert fp(source, [conftest]) != fp(source, [conftest.replace("LIMIT = 5", "LIMIT = 6")])
    assert fp(source, [conftest]) != fp(source.replace("LIMIT = 1", "LIMIT = 2"), [conftest])


def test_none_is_told_apart_from_its_neighbours():
    prints = {fp(f"def test_it(x):\n    {body}\n") for body in ("assert x is None", "assert x is not None", "assert x == 0", "assert x == False", "assert x")}
    assert len(prints) == 5
    assert fp("def test_it():\n    f(None)\n") != fp("def test_it():\n    f(0)\n")
    assert fp("def test_it():\n    def f(a=None):\n        pass\n") != fp("def test_it():\n    def f(a):\n        pass\n")


def test_every_binding_of_a_module_constant_counts_not_only_the_last():
    base = "LIMIT = 3\nLIMIT = LIMIT + 1\n\n\ndef test_it():\n    assert LIMIT\n"
    assert fp(base) != fp(base.replace("LIMIT = 3", "LIMIT = 4"))  # the first of two bindings
    aug = "CASES = [1]\nCASES += [2]\n\n\ndef test_it():\n    assert CASES\n"
    assert fp(aug) != fp(aug.replace("+= [2]", "+= [3]"))
    tup = "A, B = 1, 2\n\n\ndef test_it():\n    assert B\n"
    assert fp(tup) != fp(tup.replace("1, 2", "1, 3"))


def test_a_fixture_requested_by_its_alias_is_found():
    source = "def test_it(thing):\n    pass\n"
    conftest = "import pytest\n\n\n@pytest.fixture(name='thing')\ndef _thing_impl():\n    assert True\n"
    assert fp(source, [conftest]) != fp(source, [conftest.replace("True", "False")])
