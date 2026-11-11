"""Suite-tag brace depth is counted by the shared lexer, and a dropped covers comment is reported.

Asserts on ``propagate_suite_tags`` directly: ``parse_file`` dedupes and would hide a double
count. Cards trg-73c6425d (brace counting) and trg-b6f37040 (silent covers comment).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.lib.collectors._lib_loader import load_shared_lib  # noqa: E402
from scripts.lib.collectors._suite_tags import propagate_suite_tags  # noqa: E402

GRAMMAR = load_shared_lib("fr_tag_grammar")
PATH = "app/unit/orders.test.ts"
UNBOUND = "unbound-covers-comment"

pytestmark = pytest.mark.covers("FR-01.11/AC51")


def _by_test(hits) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for h in hits:
        out.setdefault(h.test.split("::", 1)[1], []).append(h.fr_id)
    return out


def _run(body: str, path: str = PATH):
    return propagate_suite_tags(body, path, GRAMMAR)


@pytest.mark.parametrize("literal", ['const s = "}";', "const r = /}/;", "const s = '}';", "const t = `}`;"])
def test_literal_with_closing_brace_does_not_pop_the_frame_early(literal):
    hits, _ = _run(
        "// @covers FR-01.01\ndescribe('suite', () => {\n"
        f"  {literal}\n  it('first', () => {{}});\n  it('second', () => {{}});\n}});\n")
    assert _by_test(hits) == {"first": ["FR-01.01"], "second": ["FR-01.01"]}


@pytest.mark.parametrize("literal", ['const s = "{";', "const r = /{/;", "const t = `{`;"])
def test_literal_with_opening_brace_does_not_leave_the_frame_open(literal):
    hits, _ = _run(
        "// @covers FR-01.01\ndescribe('a', () => {\n"
        f"  {literal}\n  it('inside', () => {{}});\n}});\n"
        "// @covers FR-02.01\ndescribe('b', () => {\n  it('other', () => {});\n});\n"
        "it('after', () => {});\n")
    assert _by_test(hits) == {"inside": ["FR-01.01"], "other": ["FR-02.01"]}


def test_a_test_after_a_closed_describe_does_not_carry_its_fr():
    hits, _ = _run(
        "// @covers FR-01.01\ndescribe('suite', () => {\n  const s = '{{';\n"
        "  it('inside', () => {});\n});\nit('stale', () => {});\n")
    assert "stale" not in _by_test(hits)
    assert _by_test(hits) == {"inside": ["FR-01.01"]}


def test_comment_braces_and_template_interpolation_are_not_counted():
    hits, _ = _run(
        "// @covers FR-01.01\ndescribe('suite', () => {\n  // closes } early?\n  /* } } */\n"
        "  const t = `${a} }`;\n  it('inside', () => {});\n});\nit('outside', () => {});\n")
    assert _by_test(hits) == {"inside": ["FR-01.01"]}


def test_wrapped_describe_signature_still_opens_on_the_next_line():
    hits, _ = _run("// @covers FR-01.01\ndescribe('suite', () =>\n{\n  it('t', () => {});\n});\nit('x', () => {});\n")
    assert _by_test(hits) == {"t": ["FR-01.01"]}


def test_tsx_source_is_lexed_with_jsx_on_and_ts_with_it_off():
    body = "// @covers FR-01.01\ndescribe('suite', () => {\n  const x = <p>}</p>;\n  it('t', () => {});\n});\n"
    assert _by_test(_run(body, "a/b.test.tsx")[0]) == {"t": ["FR-01.01"]}


def test_covers_above_an_import_is_reported_once_and_never_rebound():
    hits, invalid = _run("// @covers FR-01.01\nimport { x } from 'y';\ndescribe('s', () => {\n  it('t', () => {});\n});\n")
    assert hits == []
    assert [(i.reason, i.test) for i in invalid] == [(UNBOUND, "")]
    assert invalid[0].raw == f"{PATH}:1: // @covers FR-01.01"


def test_covers_separated_from_describe_by_a_blank_line_is_reported():
    hits, invalid = _run("// @covers FR-01.01\n\ndescribe('s', () => {\n  it('t', () => {});\n});\n")
    assert hits == []
    assert [(i.reason, i.raw) for i in invalid] == [(UNBOUND, f"{PATH}:1: // @covers FR-01.01")]


def test_two_consecutive_covers_lines_report_the_overwritten_first_one():
    hits, invalid = _run("// @covers FR-01.01\n// @covers FR-02.01\ndescribe('s', () => {\n  it('t', () => {});\n});\n")
    assert _by_test(hits) == {"t": ["FR-02.01"]}
    assert [(i.reason, i.raw) for i in invalid] == [(UNBOUND, f"{PATH}:1: // @covers FR-01.01")]


def test_a_covers_comment_at_end_of_file_is_reported():
    _, invalid = _run("describe('s', () => {});\n// @covers FR-01.01\n")
    assert [(i.reason, i.raw) for i in invalid] == [(UNBOUND, f"{PATH}:2: // @covers FR-01.01")]


@pytest.mark.parametrize("decl", ["it('t', () => {});", "test('t', () => {});", "describe('s', () => {});"])
def test_covers_directly_above_a_declaration_gives_no_warning(decl):
    _, invalid = _run(f"// @covers FR-01.01\n{decl}\n")
    assert invalid == []


def test_nested_suites_both_apply_and_inheritance_stops_at_each_close():
    hits, _ = _run(
        "// @covers FR-01.01\ndescribe('outer', () => {\n  const s = '}';\n"
        "  // @covers FR-02.01\n  describe('inner', () => {\n    it('deep', () => {});\n  });\n"
        "  it('mid', () => {});\n});\nit('top', () => {});\n")
    got = {k: sorted(v) for k, v in _by_test(hits).items()}
    assert got == {"deep": ["FR-01.01", "FR-02.01"], "mid": ["FR-01.01"]}


def test_the_manifest_carries_the_entry_in_the_shape_the_gate_and_audit_read(tmp_path):
    from scripts.lib.collectors.test_links import build_manifest

    (tmp_path / "spec.md").write_text(
        "# Spec\n\n## Functional Requirements\n\n| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
        "| FR-01.01 | Orders | Must | unit |\n", encoding="utf-8")
    test_file = tmp_path / "app" / "unit" / "orders.test.ts"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("// @covers FR-01.01\nimport x from 'y';\nit('t', () => {});\n", encoding="utf-8")
    manifest = build_manifest(tmp_path, spec_files=[tmp_path / "spec.md"], test_roots=[tmp_path])
    assert manifest["invalid_tags"] == [
        {"test": "", "raw": "app/unit/orders.test.ts:1: // @covers FR-01.01", "reason": UNBOUND}]


def _parse(body: str):
    from scripts.lib.collectors._file_tags import parse_file

    _src, _res, hits, invalid = parse_file(PATH, body, GRAMMAR)
    return hits, invalid


def test_a_line_comment_inside_a_wrapped_each_table_does_not_swallow_the_callback_brace():
    hits, _ = _parse(
        "// @covers FR-01.01\ndescribe('suite', () => {\n  it.each([\n    [1, 2], // first\n    [3, 4],\n"
        "  ])('adds %i', (a, b) => {\n    expect(a).toBe(1);\n  });\n  it('after', () => {});\n});\nit('outside', () => {});\n")
    assert _by_test(hits) == {"adds %i": ["FR-01.01"], "after": ["FR-01.01"]}


def test_a_line_comment_inside_a_wrapped_describe_head_does_not_leave_the_suite_open():
    hits, _ = _parse(
        "// @covers FR-01.01\ndescribe(\n  'Suite', // note\n  () => {\n    it('inside', () => {});\n  },\n);\n"
        "it('outside', () => {});\n")
    assert _by_test(hits) == {"inside": ["FR-01.01"]}


def test_the_reported_line_is_the_line_on_disk_not_in_the_joined_source():
    _, invalid = _parse(
        "it(\n  'wrapped head',\n  () => {},\n);\nit(\n  'another',\n  () => {},\n);\n// @covers FR-01.01\nimport x from 'y';\n")
    assert [i.raw for i in invalid] == [f"{PATH}:9: // @covers FR-01.01"]
