"""Test-tag gate follow-up: data-driven tests, base-side prune set, regex/JSX lexing, decorator edits.

Unit cases drive the identity layer on source text; the integration cases build a real git repo in
``tmp_path`` and run the gate through the real compliance collector (U1 follow-up, FR-01.11/AC42).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))  # after shared/scripts: tests/ has its own `tools`

import pytest  # noqa: E402

from lib.fr_tag_grammar import _TEST_DECL_RE, parse_ts_js  # noqa: E402
from test_tag_binding_gate_integration import RUN, _py_base, _repo  # noqa: E402
from tools.verifiers import tag_binding_gate as gate  # noqa: E402
from tools.verifiers._tag_binding_identity import body_digests, mechanically_renamed  # noqa: E402
from tools.verifiers._tag_binding_ts_lex import lex  # noqa: E402

TS = "tests/app.test.ts"
TSX = "tests/app.test.tsx"


def _digest(text: str, name: str, path: str = TS):
    return body_digests(text, path, name)


# --- (a) data-driven tests are declarations ------------------------------------------------------

@pytest.mark.covers("FR-01.11/AC42")
@pytest.mark.parametrize(("line", "title"), [
    ("it.each([1, 2])('adds %i', (n) => {", "adds %i"),
    ("  test.each([[1, 2], [3, 4]])('sums $a', ({ a }) => {", "sums $a"),
    ("it.skip.each([1])('skipped table', () => {", "skipped table"),
    ("test.each`a | b`('template %s', () => {", "template %s"),
    ("it.each(cases.map((c) => c.id))('nested call', () => {", "nested call"),
], ids=lambda _v: "c")
def test_a_data_driven_declaration_is_one_test_titled_by_its_literal_title(line, title):
    match = _TEST_DECL_RE.search(line)
    assert match and match.group("title") == title


@pytest.mark.covers("FR-01.11/AC42")
@pytest.mark.parametrize("line", [
    "describe.each([1])('suite', () => {",
    "test.describe.each([1])('suite', () => {",
    "// it.each([1])('commented', () => {",
    "test.step('a step', async () => {",
], ids=lambda _v: "c")
def test_suites_steps_and_comments_stay_non_declarations(line):
    assert _TEST_DECL_RE.search(line) is None


@pytest.mark.covers("FR-01.11/AC42")
def test_a_native_tag_on_a_data_driven_test_binds_to_the_test():
    res = parse_ts_js("it.each([1])('t', { tag: ['@FR-01.03'] }, () => {});\n", TS)
    assert [(h.fr_id, h.test, h.tag_source) for h in res.hits] == [("FR-01.03", f"{TS}::t", "native_tag")]


@pytest.mark.covers("FR-01.11/AC42")
def test_editing_a_table_row_or_the_modifier_is_an_edit_of_the_test():
    base = "it.each([[1, 2]])('adds', (a, b) => { expect(a + b).toBe(3); });\n"
    assert _digest(base, "adds") == _digest(base.replace("it.each", "it.each ").replace("\n", "\n\n"), "adds")
    assert _digest(base, "adds") != _digest(base.replace("[[1, 2]]", "[[1, 2], [2, 3]]"), "adds")
    assert _digest(base, "adds") != _digest(base.replace("it.each", "it.skip.each"), "adds")


@pytest.mark.covers("FR-01.11/AC42")
def test_a_wrapped_table_is_found_by_the_gate_and_a_plain_test_skip_is_an_edit():
    wrapped = "it.each([\n  [1, 2],\n  [3, 4],\n])('adds %i', (a, b) => {\n  expect(a).toBe(b);\n});\n"
    assert len(_digest(wrapped, "adds %i")) == 1
    plain = "test('t', () => { expect(1).toBe(1); });\n"
    assert _digest(plain, "t") != _digest(plain.replace("test(", "test.skip("), "t")


# --- (c) regex literals and JSX text -------------------------------------------------------------

@pytest.mark.covers("FR-01.11/AC42")
def test_the_lexer_reads_division_and_regex_literals_apart():
    assert [t.kind for t in lex("a / b / c")[0]] == ["id", "punct", "id", "punct", "id"]
    toks = lex("x = /a[/]b'c/gi.test(y)")[0]
    assert [t.text for t in toks if t.kind == "regex"] == ["/a[/]b'c/gi"]
    assert lex("return /x/")[0][-1].kind == "regex"


@pytest.mark.covers("FR-01.11/AC42")
def test_a_quote_inside_a_regex_literal_no_longer_hides_a_later_edit():
    body = "it('t', () => { expect(a).toMatch(/it's/); const n = 1; expect(c).toBe('ok'); });\n"
    assert _digest(body, "t") != _digest(body.replace("n = 1", "n = 2"), "t")
    assert _digest(body, "t") == _digest(body.replace("const n = 1;", "const n = 1; // note\n"), "t")


@pytest.mark.covers("FR-01.11/AC42")
def test_an_apostrophe_in_jsx_text_no_longer_hides_a_later_edit_and_the_text_itself_counts():
    body = "it('t', () => { render(<p>Don't panic</p>); const n = 1; expect(c).toBe('ok'); });\n"
    assert _digest(body, "t", TSX) != _digest(body.replace("n = 1", "n = 2"), "t", TSX)
    assert _digest(body, "t", TSX) != _digest(body.replace("Don't panic", "Do panic"), "t", TSX)
    assert _digest(body, "t", TSX) == _digest(body.replace("<p>Don't", "<p>  Don't"), "t", TSX)


@pytest.mark.covers("FR-01.11/AC42")
def test_jsx_expressions_stay_visible_to_the_rename_check():
    base = "it('t', () => { const el = 1; render(<Foo bar={el} label=\"it's\" />); });\n"
    head = base.replace("const el", "const node").replace("{el}", "{node}")
    assert mechanically_renamed(base, head, TSX, "t")
    assert not mechanically_renamed(base, head.replace("<Foo", "<Bar"), TSX, "t")


@pytest.mark.covers("FR-01.11/AC42")
def test_a_type_assertion_in_a_ts_file_is_not_jsx():
    body = "it('t', () => { const a = <Foo>b; const n = 1; });\n"
    assert _digest(body, "t") != _digest(body.replace("n = 1", "n = 2"), "t")


@pytest.mark.covers("FR-01.11/AC42")
def test_an_unclosed_element_falls_back_to_plain_tokens():
    toks = lex("x = <div>never closed", 0, True)[0]
    assert [t.text for t in toks][:3] == ["x", "=", "<"]


# --- (d) decorator edits are body edits ----------------------------------------------------------


@pytest.mark.covers("FR-01.11/AC42")
def test_removing_a_skip_or_swapping_parametrize_rows_changes_the_digest():
    skipped = '@pytest.mark.skip(reason="x")\ndef test_old():\n    assert 1\n'
    assert _digest(skipped, "test_old", "tests/test_m.py") != _digest(
        "def test_old():\n    assert 1\n", "test_old", "tests/test_m.py")
    rows = '@pytest.mark.parametrize("x", [1, 2])\ndef test_old(x):\n    assert x\n'
    assert _digest(rows, "test_old", "tests/test_m.py") != _digest(
        rows.replace("[1, 2]", "[3]"), "test_old", "tests/test_m.py")


@pytest.mark.covers("FR-01.11/AC42")
def test_a_covers_tag_or_a_class_tag_is_not_a_body_edit():
    plain = "def test_old():\n    assert 1\n"
    tagged = '@pytest.mark.covers("FR-02.01/AC01")\ndef test_old():\n    assert 1\n'
    assert _digest(plain, "test_old", "tests/test_m.py") == _digest(tagged, "test_old", "tests/test_m.py")
    cls = 'class TestA:\n    def test_old(self):\n        assert 1\n'
    tagged_cls = '@pytest.mark.covers("FR-02.01")\n' + cls
    assert _digest(cls, "test_old", "tests/test_m.py") == _digest(tagged_cls, "test_old", "tests/test_m.py")
    skipped_cls = '@pytest.mark.skip\n' + cls
    assert _digest(cls, "test_old", "tests/test_m.py") != _digest(skipped_cls, "test_old", "tests/test_m.py")


@pytest.mark.covers("FR-01.11/AC42")
def test_a_decorator_edit_on_a_legacy_test_stops_through_the_real_gate(tmp_path):
    base = {**_py_base(), "tests/test_a.py": '@pytest.mark.skip(reason="flaky")\ndef test_old():\n    assert 1 + 1 == 2\n'}
    root, sha = _repo(tmp_path, base, {"tests/test_a.py": "def test_old():\n    assert 1 + 1 == 2\n"})
    result = gate.check_test_tag_binding(root, RUN, sha)
    assert result.ok is False and "untagged-modified" in result.detail and "tests/test_a.py::test_old" in result.detail


# --- real git + collector -------------------------------------------------------------------------

_CFG = "shipwright_compliance_config.json"


@pytest.mark.covers("FR-01.11/AC42")
@pytest.mark.parametrize(("head_test", "ok"), [
    ("it.each([1, 2])('adds %i', (n) => { expect(n).toBe(n); });\n", False),
    ("it.each([\n  [1, 2],\n  [3, 4],\n])('wrapped %i', (a, b) => {\n  expect(a).toBe(a);\n});\n", False),
    ("it.each([1, 2])('adds %i', { tag: ['@FR-02.01'] }, (n) => { expect(n).toBe(n); });\n", True),
], ids=lambda _v: "c")
def test_an_untagged_data_driven_ts_test_stops_and_a_tagged_one_passes(tmp_path, head_test, ok):
    base = {**_py_base(), "tests/legacy.test.ts": "test('legacy', () => { expect(1).toBe(1); });\n"}
    root, sha = _repo(tmp_path, base, {"tests/legacy.test.ts": base["tests/legacy.test.ts"] + head_test})
    result = gate.check_test_tag_binding(root, RUN, sha)
    assert result.ok is ok, result.detail
    if not ok:
        assert "untagged-added" in result.detail and "legacy.test.ts::" in result.detail


@pytest.mark.covers("FR-01.11/AC42")
def test_a_head_side_exclude_dir_cannot_hide_a_new_test(tmp_path):
    base = {**_py_base(), _CFG: json.dumps({"traceability": {"exclude_dirs": ["fixtures"]}})}
    head = {_CFG: json.dumps({"traceability": {"exclude_dirs": ["fixtures", "hidden"]}}),
            "tests/hidden/test_h.py": "def test_hidden():\n    pass\n"}
    root, sha = _repo(tmp_path, base, head)
    result = gate.check_test_tag_binding(root, RUN, sha)
    assert result.ok is False and "tests/hidden/test_h.py::test_hidden" in result.detail, result.detail


@pytest.mark.covers("FR-01.11/AC42")
def test_a_new_test_in_a_dir_the_base_config_already_excluded_stays_invisible(tmp_path):
    base = {**_py_base(), _CFG: json.dumps({"traceability": {"exclude_dirs": ["fixtures", "hidden"]}})}
    root, sha = _repo(tmp_path, base, {"tests/hidden/test_h.py": "def test_hidden():\n    pass\n"})
    assert gate.check_test_tag_binding(root, RUN, sha).ok is True
