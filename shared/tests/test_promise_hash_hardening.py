"""Blind spots of the promise fingerprint that the P2p reviews found and the hardening iterate closed (programme P21)."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest


pytestmark = pytest.mark.covers("FR-01.09/AC14")  # test support for the changelog pilot (promise-hash hardening); same tag as test_promise_hash.py
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared" / "testkit"))

import promise_hash as ph  # noqa: E402
import promise_lock as pl  # noqa: E402


def fp(source: str, conftests=()) -> str:
    return ph.fingerprint("test_it", source, conftests)


def test_an_import_binding_the_test_reaches_is_hashed_so_an_alias_swap_changes_it():
    plain = "from . import oracle\n\n\ndef test_it():\n    oracle.check()\n"
    aliased = plain.replace("import oracle", "import scenario_support as oracle")
    assert fp(aliased) != fp(plain)
    assert fp(plain.replace("from . import", "from .. import")) != fp(plain)  # another package level
    assert fp("import json as oracle\n\n\ndef test_it():\n    oracle.check()\n") != fp("import os as oracle\n\n\ndef test_it():\n    oracle.check()\n")
    assert fp(plain + "from . import driver_replay\n") == fp(plain)  # an import nothing reaches stays out
    assert fp("from . import a, oracle\n\n\ndef test_it():\n    oracle.check()\n") == fp(plain)  # one name of a multi-name import


def test_an_import_in_a_conftest_helper_is_hashed_too():
    source = "def test_it(shared):\n    assert shared\n"
    conftest = "import pytest\nfrom json import dumps as dump\n\n\n@pytest.fixture\ndef shared():\n    return dump({})\n"
    assert fp(source, [conftest]) != fp(source, [conftest.replace("dumps as dump", "loads as dump")])


def test_a_module_level_rebinding_of_a_def_changes_it_and_so_does_the_order():
    base = "def h():\n    assert 1\n\n\ndef test_it():\n    h()\n"
    assert fp(base + "\nh = lambda: None\n") != fp(base)
    first = "h = lambda: None\n\n\ndef h():\n    assert 1\n\n\ndef test_it():\n    h()\n"
    assert fp(first) != fp(base) and fp(first) != fp(base + "\nh = lambda: None\n")
    twice = "def h():\n    assert 1\n\n\ndef h():\n    assert 2\n\n\ndef test_it():\n    h()\n"
    assert fp(twice) != fp(twice.replace("assert 1", "assert 3"))  # the first of two defs counts, not only the last


def test_a_rebound_test_name_is_refused():
    with pytest.raises(ValueError, match="more than once"):
        ph.closure("test_it", "def test_it():\n    assert 1\n\n\ntest_it = None\n")


FIXTURE = "import pytest\n\n\n@pytest.fixture({args})\ndef guard():\n    return 1\n"


def test_autouse_counts_unless_it_is_the_literal_false():
    source = "def test_it():\n    pass\n"
    plain = fp(source)
    assert fp(source, [FIXTURE.format(args="autouse=False")]) == plain
    for args in ("autouse=True", "autouse=ENABLED", "autouse=1", "autouse=not False", "**OPTIONS"):
        assert fp(source, [FIXTURE.format(args=args)]) != plain, args
    assert fp(source, [FIXTURE.format(args="")]) == plain  # a fixture nobody asks for


def test_a_module_level_pytest_hook_is_part_of_every_closure():
    source = "def test_it():\n    pass\n"
    hook = "def pytest_generate_tests(metafunc):\n    metafunc.parametrize('x', [1])\n"
    assert fp(source, [hook]) != fp(source) and fp(source, [hook]) != fp(source, [hook.replace("[1]", "[2]")])
    assert fp(hook + "\n\n" + source) != fp(source)  # a hook of the test module itself
    assert fp(source, ["def helper_not_a_hook():\n    pass\n"]) == fp(source)


def test_pytestmark_is_read_from_assign_annassign_and_augassign_alike():
    covers = "pytest.mark.covers('FR-01.09/AC01')"
    for head in (f"pytestmark = {covers}", f"pytestmark: object = {covers}", f"pytestmark = []\npytestmark += [{covers}]"):
        source = f"import pytest\n\n{head}\n\n\ndef test_it():\n    pass\n"
        assert ph.covers_of("test_it", source) == ["FR-01.09/AC01"], head
    skip = "pytest.mark.skip(reason='later')"
    plain = fp("import pytest\n\n\ndef test_it():\n    pass\n")
    for head in (f"pytestmark: object = {skip}", f"pytestmark = []\npytestmark += [{skip}]"):
        assert fp(f"import pytest\n\n{head}\n\n\ndef test_it():\n    pass\n") != plain, head


F_SOURCE = textwrap.dedent('''
    PRICE = 3.14159


    def test_it():
        name = "w"
        text = (f"{name!r:>8} costs " f"{PRICE:.2f}" f" {{{name}}} " "tail" f"{'nested ' + f'{name}'}")
        assert text == "x"
''')
F_DIGEST = "d486d538515fd3a85eb1725a569015944b5366f4e1306327e8b440321fec14f0"


def test_a_pinned_digest_catches_interpreter_drift_in_the_serialization():
    """Computed on CPython 3.11.15 (Windows); the same digest came out on 3.12.13 and 3.13.13. A different digest on another interpreter (3.12 changed the f-string
    grammar) means a lock written on one machine reads as a diff on another."""
    assert fp(F_SOURCE) == F_DIGEST


def test_a_lock_entry_is_keyed_by_path_and_name_and_a_missing_name_is_a_failure():
    a = "import pytest\n\n\n@pytest.mark.covers('FR-01.09/AC01')\ndef test_one():\n    assert 1\n"
    sources = {"pkg/test_a.py": a, "pkg/test_b.py": a}  # the same test name in two files is two entries, never one
    lock = {pl.lock_key(path, "test_one"): pl.lock_entry("test_one", src) for path, src in sources.items()}
    assert set(lock) == {"pkg/test_a.py::test_one", "pkg/test_b.py::test_one"}
    assert pl.lock_problems(lock, sources) == []
    extra = {**sources, "pkg/test_a.py": a + "\n\n@pytest.mark.covers('FR-01.09/AC01')\ndef test_two():\n    assert 1\n"}
    assert any("pkg/test_a.py::test_two" in p and "not in the lock" in p for p in pl.lock_problems(lock, extra))
    gone = {**lock, "pkg/test_a.py::test_gone": lock["pkg/test_a.py::test_one"]}
    assert any("test_gone" in p and "missing" in p for p in pl.lock_problems(gone, sources))
    changed = {"pkg/test_a.py": a.replace("assert 1", "assert 2"), "pkg/test_b.py": a}
    assert any("test_a.py::test_one" in p and "differs" in p for p in pl.lock_problems(lock, changed))
