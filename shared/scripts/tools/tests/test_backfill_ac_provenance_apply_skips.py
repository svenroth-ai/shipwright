"""``_backfill_ac_provenance_apply.py``'s skip-branches (non-Python candidate
file, file-absent-at-head, unreadable file, ``SyntaxError`` during test
enumeration) and the decorator-only substitution guard. Split out of
``test_backfill_ac_provenance_cli.py`` at the 300-LOC bloat-baseline
threshold (same precedent as the git-correlation split into
``test_backfill_ac_provenance_cli_git.py``).

Diff-coverage follow-up (P3.4, F0 chained gate): these branches were the last
uncovered lines in ``_backfill_ac_provenance_apply.py`` after the initial
write pass, upgrade pass, and idempotency tests already in the sibling file.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1]
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

_APPLY_SPEC = importlib.util.spec_from_file_location(
    "backfill_ac_provenance_apply_skips", _TOOLS / "_backfill_ac_provenance_apply.py",
)
apply_mod = importlib.util.module_from_spec(_APPLY_SPEC)
_APPLY_SPEC.loader.exec_module(apply_mod)  # type: ignore[union-attr]


def _candidate(fr_id, ac_id, files, status="candidate"):
    return {"fr_id": fr_id, "ac_id": ac_id, "slug": f"iterate-{fr_id}-{ac_id}".lower(),
             "commit": "deadbeef", "status": status, "test_files": list(files)}


_BARE_TAGGED_WITH_DECOY = '''"""Docstring mentions covers("FR-01.01") but is not a decorator."""
from __future__ import annotations

import pytest

# A comment could also say covers("FR-01.01") and must not be touched.


@pytest.mark.covers("FR-01.01")
def test_one():
    """Assertion text: covers("FR-01.01") appears here too, still not a decorator."""
    assert True
'''


def test_apply_upgrades_skips_a_non_python_candidate_file(tmp_path):
    rel = "tests/fixture.json"
    (tmp_path / "tests").mkdir()
    (tmp_path / rel).write_text("{}", encoding="utf-8")
    report = {"candidates": [_candidate("FR-01.01", "AC01", [rel])]}
    result = apply_mod.apply_upgrades(tmp_path, report)
    assert result["skipped"] == [{**_candidate("FR-01.01", "AC01", [rel]),
                                    "file": rel, "reason": "non_python_writer_not_built"}]


def test_apply_upgrades_skips_a_file_absent_at_head(tmp_path):
    rel = "tests/test_gone.py"  # never created
    report = {"candidates": [_candidate("FR-01.01", "AC01", [rel])]}
    result = apply_mod.apply_upgrades(tmp_path, report)
    assert result["skipped"] == [{**_candidate("FR-01.01", "AC01", [rel]),
                                    "file": rel, "reason": "file_absent_at_head"}]


def test_apply_upgrades_skips_an_unreadable_file(tmp_path):
    rel = "tests/test_binary.py"
    (tmp_path / "tests").mkdir()
    # Invalid UTF-8 bytes -- read_text(encoding="utf-8") raises UnicodeDecodeError.
    (tmp_path / rel).write_bytes(b"\xff\xfe\x00\x00not valid utf-8")
    report = {"candidates": [_candidate("FR-01.01", "AC01", [rel])]}
    result = apply_mod.apply_upgrades(tmp_path, report)
    assert result["skipped"] == [{**_candidate("FR-01.01", "AC01", [rel]),
                                    "file": rel, "reason": "unreadable"}]


def test_enumerate_python_tests_returns_nothing_for_a_syntax_error(tmp_path):
    # `_enumerate_python_tests` is reached only via a file with no bare tag to
    # widen -- exercise it directly for the SyntaxError branch, the same way
    # the module's own docstring says a malformed file must never crash the run.
    assert apply_mod._enumerate_python_tests("def test_x(:\n    pass\n") == []


def test_apply_upgrades_only_rewrites_the_real_decorator_never_lookalike_text(tmp_path):
    """External code review (P3.4, openai high): a raw whole-file regex
    substitution would also rewrite a same-looking ``covers("FR-01.01")``
    string sitting in a docstring, a comment, or an assertion. Only the ONE
    real ``@pytest.mark.covers(...)`` decorator line may change."""
    rel = "tests/test_decoy.py"
    (tmp_path / "tests").mkdir()
    (tmp_path / rel).write_text(_BARE_TAGGED_WITH_DECOY, encoding="utf-8")
    report = {"candidates": [_candidate("FR-01.01", "AC01", [rel])]}
    result = apply_mod.apply_upgrades(tmp_path, report)
    assert result["tags_upgraded_total"] == 1
    text = (tmp_path / rel).read_text(encoding="utf-8")
    assert text.count('covers("FR-01.01/AC01")') == 1  # the real decorator, upgraded
    assert text.count('covers("FR-01.01")') == 3        # docstring + comment + assertion, untouched


_TWO_TESTS_SAME_BARE_FR = '''from __future__ import annotations

import pytest


@pytest.mark.covers("FR-01.01")
def test_alpha():
    assert True


@pytest.mark.covers("FR-01.01")
def test_beta():
    assert False
'''


def test_apply_upgrades_skips_ambiguous_when_two_tests_share_the_bare_fr_tag(tmp_path):
    """External code review (P3.4 high): upgrading EVERY matching decorator
    line regardless of which test it belongs to can silently assign one AC to
    an unrelated test. Two tests sharing a bare FR tag for different reasons
    must be reported as ambiguous, with NEITHER line touched."""
    rel = "tests/test_ambiguous.py"
    (tmp_path / "tests").mkdir()
    (tmp_path / rel).write_text(_TWO_TESTS_SAME_BARE_FR, encoding="utf-8")
    report = {"candidates": [_candidate("FR-01.01", "AC01", [rel])]}
    result = apply_mod.apply_upgrades(tmp_path, report)
    assert result["tags_upgraded_total"] == 0
    assert result["tags_inserted_total"] == 0
    assert result["skipped"] == [{**_candidate("FR-01.01", "AC01", [rel]),
                                    "file": rel, "reason": "ambiguous_multiple_bare_tags_same_fr"}]
    text = (tmp_path / rel).read_text(encoding="utf-8")
    assert text == _TWO_TESTS_SAME_BARE_FR  # untouched — neither decorator was guessed at


def test_enumerate_python_tests_qualifies_by_enclosing_class():
    """External code review (P3.4 high): an unqualified ``name`` collides for
    two same-named methods in different classes. ``_enumerate_python_tests``
    must return an AST-qualified name (``ClassName.test_name``) instead."""
    source = (
        "class TestOne:\n"
        "    def test_it(self):\n"
        "        pass\n"
        "\n"
        "class TestTwo:\n"
        "    def test_it(self):\n"
        "        pass\n"
        "\n"
        "def test_module_level():\n"
        "    pass\n"
    )
    names = [qualname for qualname, _decl_line, _indent in apply_mod._enumerate_python_tests(source)]
    assert names == ["TestOne.test_it", "TestTwo.test_it", "test_module_level"]


_TWO_CLASSES_SAME_METHOD_NAME = '''from __future__ import annotations


class TestOne:
    def test_it(self):
        assert True


class TestTwo:
    def test_it(self):
        assert False
'''


def test_apply_upgrades_skips_ambiguous_when_a_file_has_two_untagged_tests(tmp_path):
    """Tier-3 CI-gate re-review (P3.4 high): file provenance ("this commit
    added this file") establishes the FILE is relevant, never WHICH untagged
    test inside it — tagging every untagged test identically is the same
    file-level attribution the D1 mistagging incident's general shape
    describes. Two untagged tests (even in different classes, so their
    unqualified names collide too) must be reported as ambiguous, with
    NEITHER tagged."""
    rel = "tests/test_two_classes.py"
    (tmp_path / "tests").mkdir()
    (tmp_path / rel).write_text(_TWO_CLASSES_SAME_METHOD_NAME, encoding="utf-8")
    report = {"candidates": [_candidate("FR-01.01", "AC01", [rel])]}
    result = apply_mod.apply_upgrades(tmp_path, report)
    assert result["tags_inserted_total"] == 0
    assert result["skipped"] == [{**_candidate("FR-01.01", "AC01", [rel]),
                                    "file": rel, "reason": "ambiguous_multiple_untagged_tests_in_file"}]
    text = (tmp_path / rel).read_text(encoding="utf-8")
    assert text == _TWO_CLASSES_SAME_METHOD_NAME  # untouched — neither test was guessed at


_ONE_CLASS_ONE_UNTAGGED_METHOD = '''from __future__ import annotations


class TestOne:
    def test_it(self):
        assert True
'''


def test_apply_upgrades_inserts_a_qualified_id_for_the_one_untagged_method(tmp_path):
    """The single-untagged-test case still auto-tags, and does so with the
    class-qualified test_id (external code review, P3.4 high)."""
    rel = "tests/test_one_class.py"
    (tmp_path / "tests").mkdir()
    (tmp_path / rel).write_text(_ONE_CLASS_ONE_UNTAGGED_METHOD, encoding="utf-8")
    report = {"candidates": [_candidate("FR-01.01", "AC01", [rel])]}
    result = apply_mod.apply_upgrades(tmp_path, report)
    assert result["tags_inserted_total"] == 1
    assert result["inserted_new_tags"][0]["test"] == f"{rel}::TestOne.test_it"
    text = (tmp_path / rel).read_text(encoding="utf-8")
    assert '@pytest.mark.covers("FR-01.01/AC01")' in text


_SINGLE_QUOTED_BARE_TAG = """from __future__ import annotations

import pytest


@pytest.mark.covers('FR-01.01')
def test_one():
    assert True
"""


def test_apply_upgrades_widens_a_single_quoted_bare_tag_to_valid_double_quoted_syntax(tmp_path):
    """Tier-3 CI-gate re-review (P3.4 high, disputed): the reviewer claimed
    ``_upgrade_bare_tags`` replaces only the opening quote of a single-quoted
    ``covers('FR-01.01')`` decorator, leaving the original closing quote
    behind and producing invalid Python (``covers("FR-01.01/AC01')``). The
    widen regex's backreference (``\\1``) actually matches the CLOSING quote
    too, so the whole quoted literal -- both delimiters -- is replaced in one
    span; this test proves the real output is valid, double-quoted syntax
    (``ast.parse`` on the rewritten file must not raise) rather than taking
    the claim on faith."""
    rel = "tests/test_single_quoted.py"
    (tmp_path / "tests").mkdir()
    (tmp_path / rel).write_text(_SINGLE_QUOTED_BARE_TAG, encoding="utf-8")
    report = {"candidates": [_candidate("FR-01.01", "AC01", [rel])]}
    result = apply_mod.apply_upgrades(tmp_path, report)
    assert result["tags_upgraded_total"] == 1
    text = (tmp_path / rel).read_text(encoding="utf-8")
    assert '@pytest.mark.covers("FR-01.01/AC01")' in text
    ast.parse(text)  # would raise SyntaxError if the quotes were mismatched


def _plant_reparse_point(path: Path, target: Path) -> None:
    """Create a real symlink (POSIX) or directory junction (Windows) at
    `path` pointing at `target`. Junctions need no elevated privilege on
    Windows, unlike symlinks (SeCreateSymbolicLinkPrivilege) -- this is what
    lets the reparse-point test below run unconditionally on every host
    instead of skipping (Tier-3 CI-gate re-review, P3.4 high, round 10 --
    same helper as ``test_review_scratch.py``'s own precedent)."""
    target.mkdir(exist_ok=True)
    if sys.platform == "win32":
        import subprocess  # nosec B404 - fixed argv, shell=False
        subprocess.run(  # nosec B603 B607 - fixed argv, shell=False
            ["cmd", "/c", "mklink", "/J", str(path), str(target)],
            capture_output=True, text=True, check=True, timeout=30,
        )
    else:
        path.symlink_to(target, target_is_directory=True)


def test_apply_upgrades_skips_a_candidate_file_that_is_really_a_symlink_escape(tmp_path):
    """Tier-3 CI-gate re-review (P3.4 high): a committed symlink (or, on
    Windows, an unprivileged directory junction -- ``IO_REPARSE_TAG_MOUNT_POINT``,
    which ``Path.is_file()`` also follows) somewhere in a test file's ANCESTOR
    chain would let ``--write`` follow it and modify a file OUTSIDE the
    repository. The real target directory here sits outside ``tmp_path`` (the
    project root) entirely; the fix must refuse the write and must never
    touch that external target."""
    outside_dir = tmp_path.parent / "outside_project_root_dir"
    outside_target = outside_dir / "test_escaping_link.py"
    _plant_reparse_point(tmp_path / "tests", outside_dir)
    outside_target.write_text(_ONE_CLASS_ONE_UNTAGGED_METHOD, encoding="utf-8")
    rel = "tests/test_escaping_link.py"

    report = {"candidates": [_candidate("FR-01.01", "AC01", [rel])]}
    result = apply_mod.apply_upgrades(tmp_path, report)

    assert result["tags_inserted_total"] == 0
    assert result["skipped"] == [{**_candidate("FR-01.01", "AC01", [rel]),
                                    "file": rel, "reason": "path_escapes_project_root"}]
    assert outside_target.read_text(encoding="utf-8") == _ONE_CLASS_ONE_UNTAGGED_METHOD
