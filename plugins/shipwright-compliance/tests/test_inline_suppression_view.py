"""Dashboard rendering for inline `# nosemgrep` suppressions.

The three states this section must keep distinct — reader/baseline broken, zero
suppressions, suppressions present — are each pinned here. Collapsing them is
how an unreadable file comes to read as a clean one (external review, GPT #6).

Fixtures build their suppression text through an f-string placeholder so this
file's own source is never counted as a suppression site by the live repo
guard in `shared/tests/test_inline_suppressions_repo_guard.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.lib.inline_suppression_view import inline_suppression_lines

_RULE = "python.lang.security.audit.non-literal-import.non-literal-import"
_REF = "iterate-2026-08-05-inline-suppression-ratchet"
_STATEMENT = "First-party module identifiers only, never untrusted input."


def _repo(tmp_path: Path, *, sources: dict, baseline=...) -> Path:
    for rel, text in sources.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    if baseline is not ...:
        (tmp_path / "shipwright_inline_suppressions.json").write_text(
            baseline if isinstance(baseline, str) else json.dumps(baseline),
            encoding="utf-8")
    return tmp_path


def _baseline(rule: str, count: int) -> dict:
    return {
        "schema": 1,
        "rules": [{
            "rule": rule, "max_sites": count,
            "rationale_ref": _REF, "statement": _STATEMENT,
        }],
    }


def test_a_clean_tree_says_none_rather_than_rendering_nothing(tmp_path):
    """An empty section is indistinguishable from a section that failed to
    render; an explicit 'none' is a claim."""
    body = "\n".join(inline_suppression_lines(_repo(tmp_path, sources={
        "a.py": "x = 1\n"})))
    assert "No inline suppressions" in body


def test_present_suppressions_render_with_their_count_and_reference(tmp_path):
    root = _repo(
        tmp_path,
        sources={"a.py": f"# nosemgrep: {_RULE}\n"},
        baseline=_baseline(_RULE, 1),
    )
    body = "\n".join(inline_suppression_lines(root))
    assert _RULE in body and _REF in body
    assert "| 1 |" in body


def test_a_suppression_with_no_baseline_entry_renders_as_drift(tmp_path):
    """Being suppressed is not the same as being governed. Rendering an
    unrecorded site as though it were recorded would launder it."""
    root = _repo(tmp_path, sources={"a.py": f"# nosemgrep: {_RULE}\n"})
    body = "\n".join(inline_suppression_lines(root))
    assert "❌ none" in body


def test_a_count_over_its_baseline_is_flagged_in_the_table(tmp_path):
    root = _repo(
        tmp_path,
        sources={"a.py": f"# nosemgrep: {_RULE}\n# nosemgrep: {_RULE}\n"},
        baseline=_baseline(_RULE, 1),
    )
    assert "exceeded" in "\n".join(inline_suppression_lines(root))


def test_an_invalid_baseline_warns_instead_of_rendering_a_reassuring_zero(
    tmp_path,
):
    root = _repo(tmp_path, sources={"a.py": "x = 1\n"}, baseline="{not json")
    body = "\n".join(inline_suppression_lines(root))
    assert "⚠️" in body and "INVALID" in body
    assert "No inline suppressions" not in body


def test_an_unreachable_shared_reader_warns_and_counts_nothing(
    tmp_path, monkeypatch
):
    import scripts.lib.inline_suppression_view as view

    monkeypatch.setattr(view, "_load_shared", lambda: None)
    body = "\n".join(view.inline_suppression_lines(tmp_path))
    assert "⚠️" in body and "not** counted" in body


def test_a_non_git_tree_discloses_the_broader_file_set(tmp_path):
    """`tmp_path` is not a git repo, so discovery falls back to a walk — the
    section must say so rather than present it as the precise measurement."""
    root = _repo(tmp_path, sources={"a.py": "x = 1\n"})
    assert "not a git tree" in "\n".join(
        inline_suppression_lines(root)).lower()


def test_the_section_states_that_it_is_visibility_not_per_site_review(tmp_path):
    """A reader must not mistake a count for the register's per-site,
    dated, owned acceptance — the whole reason the entry type was declined."""
    body = "\n".join(inline_suppression_lines(_repo(tmp_path, sources={
        "a.py": "x = 1\n"})))
    assert "not** tracked in the accepted-risk register" in body
    assert "no site here carries an owner or a re-review date" in body


def test_the_rendered_block_cites_no_shipwright_internal_run_id(tmp_path):
    """This artifact renders into ADOPTER projects, where an `iterate-…` slug
    resolves to nothing. The reasoning belongs in the artifact; the citation
    belongs in the framework's own source (Stage-2 code review)."""
    body = "\n".join(inline_suppression_lines(_repo(tmp_path, sources={
        "a.py": "x = 1\n"})))
    assert "iterate-2026-" not in body
