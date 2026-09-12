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


def test_wrapped_avoid_line_cross_referencing_another_term_is_not_flagged(tmp_path):
    """A hand-authored ``_Avoid_`` line that word-wraps onto a second
    physical line, where that second line happens to START with a bolded
    cross-reference to another term, used to orphan the wrapped remainder
    into its own unparsed raw block (only a term's *definition* absorbed a
    continuation line; its ``_Avoid_`` text did not). ``term_markup_count``
    then counted that orphaned line-start ``**Cart**`` as a real duplicate
    occurrence, and a fresh entry for "Cart" always added a second, so
    upserting "Cart" was permanently rejected — with no hand-edit recovery
    path available mid-interview (P4.1 final review, deferred finding).
    The ``_Avoid_`` text must absorb its own wrapped continuation line the
    same way a definition already does, so the reference never lands at a
    line start in the first place."""
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text(
        "# CONTEXT.md — Acme domain glossary\n\nAcme.\n\n"
        "## Language\n\n"
        "**Order** — a customer's confirmed purchase.\n"
        "_Avoid_ using this term for anything resembling a\n"
        "**Cart** that has not been confirmed yet.\n\n"
        "## Relationships\n\n## Flagged ambiguities\n",
        encoding="utf-8",
    )

    result = upsert_term(ctx, term="Cart", definition="an unconfirmed collection of items.")

    assert result["status"] == "appended"
    content = read(ctx)
    assert (
        "_Avoid_ using this term for anything resembling a **Cart** "
        "that has not been confirmed yet." in content
    )
    assert "**Cart** — an unconfirmed collection of items." in content


def test_unrelated_raw_line_after_avoid_is_not_swallowed_into_it(tmp_path):
    """Continuation absorption after an ``_Avoid_`` line only swallows a
    DIRECTLY adjacent non-blank line (doubt-reviewer, P4.1 final-review
    Stage-3 follow-up on the wrapped-avoid fix above). A hand-written note
    that is genuinely unrelated — separated from the avoid line by a blank
    line, the same convention every other hand-written block in this file
    already relies on — must survive as its own untouched raw block, not
    get silently merged into the avoid text of the entry above it."""
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text(
        "# CONTEXT.md — Acme domain glossary\n\nAcme.\n\n"
        "## Language\n\n"
        "**Order** — a confirmed purchase.\n"
        "_Avoid_ mixing this up with a Cart.\n\n"
        "Unrelated hand-written note about refund policy — not a continuation.\n\n"
        "## Relationships\n\n## Flagged ambiguities\n",
        encoding="utf-8",
    )

    result = upsert_term(ctx, term="Refund", definition="reversal of a confirmed Order.")

    assert result["status"] == "appended"
    content = read(ctx)
    assert "_Avoid_ mixing this up with a Cart." in content
    assert "mixing this up with a Cart. Unrelated" not in content
    assert "Unrelated hand-written note about refund policy — not a continuation." in content
    assert "**Refund** — reversal of a confirmed Order." in content


def test_legitimate_bold_cross_reference_in_another_entry_is_not_flagged(tmp_path):
    """A term legitimately reappears bold as a cross-reference inside
    ANOTHER entry's definition prose (``context-format.md``'s own worked
    example: "the paying **Customer**"). Upserting the referenced term
    ("Customer") for the first time must not be rejected as a hidden
    duplicate merely because the substring '**Customer**' now appears
    twice in the rendered Language section — once mid-sentence inside
    Order's definition, once as Customer's own freshly-serialized entry
    heading. Only a '**Customer**' occurring at the START of a line (an
    actual entry heading) counts toward the hidden-duplicate check."""
    ctx = tmp_path / "CONTEXT.md"
    upsert_term(ctx, term="Order", definition="a purchase made by a **Customer**.")

    result = upsert_term(ctx, term="Customer", definition="the paying party on an Order.")

    assert result["status"] == "appended"
    content = read(ctx)
    assert "**Order** — a purchase made by a **Customer**." in content
    assert "**Customer** — the paying party on an Order." in content
