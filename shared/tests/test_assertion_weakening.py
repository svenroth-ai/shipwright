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


def test_a_changed_non_python_test_file_is_refused_not_waved_through():
    findings = aw.detect_weakening([
        _change("it('x')", "it.skip('x')", path="e2e/tests/login.spec.ts")
    ])
    assert "unsupported_test_file" in _kinds(findings, blocking=True)


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
