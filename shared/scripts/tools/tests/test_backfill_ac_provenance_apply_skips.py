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
