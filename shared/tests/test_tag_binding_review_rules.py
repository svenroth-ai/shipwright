"""The test-tag gate's review hardening (U1, FR-01.11/AC41): bindings-only renames,
same-named siblings, unlocatable legacy tests, newly collected tests, scope shapes, and
the fail-closed collection rules. Hand-built manifests, as in ``test_tag_binding_core.py``.
"""

from __future__ import annotations

import pytest

from tools.verifiers._tag_binding_core import evaluate
from tools.verifiers._tag_binding_identity import body_digests, would_collect

F = "tests/test_mod.py"
_OLD = "def test_old():\n    assert 1 + 1 == 2\n"


def _manifest(untagged=(), links=()):
    tests = {"unit": [{"id": t, "path": t} for t in links]}
    return {"requirements": {"01::FR-01.11": {"tests": tests, "acs": {}}},
            "untagged_tests": sorted(untagged), "orphans": [], "invalid_tags": []}


def _reader(base, head):
    return lambda path, side: (base if side == "base" else head).get(path, "")


def _run(base_m, head_m, base_files, head_files, exemptions=(), expected=frozenset()):
    changed = set(base_files) | set(head_files)
    return evaluate(base_m, head_m, changed, _reader(base_files, head_files), list(exemptions), set(expected))


def _ex(scope, code):
    return {"kind": "test_exemption", "scope": scope, "reason_code": code}


_PY_RENAMES = [
    ("def test_x(self):\n    self.assertTrue(f())\n", "def test_x(self):\n    self.assertFalse(f())\n", False),
    ("def test_x(r):\n    assert is_ok(r)\n", "def test_x(r):\n    assert is_err(r)\n", False),
    ("def test_x(resp):\n    assert resp.ok\n", "def test_x(resp):\n    assert resp.failed\n", False),
    ("def test_x(client):\n    client.get('/a')\n", "def test_x(client):\n    client.delete('/a')\n", False),
    ("from m import is_ok\n\n\ndef test_x(r):\n    assert is_ok(r)\n",
     "from m import is_err\n\n\ndef test_x(r):\n    assert is_err(r)\n", False),
    ("def test_x(client):\n    client.get(url='/a')\n", "def test_x(client):\n    client.get(path='/a')\n", False),
    ("def test_x(old_client):\n    old_client.get('/a')\n", "def test_x(new_client):\n    new_client.get('/a')\n", True),
    ("def test_x():\n    res = run()\n    assert res\n", "def test_x():\n    out = run()\n    assert out\n", True),
    ("import json as j\n\n\ndef test_x():\n    assert j.dumps(1)\n",
     "import json as js\n\n\ndef test_x():\n    assert js.dumps(1)\n", True),
    ("def test_x():\n    import json as j\n    assert j.dumps(1)\n",
     "def test_x():\n    import json as js\n    assert js.dumps(1)\n", True),
]


@pytest.mark.covers("FR-01.11/AC41")
@pytest.mark.parametrize(("base_src", "head_src", "mechanical"), _PY_RENAMES)
def test_mechanical_refactor_renames_bindings_only(base_src, head_src, mechanical):
    tid = f"{F}::test_x"
    v = _run(_manifest([tid]), _manifest([tid]), {F: base_src}, {F: head_src},
             exemptions=[_ex(tid, "mechanical-refactor")])
    assert (v.findings == [] and v.exempted == [(tid, "mechanical-refactor")]) is mechanical, v.findings


_TS = "e2e/x.spec.ts"


@pytest.mark.covers("FR-01.11/AC41")
@pytest.mark.parametrize(("head_body", "mechanical"), [
    ("async ({ request: api }) => { const out = await api.get('/a'); expect(out.ok()).toBe(true); }", True),
    ("async ({ request: r }) => { const res = await r.delete('/a'); expect(res.ok()).toBe(true); }", False),
    ("async ({ request: r }) => { const res = await r.get('/a'); expect(res.failed()).toBe(true); }", False),
    ("async ({ request: r }) => { const res = await r.get('/a'); expect(res.ok()).toBe(false); }", False),
    ("async ({ request: r }) => { const res = await r.get('/a'); assertOk(res.ok()).toBe(true); }", False),
])
def test_ts_mechanical_refactor_renames_bindings_only(head_body, mechanical):
    base = "test('t', async ({ request: r }) => { const res = await r.get('/a'); expect(res.ok()).toBe(true); });\n"
    tid = f"{_TS}::t"
    v = _run(_manifest([tid]), _manifest([tid]), {_TS: base}, {_TS: f"test('t', {head_body});\n"},
             exemptions=[_ex(tid, "mechanical-refactor")])
    assert (v.findings == []) is mechanical, v.findings


_TWINS = "class TestA:\n{a}    def test_x(self):\n        assert 1\n\n\nclass TestB:\n{b}    def test_x(self):\n        assert 2\n"


@pytest.mark.covers("FR-01.11/AC41")
@pytest.mark.parametrize(("mark_a", "mark_b", "stops"), [
    ('    @pytest.mark.covers("FR-01.11")\n', '    @pytest.mark.covers("FR-01.11")\n', False),
    ('    @pytest.mark.covers("FR-01.11")\n', "", True),
    ('    @pytest.mark.covers("FR-01.11")\n', '    @pytest.mark.covers("FR-01.03")\n', True),
])
def test_same_named_siblings_stop_only_when_one_is_untagged_or_tags_differ(mark_a, mark_b, stops):
    tid = f"{F}::test_x"
    v = _run(_manifest(), _manifest(links=[tid]), {F: ""}, {F: _TWINS.format(a=mark_a, b=mark_b)})
    assert ([k for k, _t, _w in v.findings] == ["ambiguous-name"]) is stops
    assert stops or any("share this name and carry the same tags" in w for w in v.warnings)


@pytest.mark.covers("FR-01.11/AC41")
def test_same_title_playwright_tests_with_identical_tags_only_warn():
    head = ("test.describe('a', () => {\n  test('t', { tag: ['@FR-01.11'] }, async () => { expect(1); });\n});\n"
            "test.describe('b', () => {\n  test('t', { tag: ['@FR-01.11'] }, async () => { expect(2); });\n});\n")
    v = _run(_manifest(), _manifest(links=[f"{_TS}::t"]), {_TS: ""}, {_TS: head})
    assert v.findings == [] and any("same tags" in w for w in v.warnings)


@pytest.mark.covers("FR-01.11/AC41")
def test_an_unlocatable_legacy_test_is_untouched_when_another_test_is_edited():
    base = ("test.each([1, 2])('adds %i', async (n) => { expect(n).toBeTruthy(); });\n"
            "test('it\\'s fine', async () => { expect(1).toBe(1); });\n"
            "test('edited', { tag: ['@FR-01.11'] }, async () => { expect(1).toBe(1); });\n")
    head = base.replace("async () => { expect(1).toBe(1); });\n", "async () => { expect(2).toBe(2); });\n")
    head = head.replace("fine', async () => { expect(2).toBe(2)", "fine', async () => { expect(1).toBe(1)")
    assert head != base and "it\\'s fine', async () => { expect(1)" in head
    legacy = [f"{_TS}::adds %i", f"{_TS}::it\\"]  # the collector's titles for these two shapes
    v = _run(_manifest(legacy, links=[f"{_TS}::edited"]), _manifest(legacy, links=[f"{_TS}::edited"]),
             {_TS: base}, {_TS: head})
    assert v.findings == [] and v.touched == {f"{_TS}::edited"}, v.findings


@pytest.mark.covers("FR-01.11/AC41")
def test_an_untagged_test_in_a_file_outside_the_diff_warns_as_newly_collected():
    other = "tests/test_widened.py::test_legacy"
    v = evaluate(_manifest(), _manifest([other]), set(), _reader({}, {}), [], set())
    assert v.findings == [] and any("newly collected legacy test" in w for w in v.warnings)


@pytest.mark.covers("FR-01.11/AC41")
def test_exemption_scope_takes_backslashes_and_brackets_but_not_a_bare_wildcard():
    src = _OLD + "\n\nclass Helpers:\n    def test_data(self):\n        return 1\n"
    tid = f"{F}::test_data"
    ok = _run(_manifest([f"{F}::test_old"]), _manifest([f"{F}::test_old", tid]), {F: _OLD}, {F: src},
              exemptions=[_ex("tests\\test_mod.py::test_data", "fixture-or-helper"),
                          _ex(f"{F}::test_case[admin]", "fixture-or-helper")])
    assert ok.findings == [] and ok.exempted == [(tid, "fixture-or-helper")]
    assert any("test_case[admin]" in w and "unused" in w for w in ok.warnings)
    bare = _run(_manifest(), _manifest(), {}, {}, exemptions=[_ex(f"{F}::*", "fixture-or-helper")])
    assert [k for k, _t, _w in bare.findings] == ["bad-exemption"]


@pytest.mark.covers("FR-01.11/AC41")
def test_no_expected_frs_at_all_warns_that_the_scope_check_did_not_run():
    v = evaluate(_manifest(), _manifest(links=[f"{F}::test_new"]), set(), _reader({}, {}), [], None)
    assert v.warnings == ["no work_completed Spec-Impact FRs found; out-of-scope tag check not run"]


@pytest.mark.covers("FR-01.11/AC41")
@pytest.mark.parametrize("src", [
    "import sys\n\nif sys.platform:\n    def test_x():\n        pass\n",
    "try:\n    import a\nexcept ImportError:\n    pass\nelse:\n    def test_x():\n        pass\n",
    "with ctx():\n    def test_x():\n        pass\n",
    "class TestOuter:\n    class TestInner:\n        def test_x(self):\n            pass\n",
])
def test_would_collect_fails_closed_for_conditional_and_nested_test_classes(src):
    assert would_collect(src, F, "test_x")


@pytest.mark.covers("FR-01.11/AC41")
def test_steps_hooks_and_commented_out_calls_are_not_declarations():
    src = ("test.beforeEach(async () => {});\n// test('gone', async () => {});\n"
           "test('real', async () => {\n  await test.step('inner', async () => {});\n});\n")
    assert body_digests(src, _TS, "inner") == () == body_digests(src, _TS, "gone")
    assert body_digests(src, _TS, "real") != ()
