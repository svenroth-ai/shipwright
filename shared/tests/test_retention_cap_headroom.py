"""Regression test for the ITERATE_RETENTION headroom bump.

See ``.shipwright/planning/adr/`` (this run's ADR entry) and the 2026-08-15
ADR it amends: ``append_iterate_entry.py``'s per-branch, stale-view pruning
self-heals a bounded overshoot, but the bound was sized for roughly 2
concurrent iterate branches. Raising the cap buys headroom against the
current, much larger, working set without changing the pruning mechanism
itself. This test guards two things: the constant did not silently regress,
and its prose mirrors — the module docstring, the inline comment, F5c.md,
docs/hooks-and-pipeline.md, docs/guide.md (two locations there), and
verifiers/iterate_checks.py's operator-facing diagnostic — stay in sync
with it rather than drifting back to the old value.
"""

from __future__ import annotations

import re
from pathlib import Path

import tools.append_iterate_entry as tool

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

EXPECTED_RETENTION = 200


def test_retention_constant_is_raised():
    assert tool.ITERATE_RETENTION == EXPECTED_RETENTION


def test_module_docstring_states_current_cap():
    docstring = tool.__doc__ or ""
    assert "``ITERATE_RETENTION``" in docstring
    assert f"(~{EXPECTED_RETENTION}, not exactly" in docstring


def test_inline_comment_states_current_cap():
    source = Path(tool.__file__).read_text(encoding="utf-8")
    line = next(
        line for line in source.splitlines() if line.startswith("ITERATE_RETENTION =")
    )
    assert f"~{EXPECTED_RETENTION} unpinned entries" in line


def test_hooks_and_pipeline_doc_states_current_cap():
    doc = (REPO_ROOT / "docs" / "hooks-and-pipeline.md").read_text(encoding="utf-8")
    assert f"applies {EXPECTED_RETENTION}-entry retention" in doc, (
        "docs/hooks-and-pipeline.md's append_iterate_entry.py bullet must "
        f"state the current cap ({EXPECTED_RETENTION}), not a stale one"
    )
    assert "applies 50-entry retention" not in doc


def test_guide_doc_states_current_cap():
    doc = (REPO_ROOT / "docs" / "guide.md").read_text(encoding="utf-8")
    assert f"last {EXPECTED_RETENTION} entries retained" in doc, (
        "docs/guide.md's F5c step-9 prose must state the current cap "
        f"({EXPECTED_RETENTION}), not a stale one"
    )
    assert f"F5c, {EXPECTED_RETENTION}-entry retention" in doc, (
        "docs/guide.md's artifact table row for iterates/<run_id>.json must "
        f"state the current cap ({EXPECTED_RETENTION}), not a stale one"
    )
    assert "last 50 entries retained" not in doc
    assert "F5c, 50-entry retention" not in doc


def test_no_entry_detail_diagnostic_states_current_cap():
    from tools.verifiers.iterate_checks import _no_entry_detail

    detail = _no_entry_detail("iterate-2026-01-01-example")
    assert f"{EXPECTED_RETENTION}-entry retention window" in detail, (
        "iterate_checks.py's _no_entry_detail() operator-facing diagnostic "
        f"must state the current cap ({EXPECTED_RETENTION}), not a stale one"
    )
    assert "50-entry retention window" not in detail


def test_f5c_reference_states_current_cap():
    f5c = (
        REPO_ROOT
        / "plugins"
        / "shipwright-iterate"
        / "skills"
        / "iterate"
        / "references"
        / "F5c.md"
    ).read_text(encoding="utf-8")
    assert re.search(rf"\b{EXPECTED_RETENTION}\b", f5c), (
        "F5c.md's retention section must state the current ITERATE_RETENTION "
        f"value ({EXPECTED_RETENTION}), not a stale one"
    )
    assert "50-entry retention" not in f5c and "up to ~50 unpinned" not in f5c, (
        "F5c.md still states the old 50-entry cap alongside (or instead of) "
        "the current one"
    )
