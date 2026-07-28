"""The documents describing the triage decisions match the commands.

iterate-2026-07-27-triage-defer-review-followup. Split out of
`test_triage_defer.py`: it is the only test in that file that reads real
repository files, so a docs-only edit turned a *behaviour* test red inside
`shared/tests` — and the previous run's self-review claimed no test there
touched repo state, which this one always did.
"""

from __future__ import annotations

from pathlib import Path

_WORKTREE = Path(__file__).resolve().parents[2]


#: A spot-check, NOT a closure: an unlisted phrasing ("removed in v0.5",
#: "no-op", "deprecated") passes. Claimed as such — the point is to catch the
#: obvious regression where a document keeps the command while denying it.
_NEGATIONS = ("not implemented", "not available", "not yet", "planned",
              "todo", "unavailable", "coming soon", "deprecated", "removed",
              "no-op", "no longer")


def _command_line(text: str, doc: str) -> str:
    """The one line that documents the command — a bounded slice, so a
    negation cannot hide just outside an arbitrary character window."""
    lines = [ln for ln in text.splitlines() if "triage_cli.py defer" in ln]
    assert lines, f"{doc}: documents no `triage_cli.py defer` command"
    return " ".join(lines).lower()


def test_the_documents_describe_the_defer_subcommand() -> None:
    """The three documents that used to say the terminal had no third decision.

    Scoped to the LINES that carry the command, and spot-checked against a
    named negation set. Two earlier forms were weaker AND overclaimed: one
    asserted merely that a substring appeared somewhere in the file; the next
    searched one English phrase inside an arbitrary 200-character window. This
    one is honest about its limit — a denylist cannot prove a document is
    truthful, only catch the obvious lie.

    This is also the only test in `shared/tests` for this feature that reads
    real repository files — kept here, out of the behaviour suite, so a
    docs-only edit cannot turn a behaviour test red.
    """
    glossary = (_WORKTREE / "shared" / "glossary.md").read_text(encoding="utf-8")
    assert "`triage_cli.py` has none" not in glossary
    line = _command_line(glossary, "glossary.md")
    assert "--reason" in line, line

    for doc in ("guide.md", "security-ci-setup.md"):
        text = (_WORKTREE / "docs" / doc).read_text(encoding="utf-8")
        line = _command_line(text, doc)
        assert "--reason" in line, line
        assert not any(n in line for n in _NEGATIONS), line
