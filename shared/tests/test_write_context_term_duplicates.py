"""Hidden-duplicate-term rejection tests for write_context_term.py's
``upsert_term`` (doubt-reviewer D2, P4.1 Stage-3 review).

"Re-sharpening never creates a second entry" only held for entries the
parser actually recognized. Three hand-authored shapes hide an existing
term from re-detection while leaving its markup intact in the file — a
missing blank line before it, a heading-less file, and a non-em-dash
separator — and each used to produce a silent duplicate on the next
sharpen. All three must now be rejected loudly instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.write_context_term import upsert_term


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_hidden_duplicate_via_missing_blank_line_is_rejected(tmp_path):
    """A prose line with no blank line before an entry swallows the entry
    into the same raw block, hiding it from _TERM_RE re-detection."""
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text(
        "# CONTEXT.md — Acme domain glossary\n\nAcme.\n\n"
        "## Language\n\n"
        "Some prose line without a blank separator\n"
        "**Order** — a confirmed purchase.\n\n"
        "## Relationships\n\n## Flagged ambiguities\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="hidden duplicate"):
        upsert_term(ctx, term="Order", definition="a newer definition.")


def test_hidden_duplicate_in_headingless_file_is_rejected(tmp_path):
    """A file with no '## ' heading at all stashes any existing entries in
    the header, invisible to matching."""
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text(
        "# CONTEXT.md — Acme domain glossary\n\n"
        "**Order** — a confirmed purchase.\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="hidden duplicate"):
        upsert_term(ctx, term="Order", definition="a newer definition.")


def test_hidden_duplicate_via_non_em_dash_separator_is_rejected(tmp_path):
    """A hyphen instead of the required em dash makes an entry look like a
    term but parse as unrecognized prose."""
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text(
        "# CONTEXT.md — Acme domain glossary\n\nAcme.\n\n"
        "## Language\n\n"
        "**Order** - a confirmed purchase.\n\n"
        "## Relationships\n\n## Flagged ambiguities\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="hidden duplicate"):
        upsert_term(ctx, term="Order", definition="a newer definition.")


def test_normal_resharpen_of_a_well_formed_entry_is_not_flagged(tmp_path):
    """A properly-formatted existing entry is matched and updated in place —
    the duplicate check must not false-positive on the normal path."""
    ctx = tmp_path / "CONTEXT.md"
    upsert_term(ctx, term="Order", definition="v1")
    result = upsert_term(ctx, term="Order", definition="v2")
    assert result["status"] == "updated"
    assert read(ctx).count("**Order**") == 1
