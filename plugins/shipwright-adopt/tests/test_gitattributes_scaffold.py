"""Tests for the gitattributes-union scaffolder used by /shipwright-adopt (AC-2).

The scaffolder lands a root ``.gitattributes`` declaring ``merge=union`` for the
tracked append-log artifacts (``shipwright_events.jsonl``,
``.shipwright/triage.jsonl``) so concurrent iterate appends auto-line-union
instead of producing conflict markers — the protection that kept the monorepo
merge-theater-free but never reached managed repos (WebUI #96-#100 hand-resolved
exactly these files).

Unlike the gitleaks scaffolder (whole-file, never-overwrite), this one **merges**:
a target repo often already has a hand-rolled ``.gitattributes`` (EOL rules, LFS,
linguist overrides), so the scaffolder appends only the missing union lines and
preserves every existing user entry bit-for-bit (idempotent).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.gitattributes_scaffolder import scaffold_gitattributes

UNION_EVENTS = "shipwright_events.jsonl merge=union"
UNION_TRIAGE = ".shipwright/triage.jsonl merge=union"


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    return tmp_path


def test_scaffolds_when_absent(tmp_project: Path) -> None:
    result = scaffold_gitattributes(tmp_project)

    assert result["wrote"] is True
    assert result["reason"] == "scaffolded"
    ga = tmp_project / ".gitattributes"
    assert ga.exists()
    assert result["path"] == str(ga)
    text = ga.read_text(encoding="utf-8")
    assert UNION_EVENTS in text and UNION_TRIAGE in text


def test_merges_into_existing_preserving_user_entries(tmp_project: Path) -> None:
    ga = tmp_project / ".gitattributes"
    user = "*.png binary\n*.md text eol=lf\n"
    ga.write_text(user, encoding="utf-8")

    result = scaffold_gitattributes(tmp_project)

    assert result["wrote"] is True
    assert result["reason"] == "merged"
    text = ga.read_text(encoding="utf-8")
    # user entries preserved verbatim …
    assert "*.png binary" in text and "*.md text eol=lf" in text
    # … and the union lines appended.
    assert UNION_EVENTS in text and UNION_TRIAGE in text


def test_already_present_is_noop(tmp_project: Path) -> None:
    ga = tmp_project / ".gitattributes"
    # "already present" means EVERY fragment line — the JSONL logs AND the curated
    # agent-docs (iterate-2026-06-12-union-curated-agent-docs); a file with only
    # the JSONL pair is now incomplete and would be merged, not a no-op.
    pre = (
        f"*.png binary\n{UNION_EVENTS}\n{UNION_TRIAGE}\n"
        ".shipwright/agent_docs/architecture.md merge=union\n"
        ".shipwright/agent_docs/conventions.md merge=union\n"
    )
    ga.write_text(pre, encoding="utf-8")

    result = scaffold_gitattributes(tmp_project)

    assert result["wrote"] is False
    assert result["reason"] == "already_present"
    assert ga.read_text(encoding="utf-8") == pre  # untouched


def test_completes_a_partial_existing_union(tmp_project: Path) -> None:
    ga = tmp_project / ".gitattributes"
    ga.write_text(f"{UNION_EVENTS}\n", encoding="utf-8")  # only one of two

    result = scaffold_gitattributes(tmp_project)

    assert result["wrote"] is True
    assert result["reason"] == "merged"
    text = ga.read_text(encoding="utf-8")
    assert UNION_TRIAGE in text
    assert text.count(UNION_EVENTS) == 1  # the present line is not duplicated


def test_idempotent_when_called_twice(tmp_project: Path) -> None:
    first = scaffold_gitattributes(tmp_project)
    second = scaffold_gitattributes(tmp_project)

    assert first["wrote"] is True and first["reason"] == "scaffolded"
    assert second["wrote"] is False and second["reason"] == "already_present"
    text = (tmp_project / ".gitattributes").read_text(encoding="utf-8")
    assert UNION_EVENTS in text and UNION_TRIAGE in text
