"""`lib.assertion_weakening` — the AC-6 hard rule, in code.

@FR-01.19

"Adjust the test until it is green" is the failure mode a self-repairing branch
invites, so it is refused mechanically rather than trusted to prose. The
detector compares the **parsed** before and after of each changed test file:
diff text cannot tell a moved assertion from a deleted one, and trying to read
`==` → `>=` out of a unified diff is a tar pit (external review round 1).

The line this file draws is the interesting part. **Removing** coverage is
blocked. **Changing** an assertion's expression is only reported — because
updating a count another PR legitimately changed is the single commonest honest
repair, and a rule that blocked it would block the very thing the self-heal
exists to do.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib import assertion_weakening as aw  # noqa: E402

TEST_PATH = "shared/tests/test_thing.py"


def _change(before, after, path=TEST_PATH, status="M", old_path=None):
    return aw.FileChange(status=status, path=path, old_path=old_path,
                         before=before, after=after)


def _kinds(findings, *, blocking=None):
    return [
        f.kind for f in findings
        if blocking is None or f.blocking is blocking
    ]


# --------------------------------------------------------------------------
# blocking: coverage went away
# --------------------------------------------------------------------------

def test_an_assertion_removed_from_a_test_blocks():
    before = "def test_a():\n    assert 1 == 1\n    assert 2 == 2\n"
    after = "def test_a():\n    assert 1 == 1\n"
    findings = aw.detect_weakening([_change(before, after)])
    assert "assertions_removed" in _kinds(findings, blocking=True)


def test_a_removed_test_function_blocks():
    before = "def test_a():\n    assert 1\n\ndef test_b():\n    assert 2\n"
    after = "def test_a():\n    assert 1\n"
    assert "test_removed" in _kinds(aw.detect_weakening([_change(before, after)]),
                                    blocking=True)


def test_a_removed_test_method_blocks():
    before = ("class TestX:\n"
              "    def test_a(self):\n        assert 1\n"
              "    def test_b(self):\n        assert 2\n")
    after = "class TestX:\n    def test_a(self):\n        assert 1\n"
    findings = aw.detect_weakening([_change(before, after)])
    assert "test_removed" in _kinds(findings, blocking=True)
    assert any("TestX::test_b" in f.subject for f in findings)


def test_a_removed_test_class_blocks_every_method_it_took_with_it():
    before = "class TestX:\n    def test_a(self):\n        assert 1\n"
    after = "x = 1\n"
    assert "test_removed" in _kinds(aw.detect_weakening([_change(before, after)]),
                                    blocking=True)


def test_self_assert_calls_count_as_assertions():
    before = ("class TestX:\n    def test_a(self):\n"
              "        self.assertEqual(1, 1)\n        self.assertTrue(True)\n")
    after = "class TestX:\n    def test_a(self):\n        self.assertEqual(1, 1)\n"
    assert "assertions_removed" in _kinds(aw.detect_weakening([_change(before, after)]),
                                          blocking=True)


def test_a_pytest_raises_context_counts_as_an_assertion():
    before = ("def test_a():\n    with pytest.raises(ValueError):\n        boom()\n"
              "    assert 1\n")
    after = "def test_a():\n    boom_safely()\n    assert 1\n"
    assert "assertions_removed" in _kinds(aw.detect_weakening([_change(before, after)]),
                                          blocking=True)


def test_a_deleted_test_file_blocks():
    before = "def test_a():\n    assert 1\n"
    findings = aw.detect_weakening([_change(before, None, status="D")])
    assert "file_removed" in _kinds(findings, blocking=True)


# --------------------------------------------------------------------------
# blocking: the test is still there but has been switched off
# --------------------------------------------------------------------------

def test_a_skip_decorator_added_to_an_existing_test_blocks():
    before = "def test_a():\n    assert 1\n"
    after = "import pytest\n\n@pytest.mark.skip\ndef test_a():\n    assert 1\n"
    assert "skip_added" in _kinds(aw.detect_weakening([_change(before, after)]),
                                  blocking=True)


def test_an_xfail_decorator_added_blocks():
    before = "def test_a():\n    assert 1\n"
    after = "import pytest\n\n@pytest.mark.xfail\ndef test_a():\n    assert 1\n"
    assert "skip_added" in _kinds(aw.detect_weakening([_change(before, after)]),
                                  blocking=True)


def test_a_class_level_skip_added_blocks_its_methods():
    before = "class TestX:\n    def test_a(self):\n        assert 1\n"
    after = ("import pytest\n\n@pytest.mark.skip(reason='later')\n"
             "class TestX:\n    def test_a(self):\n        assert 1\n")
    assert "skip_added" in _kinds(aw.detect_weakening([_change(before, after)]),
                                  blocking=True)


def test_a_module_level_pytestmark_skip_added_blocks():
    before = "def test_a():\n    assert 1\n"
    after = ("import pytest\n\npytestmark = pytest.mark.skip(reason='later')\n\n"
             "def test_a():\n    assert 1\n")
    assert "skip_added" in _kinds(aw.detect_weakening([_change(before, after)]),
                                  blocking=True)


def test_a_skip_call_added_inside_an_existing_test_blocks():
    before = "def test_a():\n    assert 1\n"
    after = "import pytest\n\ndef test_a():\n    pytest.skip('later')\n    assert 1\n"
    assert "skip_added" in _kinds(aw.detect_weakening([_change(before, after)]),
                                  blocking=True)


# --------------------------------------------------------------------------
# blocking: we cannot read it, so we refuse
# --------------------------------------------------------------------------

def test_an_unparseable_after_revision_fails_closed():
    before = "def test_a():\n    assert 1\n"
    after = "def test_a(:\n    assert 1\n"
    assert "unparseable" in _kinds(aw.detect_weakening([_change(before, after)]),
                                   blocking=True)


def test_a_changed_test_file_in_an_unread_language_is_refused_not_waved_through():
    """JS/TS now has its own reader (below) — this checks a language neither
    reader covers still fails closed instead of being silently waved through."""
    findings = aw.detect_weakening([
        _change("it 'x' do\nend\n", "it 'x' do\n  xit\nend\n",
                path="e2e/tests/login_spec.rb")
    ])
    assert "unsupported_test_file" in _kinds(findings, blocking=True)


def test_a_conftest_py_change_under_a_tests_path_is_not_a_false_block():
    """Code review: adding JS/TS support dropped the pre-existing `.py`
    exemption on the `unsupported_test_file` guard, so ANY `.py` file under a
    `tests/`-shaped path that isn't pytest-collected (`conftest.py`,
    `tests/__init__.py`, a fixture module) wrongly fell into the blocking
    refusal — even though `ast` reads Python fine; it just has no tests to
    lose here. `conftest.py` is exactly the ordinary, extremely common case
    this must never block."""
    findings = aw.detect_weakening([
        _change("import pytest\n", "import pytest\n\n\ndef fixture_helper():\n    pass\n",
                path="shared/tests/conftest.py")
    ])
    assert findings == []


# --------------------------------------------------------------------------
# fences — the false positives that would make the gate unusable
# --------------------------------------------------------------------------

def test_a_newly_added_test_file_is_exempt():
    after = "def test_a():\n    assert 1\n"
    assert aw.detect_weakening([_change(None, after, status="A")]) == []


def test_a_non_test_file_is_never_examined():
    """A production `assert` is not a test assertion — counting it would block
    ordinary refactors that happen to drop one."""
    before = "def f():\n    assert x\n    return 1\n"
    after = "def f():\n    return 1\n"
    assert aw.detect_weakening([
        _change(before, after, path="shared/scripts/lib/thing.py")
    ]) == []


def test_renaming_a_test_out_of_collection_blocks():
    """The quiet way to delete tests: the assertions stay in the tree, but
    pytest no longer collects them. Judging only the destination path let this
    through (external code review, round 2)."""
    body = "def test_a():\n    assert 1\n"
    findings = aw.detect_weakening([
        _change(body, body, status="R",
                path="shared/scripts/lib/helpers.py",
                old_path="shared/tests/test_thing.py")
    ])
    assert "test_removed_by_rename" in _kinds(findings, blocking=True)


def test_a_rename_preserves_identity_rather_than_reading_as_a_deletion():
    body = "def test_a():\n    assert 1\n"
    findings = aw.detect_weakening([
        _change(body, body, status="R",
                path="shared/tests/test_new.py", old_path="shared/tests/test_old.py")
    ])
    assert findings == []


def test_adding_assertions_is_never_a_finding():
    before = "def test_a():\n    assert 1\n"
    after = "def test_a():\n    assert 1\n    assert 2\n"
    assert aw.detect_weakening([_change(before, after)]) == []


def test_an_unparseable_before_revision_does_not_block():
    """Only the *after* revision must be readable. A base that never parsed is
    not this PR's doing, and failing closed on it would wedge every repair."""
    findings = aw.detect_weakening([
        _change("def test_a(:\n", "def test_a():\n    assert 1\n")
    ])
    assert _kinds(findings, blocking=True) == []


# --------------------------------------------------------------------------
# reported, deliberately not blocked
# --------------------------------------------------------------------------

def test_a_changed_assertion_expression_is_reported_but_does_not_block():
    """Updating a pinned count another PR legitimately changed IS the canonical
    repair. Blocking it would block the mechanism this whole iterate builds —
    so it is surfaced for the reviewer and the PR must say why the new value is
    the truth."""
    before = "def test_a():\n    assert len(x) == 5\n"
    after = "def test_a():\n    assert len(x) == 6\n"
    findings = aw.detect_weakening([_change(before, after)])
    assert _kinds(findings, blocking=True) == []
    assert "assertion_changed" in _kinds(findings, blocking=False)


def test_a_relaxed_comparison_is_reported_with_both_sides_visible():
    before = "def test_a():\n    assert n == 5\n"
    after = "def test_a():\n    assert n >= 5\n"
    findings = [f for f in aw.detect_weakening([_change(before, after)])
                if f.kind == "assertion_changed"]
    assert findings
    assert "test_a" in findings[0].subject


def test_verdict_blocks_only_on_a_blocking_finding():
    assert aw.verdict([]) == "clear"
    reported = aw.Finding(kind="assertion_changed", blocking=False,
                          subject="x", detail="y")
    assert aw.verdict([reported]) == "review"
    blocked = aw.Finding(kind="assertions_removed", blocking=True,
                         subject="x", detail="y")
    assert aw.verdict([reported, blocked]) == "blocked"


# --------------------------------------------------------------------------
# JS/TS reader — a bracket-balancing scanner, not a real parser (see module
# docstring). The Python suite above is the contract; these mirror it.
# --------------------------------------------------------------------------

JS_TEST_PATH = "web/tests/thing.test.ts"


def _jschange(before, after, path=JS_TEST_PATH, status="M", old_path=None):
    return aw.FileChange(status=status, path=path, old_path=old_path,
                         before=before, after=after)


def test_js_an_assertion_removed_from_a_test_blocks():
    before = "it('a', () => { expect(1).toBe(1); expect(2).toBe(2); });\n"
    after = "it('a', () => { expect(1).toBe(1); });\n"
    findings = aw.detect_weakening([_jschange(before, after)])
    assert "assertions_removed" in _kinds(findings, blocking=True)


def test_js_a_bare_node_assert_call_counts_as_an_assertion():
    before = "it('a', () => { assert(x); assert(y); });\n"
    after = "it('a', () => { assert(x); });\n"
    findings = aw.detect_weakening([_jschange(before, after)])
    assert "assertions_removed" in _kinds(findings, blocking=True)


def test_js_a_member_style_assert_call_counts_as_an_assertion():
    """`assert.strictEqual(a, b)` (Node's built-in `assert` module, and
    Chai's `assert` interface) is at least as common as bare `assert(x)` and
    was silently uncounted — not even a reported finding, unlike every other
    named limit in this file (code review)."""
    before = "it('a', () => { assert.strictEqual(x, 1); assert.ok(y); });\n"
    after = "it('a', () => { assert.strictEqual(x, 1); });\n"
    findings = aw.detect_weakening([_jschange(before, after)])
    assert "assertions_removed" in _kinds(findings, blocking=True)


def test_js_a_member_style_helper_call_named_assert_is_not_counted_as_an_assertion():
    """External Tier-3 review, PR #685 (blocking): `fixture.assert.ok(...)` is
    an ordinary helper method call, not Node/Chai's `assert.ok(...)` --
    `_JS_ASSERT_HEAD` used to match `assert.<method>(` regardless of what
    preceded it, so removing this helper call read as removing a real
    assertion."""
    before = "it('a', () => { fixture.assert.ok(1); expect(2).toBe(2); });\n"
    after = "it('a', () => { expect(2).toBe(2); });\n"
    assert _kinds(aw.detect_weakening([_jschange(before, after)]), blocking=True) == []


def test_js_a_member_style_helper_call_named_expect_is_not_counted_as_an_assertion():
    """Same finding, `expect` half: `helper.expect(...)` is an ordinary
    helper method call, not Jest/Vitest's top-level `expect(...)`."""
    before = "it('a', () => { helper.expect(1); expect(2).toBe(2); });\n"
    after = "it('a', () => { expect(2).toBe(2); });\n"
    assert _kinds(aw.detect_weakening([_jschange(before, after)]), blocking=True) == []


def test_js_an_expect_matcher_factory_is_not_double_counted_as_its_own_assertion():
    """`expect.stringContaining(...)`/`expect.any(...)` are matcher FACTORIES
    passed as an argument into a real `expect(...)` call, not independent
    assertions — `_JS_ASSERT_HEAD` deliberately does not extend member-style
    matching to `expect.<method>(`, unlike `assert.<method>(`, so this single
    real assertion is not inflated into two. Asserted directly on the
    collected signature count, not on an unchanged-diff producing no
    findings (an identical before/after would pass even with a double-count
    bug, since both sides would double-count identically)."""
    source = "it('a', () => { expect(x).toEqual(expect.stringContaining('a')); });\n"
    tests = aw._js_collect(source)
    assert tests is not None
    (only_test,) = tests.values()
    assert len(only_test.assertions) == 1


def test_js_a_multiline_formatted_call_still_catches_a_removed_assertion():
    """`it(\\n  'name',\\n  fn\\n)` — a common formatter style for a long
    callback — must read the same as the single-line form. An earlier
    revision anchored the name-literal match right after `(` with no gap
    tolerance, silently dropping every such test from collection (code
    review)."""
    before = "it(\n  'a',\n  () => {\n    expect(1).toBe(1);\n    expect(2).toBe(2);\n  }\n);\n"
    after = "it(\n  'a',\n  () => {\n    expect(1).toBe(1);\n  }\n);\n"
    findings = aw.detect_weakening([_jschange(before, after)])
    assert "assertions_removed" in _kinds(findings, blocking=True)


def test_js_reformatting_a_call_to_multiline_is_not_itself_a_finding():
    before = "it('a', () => { expect(1).toBe(1); });\n"
    after = "it(\n  'a',\n  () => { expect(1).toBe(1); }\n);\n"
    assert aw.detect_weakening([_jschange(before, after)]) == []


def test_js_a_removed_test_blocks():
    before = ("it('a', () => { expect(1).toBe(1); });\n"
              "it('b', () => { expect(2).toBe(2); });\n")
    after = "it('a', () => { expect(1).toBe(1); });\n"
    findings = aw.detect_weakening([_jschange(before, after)])
    assert "test_removed" in _kinds(findings, blocking=True)
    assert any(f"{JS_TEST_PATH}::b" == f.subject for f in findings)


def test_js_an_it_skip_added_to_an_existing_test_blocks():
    before = "it('a', () => { expect(1).toBe(1); });\n"
    after = "it.skip('a', () => { expect(1).toBe(1); });\n"
    assert "skip_added" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                  blocking=True)


def test_js_an_xit_rename_added_blocks():
    before = "it('a', () => { expect(1).toBe(1); });\n"
    after = "xit('a', () => { expect(1).toBe(1); });\n"
    assert "skip_added" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                  blocking=True)


def test_js_an_it_fixme_added_to_an_existing_test_blocks():
    """`.fixme` was advertised (this module's own test-completeness ledger
    claimed it) but never actually added to `_JS_ALLOWED_CHAINS`, so every
    invoked `it.fixme(...)`/`test.fixme(...)` fell through to the
    unrecognized-and-invoked fail-closed path and blocked the repair outright
    -- a documentation/implementation mismatch (external Tier-3 review, PR
    #685, ninth round)."""
    before = "it('a', () => { expect(1).toBe(1); });\n"
    after = "it.fixme('a', () => { expect(1).toBe(1); });\n"
    assert "skip_added" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                  blocking=True)


def test_js_removing_an_it_fixme_is_not_itself_a_finding():
    """The companion case: `.fixme` REMOVED (the test starts running again)
    is not a weakening -- same treatment `.skip` removal already gets."""
    before = "it.fixme('a', () => { expect(1).toBe(1); });\n"
    after = "it('a', () => { expect(1).toBe(1); });\n"
    assert _kinds(aw.detect_weakening([_jschange(before, after)]), blocking=True) == []


def test_js_a_describe_skip_added_blocks_its_tests():
    before = "describe('suite', () => {\n  it('a', () => { expect(1).toBe(1); });\n});\n"
    after = ("describe.skip('suite', () => {\n"
             "  it('a', () => { expect(1).toBe(1); });\n});\n")
    assert "skip_added" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                  blocking=True)


def test_js_an_xdescribe_rename_blocks_its_tests():
    before = "describe('suite', () => {\n  it('a', () => { expect(1).toBe(1); });\n});\n"
    after = "xdescribe('suite', () => {\n  it('a', () => { expect(1).toBe(1); });\n});\n"
    assert "skip_added" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                  blocking=True)


def test_js_an_unbalanced_after_revision_fails_closed():
    """Missing the closing `});` — the bracket scanner cannot trust anything
    it extracted, so this is `unparseable`, the same fail-closed shape as an
    unparseable Python revision."""
    before = "it('a', () => { expect(1).toBe(1); });\n"
    after = "it('a', () => { expect(1).toBe(1);\n"
    assert "unparseable" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                   blocking=True)


def test_js_adding_assertions_is_never_a_finding():
    before = "it('a', () => { expect(1).toBe(1); });\n"
    after = "it('a', () => { expect(1).toBe(1); expect(2).toBe(2); });\n"
    assert aw.detect_weakening([_jschange(before, after)]) == []


def test_js_a_changed_matcher_argument_is_reported_but_does_not_block():
    before = "it('a', () => { expect(n).toBe(5); });\n"
    after = "it('a', () => { expect(n).toBe(6); });\n"
    findings = aw.detect_weakening([_jschange(before, after)])
    assert _kinds(findings, blocking=True) == []
    assert "assertion_changed" in _kinds(findings, blocking=False)


def test_js_an_unbalanced_before_revision_does_not_block():
    """Only the *after* revision must scan cleanly — a base we cannot read is
    not this change's doing (mirrors the Python `unparseable`-before case)."""
    findings = aw.detect_weakening([
        _jschange("it('a', () => { expect(1).toBe(1);\n",
                  "it('a', () => { expect(1).toBe(1); });\n")
    ])
    assert _kinds(findings, blocking=True) == []


def test_js_renaming_a_test_out_of_collection_blocks():
    body = "it('a', () => { expect(1).toBe(1); });\n"
    findings = aw.detect_weakening([
        _jschange(body, body, status="R",
                  path="web/lib/thing.ts", old_path=JS_TEST_PATH)
    ])
    assert "test_removed_by_rename" in _kinds(findings, blocking=True)


def test_js_each_parametrized_assertion_removal_blocks():
    """`test.each`/`it.each` is Jest/Vitest's `@pytest.mark.parametrize`
    equivalent — a two-call chain (table, then name+body). Missed entirely by
    an earlier revision of the scanner (external spec review round 1)."""
    before = ("test.each([[1, 1], [2, 2]])('adds %i', (a, b) => {\n"
              "  expect(a + 0).toBe(a);\n  expect(a).toBe(b);\n});\n")
    after = ("test.each([[1, 1], [2, 2]])('adds %i', (a, b) => {\n"
             "  expect(a).toBe(b);\n});\n")
    findings = aw.detect_weakening([_jschange(before, after)])
    assert "assertions_removed" in _kinds(findings, blocking=True)


def test_js_skip_each_newly_applied_blocks():
    before = "test.each([[1]])('x %i', (a) => { expect(a).toBe(1); });\n"
    after = "test.skip.each([[1]])('x %i', (a) => { expect(a).toBe(1); });\n"
    assert "skip_added" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                  blocking=True)


def test_js_describe_each_wrapping_still_sees_removed_tests():
    before = ("describe.each([['a']])('%s', (label) => {\n"
              "  it('one', () => { expect(1).toBe(1); });\n"
              "  it('two', () => { expect(2).toBe(2); });\n});\n")
    after = ("describe.each([['a']])('%s', (label) => {\n"
             "  it('one', () => { expect(1).toBe(1); });\n});\n")
    assert "test_removed" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                    blocking=True)


def test_js_each_tagged_template_table_is_supported():
    """`.each` given a tagged-template table (no parens at all around it) is
    the other documented Jest/Vitest form — invisible in an earlier revision
    of this scanner (external spec review round 2)."""
    before = ("test.each`a | b\n${1} | ${1}`('adds %s', ({a, b}) => {\n"
              "  expect(a).toBe(b);\n});\n")
    after = ("test.each`a | b\n${1} | ${1}`('adds %s', ({a, b}) => {\n"
             "});\n")
    findings = aw.detect_weakening([_jschange(before, after)])
    assert "assertions_removed" in _kinds(findings, blocking=True)


def test_js_an_each_head_with_no_table_or_body_fails_closed():
    """A recognized chain (`.each`) that never resolves to an actual call is
    treated the same as an unrecognized one: fail closed, not silently skip."""
    before = "it('a', () => { expect(1).toBe(1); });\n"
    after = "it('a', () => { expect(1).toBe(1); });\ntest.each;\n"
    assert "unparseable" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                   blocking=True)


def test_js_an_unrecognized_modifier_chain_fails_closed_rather_than_missing_it():
    """`.concurrent` is real Jest API this scanner does not implement — rather
    than silently miss whatever is inside it, the whole file fails closed."""
    before = "test.concurrent('a', async () => { expect(1).toBe(1); });\n"
    after = "test.concurrent('a', async () => {});\n"
    assert "unparseable" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                   blocking=True)


def test_js_a_line_broken_chain_is_not_collapsed_to_a_bare_reference():
    """`test\\n  .skip(...)` is ordinary Prettier-formatted code — an earlier
    revision's strict-adjacency chain regex saw an empty chain here and
    silently treated the whole declaration as a non-call (external spec
    review round 3)."""
    before = "it('a', () => { expect(1).toBe(1); });\n"
    after = "it\n  .skip('a', () => { expect(1).toBe(1); });\n"
    assert "skip_added" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                  blocking=True)


def test_js_a_comment_before_the_dot_is_not_collapsed_to_a_bare_reference():
    before = "it('a', () => { expect(1).toBe(1); });\n"
    after = "it/* eslint-disable-next-line */.skip('a', () => { expect(1).toBe(1); });\n"
    assert "skip_added" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                  blocking=True)


def test_js_computed_member_access_fails_closed_rather_than_missing_it():
    """`test['skip'](...)` chains through a computed property, not a `.word` —
    a shape this scanner does not resolve, so it must fail closed rather than
    silently read this as an ordinary, un-skipped `test` call."""
    before = "it('a', () => { expect(1).toBe(1); });\n"
    after = "it['skip']('a', () => { expect(1).toBe(1); });\n"
    assert "unparseable" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                   blocking=True)


def test_js_an_optional_call_test_declaration_fails_closed_rather_than_missing_it():
    """`test?.('a', fn)` -- an optional-call invocation of `test` itself --
    is a shape this scanner does not resolve, so it must fail closed rather
    than silently read this as an ordinary, un-skipped `test` call (external
    Tier-3 review, PR #685, eighth round: this was previously invisible
    entirely, dropping the test rather than blocking)."""
    before = "it('a', () => { expect(1).toBe(1); });\n"
    after = "it?.('a', () => { expect(1).toBe(1); });\n"
    assert "unparseable" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                   blocking=True)


def test_js_an_optional_chained_modifier_fails_closed_rather_than_missing_it():
    """`test?.skip('a', fn)` -- an optional-chained `.skip` modifier -- same
    fail-closed requirement as the bare optional call above."""
    before = "it('a', () => { expect(1).toBe(1); });\n"
    after = "it?.skip('a', () => { expect(1).toBe(1); });\n"
    assert "unparseable" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                   blocking=True)


def test_js_an_optional_chained_property_never_invoked_is_not_a_false_block():
    """The companion case: an optional-chained property reference that is
    NEVER actually invoked here is ordinary code, not a test declaration --
    same "invoked vs. not" distinction the fifth round's fix already applies
    to every other unrecognized chain shape."""
    before = "it('a', () => { expect(1).toBe(1); });\nconst helper = it?.customModifier;\n"
    after = "it('a', () => { expect(1).toBe(1); });\nconst runner = test?.concurrent;\n"
    assert aw.detect_weakening([_jschange(before, after)]) == []


def test_js_a_comment_mentioning_a_test_api_call_is_not_mistaken_for_one():
    """`_JS_NAME`/`_JS_ASSERT_HEAD` scan raw text; without the non-code spans
    from `_js_bracket_match`, a TODO like this would itself have been misread
    as a real `it.skip(...)` declaration (external spec review round 3)."""
    before = "it('a', () => { expect(1).toBe(1); });\n"
    after = ("// TODO: consider it.skip('a', () => { expect(0).toBe(0); });\n"
             "it('a', () => { expect(1).toBe(1); });\n")
    assert aw.detect_weakening([_jschange(before, after)]) == []


def test_js_a_comment_mentioning_expect_inside_a_test_is_not_counted():
    before = "it('a', () => {\n  // was: expect(2).toBe(2);\n  expect(1).toBe(1);\n});\n"
    after = "it('a', () => {\n  expect(1).toBe(1);\n});\n"
    assert aw.detect_weakening([_jschange(before, after)]) == []


def test_js_a_newly_added_only_shadows_its_siblings():
    """`it.only(...)` makes Jest/Vitest skip every OTHER test in the file at
    runtime, with no mark on the siblings themselves — an earlier revision
    recognized `.only` as a chain but gave it no effect, so this silenced a
    neighbor without touching its body at all (doubt review)."""
    before = ("it('a', () => { expect(1).toBe(1); });\n"
              "it('b', () => { expect(2).toBe(2); });\n")
    after = ("it.only('a', () => { expect(1).toBe(1); });\n"
             "it('b', () => { expect(2).toBe(2); });\n")
    findings = aw.detect_weakening([_jschange(before, after)])
    assert "skip_added" in _kinds(findings, blocking=True)
    assert any(f"{JS_TEST_PATH}::b" == f.subject for f in findings)


def test_js_a_describe_only_shadows_tests_outside_it():
    before = ("describe('A', () => { it('a', () => { expect(1).toBe(1); }); });\n"
              "it('b', () => { expect(2).toBe(2); });\n")
    after = ("describe.only('A', () => { it('a', () => { expect(1).toBe(1); }); });\n"
             "it('b', () => { expect(2).toBe(2); });\n")
    findings = aw.detect_weakening([_jschange(before, after)])
    assert "skip_added" in _kinds(findings, blocking=True)
    assert any(f"{JS_TEST_PATH}::b" == f.subject for f in findings)


def test_js_a_test_nested_under_describe_only_is_not_itself_shadowed():
    before = "describe.only('A', () => {\n  it('a', () => { expect(1).toBe(1); expect(2).toBe(2); });\n});\n"
    after = "describe.only('A', () => {\n  it('a', () => { expect(1).toBe(1); });\n});\n"
    findings = aw.detect_weakening([_jschange(before, after)])
    assert "assertions_removed" in _kinds(findings, blocking=True)
    assert "skip_added" not in _kinds(findings, blocking=True)


def test_js_removing_an_assertion_from_a_focused_fit_test_blocks():
    """`fit(...)` is Jasmine/Jest's own alias for `it.only(...)`, not a chain
    -- entirely invisible to `_JS_NAME` before this fix, so weakening inside
    one passed the gate with no finding at all (external Tier-3 review, PR
    #685, sixth round: a genuine false negative)."""
    before = "fit('a', () => { expect(1).toBe(1); expect(2).toBe(2); });\n"
    after = "fit('a', () => { expect(1).toBe(1); });\n"
    assert "assertions_removed" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                          blocking=True)


def test_js_removing_an_assertion_from_a_test_nested_under_fdescribe_blocks():
    """`fdescribe(...)` is Jasmine/Jest's own alias for `describe.only(...)`;
    same false-negative gap as `fit` above, for the nested-describe form."""
    before = "fdescribe('A', () => {\n  it('a', () => { expect(1).toBe(1); expect(2).toBe(2); });\n});\n"
    after = "fdescribe('A', () => {\n  it('a', () => { expect(1).toBe(1); });\n});\n"
    findings = aw.detect_weakening([_jschange(before, after)])
    assert "assertions_removed" in _kinds(findings, blocking=True)
    assert "skip_added" not in _kinds(findings, blocking=True)


def test_js_a_newly_focused_fit_shadows_its_siblings_like_only_does():
    """`fit` carries the same "everything else in the file is silently
    skipped at runtime" footgun as a written-out `.only` -- newly focusing
    one test with `fit` must produce the same `skip_added` finding on its
    un-focused sibling that `.only` does."""
    before = ("it('a', () => { expect(1).toBe(1); });\n"
              "it('b', () => { expect(2).toBe(2); });\n")
    after = ("fit('a', () => { expect(1).toBe(1); });\n"
             "it('b', () => { expect(2).toBe(2); });\n")
    findings = aw.detect_weakening([_jschange(before, after)])
    assert "skip_added" in _kinds(findings, blocking=True)
    assert any(f"{JS_TEST_PATH}::b" == f.subject for f in findings)


def test_js_a_dynamic_test_names_assertion_loss_is_still_caught():
    """`it(caseName, fn)` — a common data-driven-test pattern — resolves to a
    real call but has no string-literal name; dropping it outright made it
    invisible to diffing on both sides (doubt review, round 1). Pooled into
    one aggregate entry for the file instead."""
    before = "const name = 'a';\nit(name, () => { expect(1).toBe(1); expect(2).toBe(2); });\n"
    after = "const name = 'a';\nit(name, () => { expect(1).toBe(1); });\n"
    findings = aw.detect_weakening([_jschange(before, after)])
    assert "assertions_removed" in _kinds(findings, blocking=True)


def test_js_a_decoy_dynamic_test_softens_but_does_not_hide_a_real_loss():
    """An ordinal-keyed first attempt at this (round 1 fix) let a dynamic test
    inserted earlier in the same diff reoccupy a shifted test's key, comparing
    a real assertion loss against unrelated decoy content and hiding it
    entirely (doubt review, round 2). Pooling every dynamic-named test's
    assertions into one aggregate entry makes this order-independent: with
    DIFFERENT decoy assertion text (the ordinary case), the real loss still
    shows up, at minimum as a reported `assertion_changed`."""
    before = "const a = 'a';\nit(a, () => { expect(1).toBe(1); expect(2).toBe(2); });\n"
    after = (
        "const b = 'b';\nit(b, () => { expect(9).toBe(9); expect(8).toBe(8); });\n"
        "const a = 'a';\nit(a, () => { expect(1).toBe(1); });\n"
    )
    findings = aw.detect_weakening([_jschange(before, after)])
    assert findings != []


def test_js_a_decoy_with_identical_assertion_text_can_hide_a_real_loss():
    """Named, honest residual limit (doubt review, round 3): content-only
    pooling cannot distinguish "this assertion moved to another dynamic test"
    from "this assertion was deleted and an unrelated one happens to read the
    same" — realistic for table-driven tests sharing boilerplate assertions.
    Left open rather than silently left as a surprise; see `_js_collect`'s
    docstring. A body-hash-based best-effort pairing would close this but
    was judged not worth the added complexity for a residual, inherently
    unprovable-complete gap in anonymous-test identity."""
    before = "const a = 'a';\nit(a, () => { expect(result).toBe(true); expect(extra).toBe(1); });\n"
    after = (
        "const c = 'c';\nit(c, () => { expect(extra).toBe(1); });\n"
        "const a = 'a';\nit(a, () => { expect(result).toBe(true); });\n"
    )
    assert aw.detect_weakening([_jschange(before, after)]) == []


def test_js_a_test_named_like_the_dynamic_pool_sentinel_is_not_overwritten():
    """`it('<dynamically-named tests>', fn)` is syntactically valid JS — a
    real test with (nearly) that name must not collide with the pooled-
    dynamic-tests entry. The sentinel embeds a raw instance of all three
    quote delimiters (doubt review round 3, revised external Tier-3 review
    round 14), which already makes an exact collision structurally
    impossible — no single string literal can contain an unescaped copy of
    its own delimiter — so this checks the near-miss case stays a distinct,
    independently-tracked entry."""
    before = ("const c = 'c';\nit(c, () => { expect(9).toBe(9); });\n"
              "it('<dynamically-named tests>', () => { expect(1).toBe(1); expect(2).toBe(2); });\n")
    after = ("const c = 'c';\nit(c, () => { expect(9).toBe(9); });\n"
             "it('<dynamically-named tests>', () => { expect(1).toBe(1); });\n")
    findings = aw.detect_weakening([_jschange(before, after)])
    assert "assertions_removed" in _kinds(findings, blocking=True)
    assert any(f.subject.endswith("<dynamically-named tests>") for f in findings)


def test_js_a_crafted_template_literal_name_does_not_collide_with_the_dynamic_pool():
    """External Tier-3 review, PR #685 (fourteenth round, blocking): the
    prior sentinel was just `<dynamically-named tests>` plus a trailing raw
    newline -- reachable from a template literal (which, unlike single/
    double-quoted strings, can legally contain a raw newline), so a test
    whose template-literal name happened to match that exact text plus a
    newline would pool together with genuinely dynamic-named tests, letting
    one side's assertion loss cancel out against the other's gain in the
    combined pooled aggregate -- the exact kind of silent clear this
    scanner's own pooling design otherwise goes out of its way to avoid."""
    src = (
        "const dynamicName = 'x';\n"
        "it(dynamicName, () => { expect(1).toBe(1); });\n"
        "it(`<dynamically-named tests>\n`, () => { expect(2).toBe(2); });\n"
    )
    result = aw._js_collect(src)
    assert result is not None
    assert len(result) == 2


def test_js_duplicate_literal_test_names_are_pooled_not_ordinal_keyed():
    """Two `it('works', ...)` calls sharing one literal title — ordinary
    Jest/Vitest style across different `describe` blocks — used to be keyed
    `works` / `works#2` by scan order. A decoy inserted earlier in the diff
    could reoccupy the `works` ordinal and launder a real loss in the shifted
    test into a comparison against unrelated content (doubt review, round 4;
    the identical exposure round 2 already fixed for dynamic names). Pooling
    every same-named test together, the same way, makes this order-
    independent: the aggregate assertion count still drops when one is
    genuinely removed."""
    before = (
        "describe('A', () => { it('works', () => { expect(1).toBe(1); expect(2).toBe(2); }); });\n"
        "describe('B', () => { it('works', () => { expect(3).toBe(3); }); });\n"
    )
    after = (
        "describe('A', () => { it('works', () => { expect(1).toBe(1); }); });\n"
        "describe('B', () => { it('works', () => { expect(3).toBe(3); }); });\n"
    )
    findings = aw.detect_weakening([_jschange(before, after)])
    assert "assertions_removed" in _kinds(findings, blocking=True)


def test_js_a_decoy_reusing_a_literal_test_name_softens_but_does_not_hide_a_real_loss():
    """The round-4 PoC: a decoy `describe('C', ...)` reusing title `'works'`
    is inserted BEFORE the test that actually loses an assertion. Under the
    old ordinal keying this fully hid the loss (`works` compared decoy-vs-
    original-A, `works#2` compared old-A-content vs B, the real A-vs-A
    comparison never happened). Pooling makes it order-independent: with
    DIFFERENT decoy assertion text (the ordinary case), the real loss still
    surfaces, at minimum as a reported `assertion_changed`."""
    before = (
        "describe('A', () => { it('works', () => { expect(1).toBe(1); expect(2).toBe(2); }); });\n"
        "describe('B', () => { it('works', () => { expect(3).toBe(3); }); });\n"
    )
    after = (
        "describe('C', () => { it('works', () => { expect(9).toBe(9); expect(8).toBe(8); }); });\n"
        "describe('A', () => { it('works', () => { expect(1).toBe(1); }); });\n"
        "describe('B', () => { it('works', () => { expect(3).toBe(3); }); });\n"
    )
    findings = aw.detect_weakening([_jschange(before, after)])
    assert findings != []


def test_js_a_new_skip_on_one_pooled_instance_is_caught_even_if_another_was_already_skipped():
    """Pooling marks as a plain set (round 4) made a genuinely new `.skip` on
    one same-named test invisible whenever ANOTHER pooled instance already
    carried `skip` before the change — no reordering or decoy needed, just an
    ordinary pre-existing skipped duplicate-named test elsewhere in the file
    (doubt review, round 5). Marks are now a multiset, keyed on occurrence
    COUNT increasing, the same "quantity, not presence" floor assertions
    already get."""
    before = "it('works', () => { expect(1).toBe(1); });\nit.skip('works', () => { expect(2).toBe(2); });\n"
    after = "it.skip('works', () => { expect(1).toBe(1); });\nit.skip('works', () => { expect(2).toBe(2); });\n"
    findings = aw.detect_weakening([_jschange(before, after)])
    assert "skip_added" in _kinds(findings, blocking=True)


def test_js_removing_an_empty_skip_stub_while_skipping_its_real_sibling_is_not_a_silent_clear():
    """The round-6 PoC: an empty-bodied, already-skipped `it.skip('works', () => {})`
    placeholder is removed in the SAME edit that newly `.skip`'s a real,
    assertion-bearing `it('works', ...)` sibling. The "skip" mark's pooled
    occurrence count stays flat (1 before, 1 after — it just relocated), and
    the removed stub contributed zero assertions, so neither the mark-count
    nor the assertion-count check sees any change: `verdict()` came out
    `clear` (doubt review, round 6). Tracking pooled instance count and
    reporting a decrease turns this into a `review` verdict instead."""
    before = "it('works', () => { expect(1).toBe(1); });\nit.skip('works', () => {});\n"
    after = "it.skip('works', () => { expect(1).toBe(1); });\n"
    findings = aw.detect_weakening([_jschange(before, after)])
    assert findings != []
    assert aw.verdict(findings) != "clear"
    assert "pooled_test_instance_lost" in _kinds(findings, blocking=False)


def test_js_a_skip_swap_between_two_surviving_pooled_instances_is_caught_by_exact_content_match():
    """The round-7 PoC: TWO same-titled tests both survive (`instance_count`
    unchanged), and their assertion bodies are untouched — only WHICH
    physical instance carries `.skip` is swapped. The pool's aggregate
    assertion multiset is identical and the aggregate skip-mark count is
    identical (1 before, 1 after — it just relocated), so `instance_count`
    and the aggregate mark-count check both see no change — but because the
    two instances have distinct, non-colliding assertion content, an exact
    content bijection recovers which physical instance gained the skip
    (doubt review, round 8; `_relocated_mark_findings`)."""
    before = (
        "it('works', () => { expect(1).toBe(1); });\n"
        "it.skip('works', () => { expect(2).toBe(2); });\n"
    )
    after = (
        "it.skip('works', () => { expect(1).toBe(1); });\n"
        "it('works', () => { expect(2).toBe(2); });\n"
    )
    findings = aw.detect_weakening([_jschange(before, after)])
    assert "skip_added" in _kinds(findings, blocking=True)


def test_js_a_skip_swap_is_still_blocked_alongside_an_unrelated_conserved_decoy_pair():
    """Doubt review, round 9 then round 11: two unrelated, mutually-identical
    decoy instances elsewhere in the pool (ordinary boilerplate duplication)
    are PRESENT WITH THE SAME COUNT before and after — untouched, they add no
    new text and erase none, so they cannot supply round 10's coincidental-
    collision material. `full_bijection` is Counter equality, not "every
    count is 1", so this conserved duplicate does not downgrade the swap's
    own genuinely unambiguous match: it still blocks."""
    before = (
        "it('works', () => { expect(1).toBe(1); });\n"
        "it.skip('works', () => { expect(2).toBe(2); });\n"
        "it('works', () => { expect(3).toBe(3); });\n"
        "it('works', () => { expect(3).toBe(3); });\n"
    )
    after = (
        "it.skip('works', () => { expect(1).toBe(1); });\n"
        "it('works', () => { expect(2).toBe(2); });\n"
        "it('works', () => { expect(3).toBe(3); });\n"
        "it('works', () => { expect(3).toBe(3); });\n"
    )
    findings = aw.detect_weakening([_jschange(before, after)])
    assert "skip_added" in _kinds(findings, blocking=True)
    assert aw.verdict(findings) != "clear"


def test_js_a_skip_swap_is_reported_not_blocked_alongside_an_unrelated_sibling_content_edit():
    """Doubt review, round 9 then round 10: an ORDINARY, unrelated edit to a
    completely different same-titled sibling (a routine value fix, no
    ambiguity of its own) means the pool is not a full bijection, so the
    swap's own otherwise-clean key match is reported rather than blocked —
    the sibling's edit means a coincidental text collision can't be ruled
    out (round 10)."""
    before = (
        "it('works', () => { expect(1).toBe(1); });\n"
        "it.skip('works', () => { expect(2).toBe(2); });\n"
        "it('works', () => { expect(3).toBe(3); });\n"
    )
    after = (
        "it.skip('works', () => { expect(1).toBe(1); });\n"
        "it('works', () => { expect(2).toBe(2); });\n"
        "it('works', () => { expect(4).toBe(4); });\n"
    )
    findings = aw.detect_weakening([_jschange(before, after)])
    assert "skip_added" not in _kinds(findings, blocking=True)
    assert "pooled_mark_possibly_relocated" in _kinds(findings, blocking=False)


def test_js_a_coincidental_content_collision_across_an_unrelated_edit_is_not_blocked():
    """Doubt review, round 10: the exact false-positive a full-pool-bijection
    requirement exists to prevent. `B`'s NEW text happens to equal `A`'s OLD
    text (a coincidence, not the same instance persisting), while `A` is
    independently rewritten to something else entirely. A per-key-only match
    would misread the coincidentally-matching key as "this instance gained a
    skip" and BLOCK a diff that introduced no real weakening at all — this
    file's own stated design blocks only unambiguous loss, so this must be at
    most reported, never blocked."""
    before = (
        "it('works', () => { expect(status).toBe(200); });\n"
        "it.skip('works', () => { expect(other).toBe(1); });\n"
    )
    after = (
        "it('works', () => { expect(newThing).toBe(42); });\n"
        "it.skip('works', () => { expect(status).toBe(200); });\n"
    )
    findings = aw.detect_weakening([_jschange(before, after)])
    assert "skip_added" not in _kinds(findings, blocking=True)


def test_js_two_identically_asserted_instances_swapping_skip_still_defeats_the_bijection():
    """Named, honest residual limit (doubt review, round 8): the exact-
    content matching that closes the round-7 gap only works when the two
    instances' assertion content is DISTINGUISHABLE. If both instances assert
    the identical thing (realistic for boilerplate-heavy table-driven tests),
    that content key occurs twice on each side, so `_relocated_mark_findings`
    skips it (no unique key to hang the comparison on) — the same
    content-collision residual round 3 already named, not a new one."""
    before = (
        "it('works', () => { expect(1).toBe(1); });\n"
        "it.skip('works', () => { expect(1).toBe(1); });\n"
    )
    after = (
        "it.skip('works', () => { expect(1).toBe(1); });\n"
        "it('works', () => { expect(1).toBe(1); });\n"
    )
    assert aw.detect_weakening([_jschange(before, after)]) == []


def test_js_a_regex_literal_with_a_lone_bracket_is_parsed_not_a_false_block():
    """`_js_bracket_match` now lexes regex literals as non-code spans, so a
    bracket character inside one (`/\\(/`) no longer desyncs the bracket
    stack. Removing the real assertion alongside it is still caught
    correctly -- this is a genuine fix, not a downgrade to `n/a` (external
    Tier-3 review, PR #685, third round: this exact file previously
    documented the false block as an accepted limit; the reviewer escalated
    it to a hard BLOCK because it blocks every future repair to any test
    file using a regex literal with a bracket in it, not just one edit)."""
    before = "it('a', () => { expect(x).toMatch(/\\(/); expect(1).toBe(1); });\n"
    after = "it('a', () => { expect(x).toMatch(/\\(/); });\n"
    kinds = _kinds(aw.detect_weakening([_jschange(before, after)]), blocking=True)
    assert "unparseable" not in kinds
    assert "assertions_removed" in kinds


def test_js_a_regex_literal_right_after_an_if_condition_is_not_a_false_block():
    """`if (enabled) /\\[/.test(value);` is valid JS -- a regex literal can
    open right after a control-flow condition's closing `)`, not just after
    an operator/keyword. `_js_slash_starts_regex` treated every `)` as
    division unconditionally, so the escaped `[` inside the regex read as an
    unmatched structural bracket and blocked the repair (external Tier-3
    review, PR #685, seventh round)."""
    before = ("it('a', () => {\n"
              "  if (enabled) /\\[/.test(value);\n"
              "  expect(1).toBe(1);\n"
              "});\n")
    after = ("it('a', () => {\n"
             "  if (enabled) /\\[/.test(value);\n"
             "});\n")
    kinds = _kinds(aw.detect_weakening([_jschange(before, after)]), blocking=True)
    assert "unparseable" not in kinds
    assert "assertions_removed" in kinds


def test_js_division_right_after_a_grouping_paren_is_still_division():
    """`(a + b) / c` -- a plain grouping expression, not a control-flow
    condition -- must still read as division after the `)`, the companion
    case to the if-condition test above."""
    before = "it('a', () => { const r = (a + b) / c; expect(r).toBe(1); });\n"
    after = "it('a', () => { const r = (a + b) / c; });\n"
    kinds = _kinds(aw.detect_weakening([_jschange(before, after)]), blocking=True)
    assert "unparseable" not in kinds
    assert "assertions_removed" in kinds


def test_js_a_comment_between_if_and_its_condition_paren_is_not_a_false_block():
    """`if /* c */ (enabled) /\\[/.test(value);` -- a comment between the
    keyword and its condition paren must not hide the keyword from
    `_js_word_before`, or the regex right after the `)` misreads as division
    and its escaped bracket corrupts bracket tracking (external Tier-3
    review, PR #685, tenth round)."""
    before = ("it('a', () => {\n"
              "  if /* c */ (enabled) /\\[/.test(value);\n"
              "  expect(1).toBe(1);\n"
              "});\n")
    after = ("it('a', () => {\n"
             "  if /* c */ (enabled) /\\[/.test(value);\n"
             "});\n")
    kinds = _kinds(aw.detect_weakening([_jschange(before, after)]), blocking=True)
    assert "unparseable" not in kinds
    assert "assertions_removed" in kinds


def test_js_a_comment_between_while_and_its_condition_paren_is_not_a_false_block():
    """Same requirement as the `if` case above, for `while`."""
    before = ("it('a', () => {\n"
              "  while // c\n"
              "  (enabled) /\\[/.test(value);\n"
              "  expect(1).toBe(1);\n"
              "});\n")
    after = ("it('a', () => {\n"
             "  while // c\n"
             "  (enabled) /\\[/.test(value);\n"
             "});\n")
    kinds = _kinds(aw.detect_weakening([_jschange(before, after)]), blocking=True)
    assert "unparseable" not in kinds
    assert "assertions_removed" in kinds


def test_js_a_comment_between_for_and_its_condition_paren_is_not_a_false_block():
    """Same requirement as the `if` case above, for `for`."""
    before = ("it('a', () => {\n"
              "  for /* c */ (let i = 0; i < 1; i++) /\\[/.test(value);\n"
              "  expect(1).toBe(1);\n"
              "});\n")
    after = ("it('a', () => {\n"
             "  for /* c */ (let i = 0; i < 1; i++) /\\[/.test(value);\n"
             "});\n")
    kinds = _kinds(aw.detect_weakening([_jschange(before, after)]), blocking=True)
    assert "unparseable" not in kinds
    assert "assertions_removed" in kinds


def test_js_a_character_class_containing_a_slash_does_not_end_the_regex_early():
    """`/[a/b]/` must not be misread as ending at the `/` inside the
    character class -- `_js_regex_literal_end` tracks `[`/`]` state so an
    in-class `/` doesn't terminate the literal early and desync the scan
    that follows."""
    before = "it('a', () => { expect('a').toMatch(/[a/b]/); expect(1).toBe(1); });\n"
    after = "it('a', () => { expect('a').toMatch(/[a/b]/); });\n"
    kinds = _kinds(aw.detect_weakening([_jschange(before, after)]), blocking=True)
    assert "unparseable" not in kinds
    assert "assertions_removed" in kinds


def test_js_division_after_a_value_is_not_mistaken_for_a_regex_literal():
    """`a / b` (division, following an identifier) must not be swallowed as
    a regex-literal span -- `_js_slash_starts_regex` returns False right
    after a value, so the brackets in the surrounding real code still
    balance correctly."""
    before = "it('a', () => { const r = a / b; expect(r).toBe(1); });\n"
    after = "it('a', () => { const r = a / b; });\n"
    kinds = _kinds(aw.detect_weakening([_jschange(before, after)]), blocking=True)
    assert "unparseable" not in kinds
    assert "assertions_removed" in kinds


def test_js_an_unrecognized_chain_never_invoked_is_not_a_false_block():
    """`const helper = it.customModifier;` is a plain property reference, not
    a test declaration -- the chain (`.customModifier`) is unrecognized, but
    since it is never actually called here there is nothing to weaken.
    Before this fix, ANY unrecognized chain failed closed regardless of
    whether it was invoked, blocking ordinary non-test code (external Tier-3
    review, PR #685, fifth round)."""
    before = "it('a', () => { expect(1).toBe(1); });\nconst helper = it.customModifier;\n"
    after = "it('a', () => { expect(1).toBe(1); });\nconst runner = test.concurrent;\n"
    assert aw.detect_weakening([_jschange(before, after)]) == []


def test_js_an_unrecognized_chain_that_is_actually_invoked_still_fails_closed():
    """The companion case to the test above: once an unrecognized chain is
    actually CALLED (`test.concurrent(...)`), this scanner still cannot
    safely interpret it and must keep failing closed -- the fix narrows the
    blocking path to invoked chains, it does not remove it."""
    before = "test.concurrent('a', async () => { expect(1).toBe(1); });\n"
    after = ("test.concurrent('a', async () => { expect(1).toBe(1); });\n"
             "const runner = test.concurrent;\n")
    assert "unparseable" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                   blocking=True)


def test_js_an_unterminated_string_in_the_after_revision_fails_closed_as_unparseable():
    """An unterminated quoted string is not valid JS/TS. Before the fix,
    `_js_bracket_match` advanced to end-of-file and returned a (bogus)
    balanced bracket map instead of failing closed, so a genuinely
    non-compiling repair could pass this safety gate silently (external
    Tier-3 review, PR #685, fourth round: blocking finding)."""
    before = "it('a', () => { expect(1).toBe(1); });\n"
    after = "it('a', () => { const s = 'unterminated; expect(1).toBe(1); });\n"
    assert "unparseable" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                   blocking=True)


def test_js_an_unterminated_block_comment_in_the_after_revision_fails_closed_as_unparseable():
    """Same fail-closed requirement as the unterminated-string case above,
    for an unterminated `/* ... */` block comment."""
    before = "it('a', () => { expect(1).toBe(1); });\n"
    after = "it('a', () => { /* unterminated expect(1).toBe(1); });\n"
    assert "unparseable" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                   blocking=True)


def test_js_string_literal_regex_does_not_exponentially_backtrack_on_a_run_of_backslashes():
    """CodeQL (high severity, this run's own PR check): the original
    `_JS_STRING_LIT` body was `(?:\\\\.|(?!\\1).)*` -- a backslash could be
    consumed either as the start of `\\\\.` or as the plain char matched by
    `(?!\\1).`, so a long unterminated run of backslashes had an exponential
    number of ways to fail. Three explicit non-overlapping alternatives fixed
    it; this pins that a large adversarial input still resolves near-instantly
    rather than hanging."""
    import time

    evil = 'it("' + "\\a" * 20000
    start = time.monotonic()
    aw._JS_STRING_LIT.match(evil)
    assert time.monotonic() - start < 2.0


def test_js_string_literal_still_allows_a_different_quote_character_as_literal_content():
    """The fix's per-alternative exclusion set only excludes the string's OWN
    delimiter (plus backslash), not all three quote characters -- otherwise
    `"it's a test"` would truncate at the apostrophe instead of reading the
    whole literal."""
    m = aw._JS_STRING_LIT.match("\"it's a test\"")
    assert m is not None
    body = m.group(1) if m.group(1) is not None else (
        m.group(2) if m.group(2) is not None else m.group(3)
    )
    assert body == "it's a test"


def test_js_a_member_style_helper_call_named_test_is_not_treated_as_a_declaration():
    """External Tier-3 review, PR #685 (blocking): `fixture.test('case', fn)`
    is an ordinary helper method call, not a Jest/Vitest `test(...)` — the
    scanner used to match the bare word `test` regardless of what preceded
    it, so removing an assertion from inside that helper produced a
    blocking finding for a change that touched no real test."""
    before = (
        "it('real', () => { expect(1).toBe(1); });\n"
        "fixture.test('case', () => { helper(); expect(2).toBe(2); });\n"
    )
    after = (
        "it('real', () => { expect(1).toBe(1); });\n"
        "fixture.test('case', () => { helper(); });\n"
    )
    assert _kinds(aw.detect_weakening([_jschange(before, after)]), blocking=True) == []


def test_js_a_function_declaration_named_test_is_not_treated_as_a_call():
    """A `function test(name, fn) { ... }` declaration's parameter list reads
    identically to a call's argument list at the token level. Editing its
    body must not be read as editing a real `test(...)` call (external
    Tier-3 review, PR #685, non-blocking comment)."""
    before = (
        "function test(name, fn) { expect(name).toBeTruthy(); helper(); }\n"
        "it('real', () => { expect(1).toBe(1); });\n"
    )
    after = (
        "function test(name, fn) { helper(); }\n"
        "it('real', () => { expect(1).toBe(1); });\n"
    )
    assert _kinds(aw.detect_weakening([_jschange(before, after)]), blocking=True) == []


def test_a_python_test_renamed_to_a_js_test_path_is_not_flagged_as_removed():
    """Cross-language rename: both ends are still test-collected — this is a
    stated limit (content isn't re-diffed across languages), not a removal."""
    findings = aw.detect_weakening([
        _jschange("def test_a():\n    assert 1\n",
                  "it('a', () => { expect(1).toBe(1); });\n",
                  status="R", path=JS_TEST_PATH, old_path="tests/test_thing.py")
    ])
    assert "test_removed_by_rename" not in _kinds(findings, blocking=True)


def test_js_a_malformed_template_interpolation_in_after_revision_fails_closed():
    """External Tier-3 review, PR #685 (eleventh round, blocking): a
    template literal used to be skipped as one opaque span from backtick to
    backtick, so a `${...}` interpolation's own unbalanced bracket was
    invisible — this after revision has a `${(}` interpolation whose `(`
    never closes, and must be reported `unparseable`, the same fail-closed
    shape as any other unbalanced after revision."""
    before = "it(`case ${1}`, () => { expect(1).toBe(1); });\n"
    after = "it(`case ${(}`, () => { expect(1).toBe(1); });\n"
    assert "unparseable" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                   blocking=True)


def test_js_a_valid_template_interpolation_is_not_a_false_block():
    """The other side of the same fix: an ordinary, balanced `${...}`
    interpolation (dynamic test names are extremely common in real suites)
    must keep scanning cleanly, not regress into a false `unparseable`."""
    before = "it(`case ${1 + 1}`, () => { expect(1).toBe(1); });\n"
    after = "it(`case ${1 + 1}`, () => { expect(1).toBe(2); });\n"
    findings = aw.detect_weakening([_jschange(before, after)])
    assert _kinds(findings, blocking=True) == []
    assert "assertion_changed" in _kinds(findings, blocking=False)


def test_js_an_assertion_inside_a_template_interpolation_is_visible():
    """Side effect of recursive interpolation scanning: an interpolation's
    body is now real code to the scanners, not opaque text, so an assertion
    removed from inside one is caught the same as anywhere else (closes a
    fourth-round non-blocking comment about executable interpolations being
    invisible)."""
    before = "it('a', () => { const label = `${expect(1).toBe(1) && 'ok'}`; expect(2).toBe(2); });\n"
    after = "it('a', () => { const label = `${'ok'}`; expect(2).toBe(2); });\n"
    findings = aw.detect_weakening([_jschange(before, after)])
    assert "assertions_removed" in _kinds(findings, blocking=True)


def test_js_a_newly_added_fit_each_focus_blocks_its_siblings():
    """External Tier-3 review, PR #685 (twelfth round, blocking): claimed
    `fit.each(...)` is treated as an ordinary `.each` call with no `.only`
    effect, so a newly-focused parametrized test would silently shadow its
    siblings with no finding. Traced and reproduced directly against
    `_js_collect`: `fit`/`fdescribe` already get `mod = \"only\"` whenever the
    formula above leaves `mod` as `None` -- which chain `.each` alone also
    does -- so `fit.each(...)` already composes correctly and this already
    blocks. The one real gap the review surfaced was test coverage, not
    behavior; this and the next three tests close it."""
    before = ("describe('suite', () => {\n"
              "  it.each([[1]])('a %i', (a) => { expect(a).toBe(1); });\n"
              "  it('sibling', () => { expect(2).toBe(2); });\n});\n")
    after = ("describe('suite', () => {\n"
             "  fit.each([[1]])('a %i', (a) => { expect(a).toBe(1); });\n"
             "  it('sibling', () => { expect(2).toBe(2); });\n});\n")
    assert "skip_added" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                  blocking=True)


def test_js_a_newly_added_fit_each_tagged_template_focus_blocks_its_siblings():
    """Same claim, the other documented `.each` form (tagged-template table,
    no parens) -- also already correct, also uncovered before this round."""
    before = ("describe('suite', () => {\n"
              "  it.each`a | b\n${1} | ${1}`('adds %s', ({a, b}) => { expect(a).toBe(b); });\n"
              "  it('sibling', () => { expect(2).toBe(2); });\n});\n")
    after = ("describe('suite', () => {\n"
             "  fit.each`a | b\n${1} | ${1}`('adds %s', ({a, b}) => { expect(a).toBe(b); });\n"
             "  it('sibling', () => { expect(2).toBe(2); });\n});\n")
    assert "skip_added" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                  blocking=True)


def test_js_a_newly_added_fdescribe_each_focus_blocks_its_siblings():
    """`fdescribe.each(...)` half of the same claim: a newly-focused
    parametrized describe block must shadow every OTHER top-level test."""
    before = ("describe.each([[1]])('suite %i', (a) => {\n"
              "  it('one', () => { expect(a).toBe(1); });\n});\n"
              "describe('other', () => {\n"
              "  it('two', () => { expect(2).toBe(2); });\n});\n")
    after = ("fdescribe.each([[1]])('suite %i', (a) => {\n"
             "  it('one', () => { expect(a).toBe(1); });\n});\n"
             "describe('other', () => {\n"
             "  it('two', () => { expect(2).toBe(2); });\n});\n")
    assert "skip_added" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                  blocking=True)


def test_js_an_unescaped_lf_inside_a_single_quoted_string_fails_closed():
    """External Tier-3 review, PR #685 (thirteenth round, blocking): a
    single/double-quoted string cannot legally contain a raw, unescaped
    line terminator -- unlike a template literal, which can. Treating one
    as ordinary string content let the scanner run past the line where the
    string was actually supposed to end, silently swallowing real code
    (here, the entire rest of the test) as "string content"."""
    before = "it('a', () => { expect(1).toBe(1); });\n"
    after = "it('a\nb', () => { expect(1).toBe(1); });\n"
    assert "unparseable" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                   blocking=True)


def test_js_an_unescaped_crlf_inside_a_double_quoted_string_fails_closed():
    """Same claim, the other named newline form (CRLF) and the other quote
    character (double quotes) -- both explicitly asked for by the review."""
    before = 'it("a", () => { expect(1).toBe(1); });\n'
    after = 'it("a\r\nb", () => { expect(1).toBe(1); });\r\n'
    assert "unparseable" in _kinds(aw.detect_weakening([_jschange(before, after)]),
                                   blocking=True)


def test_js_a_backslash_line_continuation_inside_a_string_is_not_a_false_block():
    """The other side of the same fix: a backslash immediately before a line
    terminator is a legal escape (line continuation) -- must not regress
    into a false `unparseable`. The test name's literal source text (an
    identity key elsewhere in this scanner) is unchanged across revisions;
    only the matcher argument changes, isolating this from a rename."""
    before = "it('a\\\nb', () => { expect(1).toBe(1); });\n"
    after = "it('a\\\nb', () => { expect(1).toBe(2); });\n"
    findings = aw.detect_weakening([_jschange(before, after)])
    assert _kinds(findings, blocking=True) == []
