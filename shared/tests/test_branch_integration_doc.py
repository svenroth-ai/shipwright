"""``docs/hooks-and-pipeline.md`` carries the merge-not-rebase convention.

iterate-2026-05-27-tracked-artifacts-single-producer-and-finalize-sandbox
SCOPE 3: rebase rewrites Run-ID trailer commit SHAs and breaks
``audit_staleness.find_snapshot_commit``. Operators self-discipline via
the documented convention; this test fails if the section disappears or
loses its canonical commands.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "docs" / "hooks-and-pipeline.md"


def test_branch_integration_section_present() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "## Branch integration" in text, (
        "expected 'Branch integration' top-level heading in "
        "docs/hooks-and-pipeline.md (iterate-2026-05-27 SCOPE 3)"
    )


def test_branch_integration_names_merge_and_rebase() -> None:
    text = DOC.read_text(encoding="utf-8")
    # Slice to the section so a stray "rebase" elsewhere doesn't satisfy
    # the test by accident.
    start = text.index("## Branch integration")
    # Next top-level heading or EOF.
    end_idx = text.find("\n## ", start + 1)
    section = text[start: end_idx if end_idx > 0 else len(text)]

    assert "git merge main" in section, "merge guidance missing"
    assert "git rebase main" in section, "rebase warning missing"
    assert "Run-ID" in section, "Run-ID trailer rationale missing"
    assert "audit_staleness" in section, (
        "explanation must reference audit_staleness consumer "
        "(why the convention matters)"
    )


def test_branch_integration_warns_against_force_push() -> None:
    text = DOC.read_text(encoding="utf-8")
    start = text.index("## Branch integration")
    end_idx = text.find("\n## ", start + 1)
    section = text[start: end_idx if end_idx > 0 else len(text)]

    # Operational guidance must call out the destructive recovery path.
    assert "reflog" in section, (
        "section should mention git reflog as the recovery path after "
        "an accidental rebase + force-push"
    )
