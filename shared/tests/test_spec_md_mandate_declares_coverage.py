"""TC3.2 (trg-c0d83dce) — permanent regression guard.

Mirrors test_mandated_reader_index_first.py's pattern for the ONE remaining
"read completely" mandate that TC3.2a's index-first fix did not cover:
`.shipwright/planning/*/spec.md`, which has no ready-made index to dodge the
cap with. Without this, the wired-in coverage check could quietly regress
back to a bare "read completely" promise.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

_MANDATED_READERS = [
    "plugins/shipwright-iterate/skills/iterate/references/context-loading.md",
    "plugins/shipwright-project/skills/project/references/step-1-interview.md",
]


@pytest.mark.parametrize("relpath", _MANDATED_READERS)
def test_spec_md_mandate_references_the_coverage_check(relpath):
    text = (_REPO_ROOT / relpath).read_text(encoding="utf-8")
    assert "check_mandated_load_coverage.py" in text, (
        f"{relpath} does not reference check_mandated_load_coverage.py — "
        "TC3.2 requires the spec.md mandate to run the coverage check, not "
        "just promise a complete read"
    )


@pytest.mark.parametrize("relpath", _MANDATED_READERS)
def test_spec_md_mandate_no_longer_bare_read_completely(relpath):
    text = (_REPO_ROOT / relpath).read_text(encoding="utf-8")
    assert "spec.md — ALL spec files across all splits (read completely)" not in text
    assert "spec.md — existing specs across all splits (read completely)" not in text


@pytest.mark.parametrize("relpath", _MANDATED_READERS)
def test_spec_md_mandate_names_the_exceeds_cap_and_missing_file_shapes(relpath):
    """Both row shapes the check can emit (over-cap, missing file) must be
    named -- a coverage check that is run but whose output is never acted on
    is the same silent-truncation defect wearing a green checkmark."""
    text = (_REPO_ROOT / relpath).read_text(encoding="utf-8")
    assert "exceeds_cap" in text
    assert "exists: false" in text
