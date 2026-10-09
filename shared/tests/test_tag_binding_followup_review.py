"""Test-tag gate follow-up, part 2: cases that came out of the plan, architecture and code reviews.

Unit cases drive the identity layer on source text; the integration cases build a real git repo in
``tmp_path`` and run the gate through the real compliance collector (U1 follow-up, FR-01.11/AC42).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))  # after shared/scripts: tests/ has its own `tools`

import pytest  # noqa: E402

from lib.fr_tag_grammar import parse_ts_js  # noqa: E402
from test_tag_binding_gate_integration import RUN, _py_base, _repo  # noqa: E402
from tools.verifiers import tag_binding_gate as gate  # noqa: E402
from tools.verifiers._tag_binding_identity import body_digests, mechanically_renamed  # noqa: E402
from lib.ts_lexer import lex  # noqa: E402

TS = "tests/app.test.ts"
TSX = "tests/app.test.tsx"
_CFG = "shipwright_compliance_config.json"


def _digest(text: str, name: str, path: str = TS):
    return body_digests(text, path, name)


# --- triage of the plan / architecture reviews ---------------------------------------------------

@pytest.mark.covers("FR-01.11/AC42")
def test_a_covers_tag_is_not_an_edit_but_any_other_mark_or_decorator_is():
    plain = "def test_old():\n    assert 1\n"
    path = "tests/test_m.py"
    assert _digest(plain, "test_old", path) == _digest('@pytest.mark.covers("FR-01.11")\n' + plain, "test_old", path)
    for dec in ("@patch('m.x')", "@pytest.mark.slow", "@pytest.mark.skip"):
        assert _digest(plain, "test_old", path) != _digest(dec + "\n" + plain, "test_old", path), dec


@pytest.mark.covers("FR-01.11/AC42")
def test_lexer_combinations_keep_the_rest_of_the_body_visible():
    body = ("it('t', () => { render(<A b={`it's ${x / 2}`}><p>{y}</p> isn't</A>); const q = a / b / c;"
            " expect(q).toBe(/x'y/.test(z)); const n = 1; });\n")
    assert _digest(body, "t", TSX) != _digest(body.replace("n = 1", "n = 2"), "t", TSX)
    assert _digest(body, "t", TSX) != _digest(body.replace("a / b / c", "a / b"), "t", TSX)
    generic = "it('t', () => { const f = <T,>(v: T) => v; const n = 1; });\n"
    assert _digest(generic, "t") != _digest(generic.replace("n = 1", "n = 2"), "t")


@pytest.mark.covers("FR-01.11/AC42")
def test_adding_a_row_to_a_legacy_untagged_each_table_stops_through_the_real_gate(tmp_path):
    old = "it.each([1, 2])('adds %i', (n) => { expect(n).toBe(n); });\n"
    base = {**_py_base(), "tests/legacy.test.ts": old}
    root, sha = _repo(tmp_path, base, {"tests/legacy.test.ts": old.replace("[1, 2]", "[1, 2, 3]")})
    result = gate.check_test_tag_binding(root, RUN, sha)
    assert result.ok is False and "untagged-modified" in result.detail, result.detail


@pytest.mark.covers("FR-01.11/AC42")
def test_head_dropping_an_exclude_dir_surfaces_the_new_test_in_it(tmp_path):
    base = {**_py_base(), _CFG: json.dumps({"traceability": {"exclude_dirs": ["fixtures", "hidden"]}})}
    head = {_CFG: json.dumps({"traceability": {"exclude_dirs": ["fixtures"]}}),
            "tests/hidden/test_h.py": "def test_hidden():\n    pass\n"}
    root, sha = _repo(tmp_path, base, head)
    result = gate.check_test_tag_binding(root, RUN, sha)
    assert result.ok is False and "tests/hidden/test_h.py::test_hidden" in result.detail, result.detail


@pytest.mark.covers("FR-01.11/AC42")
def test_a_head_exclude_dir_cannot_hide_a_new_test_when_base_has_no_config(tmp_path):
    head = {_CFG: json.dumps({"traceability": {"exclude_dirs": ["hidden"]}}),
            "tests/hidden/test_h.py": "def test_hidden():\n    pass\n"}
    root, sha = _repo(tmp_path, _py_base(), head)
    assert gate.check_test_tag_binding(root, RUN, sha).ok is False


@pytest.mark.covers("FR-01.11/AC42")
def test_class_decorators_module_marks_and_it_vs_test_in_the_digest():
    cls = "class TestA:\n    def test_old(self):\n        assert 1\n"
    path = "tests/test_m.py"
    assert _digest(cls, "test_old", path) != _digest('@unittest.skip("x")\n' + cls, "test_old", path)
    fn = "def test_old():\n    assert 1\n"
    assert _digest(fn, "test_old", path) != _digest("pytestmark = pytest.mark.skip\n" + fn, "test_old", path)
    assert _digest(fn, "test_old", path) != _digest("pytestmark = pytest.mark.slow\n" + fn, "test_old", path)
    assert _digest(fn, "test_old", path) == _digest('pytestmark = pytest.mark.covers("FR-01.11")\n' + fn, "test_old", path)
    assert _digest(cls, "test_old", path) != _digest(
        cls.replace("    def", "    pytestmark = [pytest.mark.skip]\n    def"), "test_old", path)
    assert _digest(fn, "test_old", path) != _digest("pytestmark: list = [pytest.mark.skip]\n" + fn, "test_old", path)
    assert _digest("pytestmark = []\n" + fn, "test_old", path) != _digest(
        "pytestmark = []\npytestmark += [pytest.mark.skip]\n" + fn, "test_old", path)
    body = "('t', () => { expect(1).toBe(1); });\n"
    assert _digest("it" + body, "t") == _digest("test" + body, "t")


@pytest.mark.covers("FR-01.11/AC42")
def test_a_covers_tag_spelled_with_a_mark_import_is_not_a_body_edit():
    plain = "def test_old():\n    assert 1\n"
    tagged = '@mark.covers("FR-02.01")\n' + plain
    assert _digest(plain, "test_old", "tests/test_m.py") == _digest(tagged, "test_old", "tests/test_m.py")


@pytest.mark.covers("FR-01.11/AC42")
def test_an_annotated_module_pytestmark_skip_is_part_of_the_digest():
    fn = "def test_old():\n    assert 1\n"
    marked = "pytestmark: list = [pytest.mark.skip(reason='x')]\n" + fn
    assert _digest(fn, "test_old", "tests/test_m.py") != _digest(marked, "test_old", "tests/test_m.py")


@pytest.mark.covers("FR-01.11/AC42")
def test_consecutive_each_tests_keep_their_own_table_and_tags():
    first = "it.each([\n  [1, 2],\n])('first %i', (a, b) => {\n  expect(a).toBe(b);\n});\n"
    second = "it.each([\n  [3, 4],\n])('second %i', (a, b) => {\n  expect(a).toBe(b);\n});\n"
    text = first + second
    edited = text.replace("[1, 2]", "[1, 9]")
    assert _digest(text, "second %i") == _digest(edited, "second %i")
    assert _digest(text, "first %i") != _digest(edited, "first %i")
    assert len(_digest(text, "second %i")) == 1


@pytest.mark.covers("FR-01.11/AC42")
@pytest.mark.parametrize("pathological", ["${`" * 40, "<b>{" * 40, "`${" * 200], ids=["templates", "elements", "dollars"])
def test_unclosed_nesting_lexes_in_bounded_time(pathological):
    import time
    started = time.perf_counter()
    lex(pathological, 0, True)
    assert time.perf_counter() - started < 1.0


@pytest.mark.covers("FR-01.11/AC42")
def test_same_line_second_each_test_and_parametrize_rename():
    line = "it.each([1])('a', (n) => {}); it.each([2])('b', (n) => { expect(n).toBe(2); });\n"
    assert len(_digest(line, "b")) == 1
    assert _digest(line, "b") != _digest(line.replace("toBe(2)", "toBe(3)"), "b")
    base = '@pytest.mark.parametrize("value", [1])\ndef test_a(value):\n    assert value\n'
    head = '@pytest.mark.parametrize("v", [1])\ndef test_a(v):\n    assert v\n'
    assert mechanically_renamed(base, head, "tests/test_m.py", "test_a")


@pytest.mark.covers("FR-01.11/AC42")
def test_a_tag_inside_an_each_row_is_not_the_tests_own_tag():
    row_tag = "it.each([{ tag: ['@FR-02.01'] }])('shows %o', (row) => {});\n"
    own_tag = "it.each([{ tag: ['news'] }])('shows %o', { tag: ['@FR-02.01'] }, (row) => {});\n"
    assert not parse_ts_js(row_tag, "t.spec.ts").hits
    assert [h.fr_id for h in parse_ts_js(own_tag, "t.spec.ts").hits] == ["FR-02.01"]
