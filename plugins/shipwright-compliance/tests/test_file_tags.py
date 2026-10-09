"""The collector binds the three shapes the reference grammar cannot (FR-01.11/AC41, U1).

A wrapped multi-line Playwright ``test(``, a test inheriting a ``describe`` tag, and
pytest class-level / module-level ``covers`` marks must all bind, or the test-tag gate
would false-STOP on correctly tagged tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts.lib.collectors._file_tags import join_multiline_decls  # noqa: E402
from scripts.lib.collectors.test_links import build_manifest  # noqa: E402

_SPEC = (
    "# Spec\n\n## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
    "| FR-02.01 | Log in | Must | e2e |\n| FR-02.02 | Log out | Must | unit |\n"
)


def _manifest(tmp_path: Path, rel: str, body: str) -> dict:
    (tmp_path / "spec.md").write_text(_SPEC, encoding="utf-8")
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return build_manifest(tmp_path, spec_files=[tmp_path / "spec.md"], test_roots=[tmp_path])


def _bound(manifest: dict) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for key, node in manifest["requirements"].items():
        for links in node["tests"].values():
            for link in links:
                out.setdefault(link["id"], set()).add(key.split("::")[-1])
    return out


@pytest.mark.covers("FR-01.11/AC41")
def test_multi_line_playwright_test_binds_its_native_tag(tmp_path):
    body = (
        "import { test } from '@playwright/test';\n\n"
        "test(\n  'logs the user in with a very long descriptive title',\n"
        "  { tag: ['@FR-02.01'] },\n  async ({ page }) => {\n    await page.goto('/');\n  },\n);\n"
    )
    m = _manifest(tmp_path, "e2e/login.spec.ts", body)
    tid = "e2e/login.spec.ts::logs the user in with a very long descriptive title"
    assert _bound(m) == {tid: {"FR-02.01"}} and m["untagged_tests"] == []


@pytest.mark.covers("FR-01.11/AC41")
def test_multi_line_untagged_playwright_test_is_enumerated_as_untagged(tmp_path):
    body = "test(\n  'no tag here',\n  async ({ page }) => {\n    await page.goto('/');\n  },\n);\n"
    m = _manifest(tmp_path, "e2e/a.spec.ts", body)
    assert m["untagged_tests"] == ["e2e/a.spec.ts::no tag here"]


@pytest.mark.covers("FR-01.11/AC41")
def test_a_test_inheriting_a_describe_tag_binds(tmp_path):
    body = (
        "test.describe(\n  'auth',\n  { tag: ['@FR-02.01'] },\n  () => {\n"
        "    test('inner', async () => {});\n  },\n);\n"
    )
    assert _bound(_manifest(tmp_path, "e2e/s.spec.ts", body)) == {"e2e/s.spec.ts::inner": {"FR-02.01"}}


@pytest.mark.covers("FR-01.11/AC41")
def test_class_level_covers_mark_applies_to_every_test_method(tmp_path):
    body = (
        "import pytest\n\n\n@pytest.mark.covers(\"FR-02.02\")\nclass TestLogout:\n"
        "    def test_a(self):\n        pass\n\n"
        "    @pytest.mark.covers(\"FR-02.02\")\n    def test_b(self):\n        pass\n"
    )
    m = _manifest(tmp_path, "tests/test_logout.py", body)
    assert _bound(m) == {"tests/test_logout.py::test_a": {"FR-02.02"}, "tests/test_logout.py::test_b": {"FR-02.02"}}
    links = m["requirements"]["02::FR-02.02"]["tests"]["unit"]
    assert len(links) == 2, "a method carrying its class's tag must not be linked twice"


@pytest.mark.covers("FR-01.11/AC41")
def test_module_level_pytestmark_applies_to_every_test(tmp_path):
    body = "import pytest\n\npytestmark = [pytest.mark.covers(\"FR-02.02\")]\n\n\ndef test_x():\n    pass\n"
    m = _manifest(tmp_path, "tests/test_mod.py", body)
    assert _bound(m) == {"tests/test_mod.py::test_x": {"FR-02.02"}} and m["untagged_tests"] == []


@pytest.mark.covers("FR-01.11/AC41")
def test_join_leaves_single_line_and_unusual_shapes_untouched():
    single = "test('a', async () => {});\n"
    assert join_multiline_decls(single) == single
    commented = "test(\n  // why\n  'a',\n  async () => {},\n);\n"
    assert join_multiline_decls(commented) == commented


@pytest.mark.covers("FR-01.11/AC41")
def test_a_title_containing_function_or_arrow_does_not_end_the_head_early(tmp_path):
    body = ("test(\n  'the login function works => yes',\n  { tag: ['@FR-02.01'] },\n"
            "  async ({ page }) => {\n    await page.goto('/');\n  },\n);\n")
    m = _manifest(tmp_path, "e2e/t.spec.ts", body)
    assert _bound(m) == {"e2e/t.spec.ts::the login function works => yes": {"FR-02.01"}}


@pytest.mark.covers("FR-01.11/AC41")
def test_pytestmark_and_class_marks_skip_what_pytest_would_not_collect(tmp_path):
    body = ("import pytest\n\npytestmark = pytest.mark.covers(\"FR-02.02\")\n\n\n"
            "class Helpers:\n    def test_like_helper(self):\n        pass\n\n\n"
            "@pytest.mark.covers(\"FR-02.02\")\nclass NotATestClass:\n    def test_other(self):\n        pass\n\n\n"
            "def test_real():\n    pass\n")
    m = _manifest(tmp_path, "tests/test_scope.py", body)
    assert set(_bound(m)) == {"tests/test_scope.py::test_real"}


@pytest.mark.covers("FR-01.11/AC41")
def test_a_utf8_bom_file_is_still_enumerated(tmp_path):
    path = tmp_path / "tests" / "test_bom.py"
    path.parent.mkdir(parents=True)
    (tmp_path / "spec.md").write_text(_SPEC, encoding="utf-8")
    path.write_bytes(b"\xef\xbb\xbfdef test_hidden():\n    pass\n")
    m = build_manifest(tmp_path, spec_files=[tmp_path / "spec.md"], test_roots=[tmp_path])
    assert m["untagged_tests"] == ["tests/test_bom.py::test_hidden"]


@pytest.mark.covers("FR-01.11/AC42")
def test_a_data_driven_test_is_enumerated_and_a_native_tag_binds_it(tmp_path):
    body = ("it.each([1, 2])('adds %i', (n) => {});\n"
            "test.each([3])('tagged $n', { tag: ['@FR-02.01'] }, (n) => {});\n"
            "describe.each([1])('a suite', () => {});\n")
    m = _manifest(tmp_path, "e2e/t.spec.ts", body)
    assert _bound(m) == {"e2e/t.spec.ts::tagged $n": {"FR-02.01"}}
    assert m["untagged_tests"] == ["e2e/t.spec.ts::adds %i"]


@pytest.mark.covers("FR-01.11/AC42")
def test_a_wrapped_table_is_folded_onto_the_title_line(tmp_path):
    body = ("it.each([\n  [1, 2],\n  ['a)', 'b('],\n])('wrapped %i', { tag: ['@FR-02.01'] }, (a, b) => {\n"
            "  expect(a).toBe(b);\n});\n"
            "test.each`\n  a | b\n  ${1} | ${2}\n`('template $a', (t) => {});\n")
    joined = join_multiline_decls(body)
    assert "])('wrapped %i'" in joined
    assert len(joined.splitlines()) == 4
    m = _manifest(tmp_path, "e2e/t.spec.ts", body)
    assert _bound(m) == {"e2e/t.spec.ts::wrapped %i": {"FR-02.01"}}
    assert m["untagged_tests"] == ["e2e/t.spec.ts::template $a"]


@pytest.mark.covers("FR-01.11/AC42")
def test_an_each_table_that_never_reaches_a_title_is_left_untouched():
    unfinished = "it.each([\n  [1, 2],\n])\n(foo);\nconst x = 1;\n"
    assert join_multiline_decls(unfinished) == unfinished


@pytest.mark.covers("FR-01.11/AC42")
def test_a_table_whose_title_sits_on_the_next_line_is_folded_and_enumerated(tmp_path):
    body = "it.each([\n  [1, 2],\n])(\n  'long title %i',\n  (a, b) => {\n    expect(a).toBe(b);\n  },\n);\n"
    m = _manifest(tmp_path, "e2e/t.spec.ts", body)
    assert m["untagged_tests"] == ["e2e/t.spec.ts::long title %i"]


@pytest.mark.covers("FR-01.11/AC42")
def test_comments_with_quotes_and_parens_inside_a_wrapped_table_do_not_break_the_fold(tmp_path):
    body = ("it.each([\n  1, // don't ) stop\n  /* ) ' */ 2,\n])('commented %i', (n) => {});\n"
            "test.each\n`\n  a | b\n`('bare %s', (t) => {});\n")
    m = _manifest(tmp_path, "e2e/t.spec.ts", body)
    assert m["untagged_tests"] == ["e2e/t.spec.ts::bare %s", "e2e/t.spec.ts::commented %i"]


@pytest.mark.covers("FR-01.11/AC42")
def test_a_bare_each_opener_with_a_long_table_is_folded_and_enumerated(tmp_path):
    rows = "".join(f"  [{i}, {i + 1}],\n" for i in range(12))
    body = f"it.each(\n[\n{rows}])('long table %i', (a, b) => {{}});\n"
    joined = join_multiline_decls(body)
    assert "])('long table %i'" in joined
    assert len(joined.splitlines()) == 1
    m = _manifest(tmp_path, "e2e/t.spec.ts", body)
    assert m["untagged_tests"] == ["e2e/t.spec.ts::long table %i"]


@pytest.mark.covers("FR-01.11/AC42")
def test_a_tag_on_the_line_after_a_next_line_title_still_binds(tmp_path):
    body = ("it.each([1, 2])(\n  'long data-driven title %i',\n  { tag: ['@FR-02.01'] },\n"
            "  (n) => {\n    expect(n).toBe(n);\n  },\n);\n")
    m = _manifest(tmp_path, "e2e/t.spec.ts", body)
    assert _bound(m) == {"e2e/t.spec.ts::long data-driven title %i": {"FR-02.01"}}
