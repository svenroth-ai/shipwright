"""Tests for shared/scripts/tools/context_md_format.py — the continuation-
line absorption fix (doubt-reviewer D3), the public ``read_terms()`` API
(doubt-reviewer D4), and the duplicate-term scan's scope fix (P4.1 final
review — the scan must not treat a legitimate bold cross-reference in
Relationships/Flagged ambiguities as a hidden duplicate).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.context_md_format import Term, parse_language_entries, read_terms, split_lines_strict
from tools.write_context_term import upsert_term


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# shared/context-format.md §2's own worked example, VERBATIM (bold
# cross-references included) — a paraphrase without the bold markup would
# silently avoid exercising the duplicate-term scan's scope (P4.1 final
# review: upserting "Customer" against a paraphrased copy used to pass even
# though it failed against the real doc).
# ---------------------------------------------------------------------------

_CONTEXT_FORMAT_MD_EXAMPLE = (
    "# CONTEXT.md — Acme domain glossary\n\n"
    "Acme is an order-management tool.\n\n"
    "## Language\n\n"
    "**Order** — a customer's confirmed purchase of one or more items.\n"
    '_Avoid_ "cart" for a confirmed order — a cart is unconfirmed.\n\n'
    "**Cancellation** — voiding an Order before it ships. Partial cancellation\n"
    "(some line items) is distinct from full cancellation.\n\n"
    "## Relationships\n\n"
    "- A Customer has many Orders; an Order belongs to exactly one Customer.\n"
    "- An Order has many line items; a Cancellation targets one or more line items.\n\n"
    "## Flagged ambiguities\n\n"
    '- "account" was used for both Customer and User — resolved 2026-07-23 to mean\n'
    "  the paying **Customer**; the logged-in identity is a **User**.\n"
)


def test_continuation_line_is_absorbed_into_the_definition_not_orphaned(tmp_path):
    """context-format.md §2's own Cancellation example must round-trip
    without corrupting the wrapped continuation line into an orphaned raw
    block or injecting a blank line mid-definition (doubt-reviewer D3)."""
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text(_CONTEXT_FORMAT_MD_EXAMPLE, encoding="utf-8")

    result = upsert_term(ctx, term="Refund", definition="returning money for a cancelled order.")
    assert result["status"] == "appended"

    content = read(ctx)
    assert content.count("**Cancellation**") == 1
    assert (
        "voiding an Order before it ships. Partial cancellation "
        "(some line items) is distinct from full cancellation."
    ) in content
    # No orphaned raw block: the continuation text must not be reflowed
    # into its own paragraph, separated from "**Cancellation**" by a blank
    # line.
    assert "\n\n(some line items)" not in content


def test_upserting_the_already_wrapped_cancellation_term_is_then_idempotent(tmp_path):
    """Once the tool has touched the file once (reflowing the wrap onto one
    line), re-running with the same joined definition is byte-identical."""
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text(_CONTEXT_FORMAT_MD_EXAMPLE, encoding="utf-8")
    upsert_term(ctx, term="Refund", definition="returning money for a cancelled order.")
    before = read(ctx)
    result = upsert_term(ctx, term="Refund", definition="returning money for a cancelled order.")
    assert result["status"] == "unchanged"
    assert read(ctx) == before


def test_preserves_relationships_and_flagged_ambiguities_content(tmp_path):
    """A term written to Language must not disturb the bold cross-references
    already living in Relationships/Flagged ambiguities."""
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text(_CONTEXT_FORMAT_MD_EXAMPLE, encoding="utf-8")
    upsert_term(ctx, term="Refund", definition="returning money for a cancelled order.")
    content = read(ctx)
    assert "- A Customer has many Orders; an Order belongs to exactly one Customer." in content
    assert "the paying **Customer**; the logged-in identity is a **User**." in content


def test_upsert_new_term_whose_name_is_bold_in_flagged_ambiguities_succeeds(tmp_path):
    """context-format.md §2's own worked example bolds "Customer" as a
    cross-reference inside Flagged ambiguities ("the paying **Customer**").
    Upserting a NEW "Customer" Language entry against that canonical
    example must succeed — the duplicate-term scan must not treat a
    legitimate cross-reference elsewhere in the document as a hidden
    duplicate (regression for the scoping bug, P4.1 final review)."""
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text(_CONTEXT_FORMAT_MD_EXAMPLE, encoding="utf-8")

    result = upsert_term(ctx, term="Customer", definition="the paying party on an Order.")
    assert result["status"] == "appended"

    content = read(ctx)
    assert "**Customer** — the paying party on an Order." in content
    # The Flagged-ambiguities cross-reference is untouched.
    assert "the paying **Customer**; the logged-in identity is a **User**." in content


def test_parse_language_entries_joins_a_continuation_line():
    body = [
        "**Cancellation** — voiding an Order before it ships. Partial cancellation",
        "(some line items) is distinct from full cancellation.",
    ]
    entries = parse_language_entries(body)
    assert len(entries) == 1
    assert entries[0]["term"] == "Cancellation"
    assert entries[0]["definition"] == (
        "voiding an Order before it ships. Partial cancellation "
        "(some line items) is distinct from full cancellation."
    )
    assert entries[0]["avoid"] is None


def test_parse_language_entries_continuation_stops_at_an_avoid_line():
    body = [
        "**Order** — a confirmed purchase.",
        '_Avoid_ "cart" for a confirmed order.',
    ]
    entries = parse_language_entries(body)
    assert len(entries) == 1
    assert entries[0]["definition"] == "a confirmed purchase."
    assert entries[0]["avoid"] == '"cart" for a confirmed order.'


def test_parse_language_entries_continuation_stops_at_a_new_term_line():
    body = [
        "**Order** — a confirmed purchase.",
        "**Cancellation** — voiding an order.",
    ]
    entries = parse_language_entries(body)
    assert len(entries) == 2
    assert entries[0]["term"] == "Order"
    assert entries[1]["term"] == "Cancellation"


# ---------------------------------------------------------------------------
# read_terms() — the sanctioned public read API (D4)
# ---------------------------------------------------------------------------

def test_read_terms_missing_file_returns_empty_list(tmp_path):
    assert read_terms(tmp_path / "CONTEXT.md") == []


def test_read_terms_no_language_section_returns_empty_list(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text("# CONTEXT.md — Acme domain glossary\n\nAcme.\n", encoding="utf-8")
    assert read_terms(ctx) == []


def test_read_terms_returns_every_sharpened_term(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    upsert_term(ctx, term="Order", definition="a confirmed purchase.", avoid="cart.")
    upsert_term(ctx, term="Cancellation", definition="voiding an order.")
    terms = read_terms(ctx)
    assert terms == [
        Term(term="Order", definition="a confirmed purchase.", avoid="cart."),
        Term(term="Cancellation", definition="voiding an order.", avoid=None),
    ]


def test_read_terms_matching_is_exact_case_no_folding(tmp_path):
    """Contract: two terms differing only in case are two different terms,
    never merged or folded together (doubt-reviewer D4)."""
    ctx = tmp_path / "CONTEXT.md"
    upsert_term(ctx, term="Order", definition="v1")
    upsert_term(ctx, term="order", definition="v2")
    terms = {t.term: t.definition for t in read_terms(ctx)}
    assert terms == {"Order": "v1", "order": "v2"}


def test_read_terms_propagates_duplicate_heading_value_error(tmp_path):
    """Failure contract (P4.1 final review): a malformed hand-edit is not
    swallowed into an empty/partial result."""
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text(
        "# CONTEXT.md — Acme domain glossary\n\nAcme.\n\n"
        "## Language\n\n**Order** — a confirmed purchase.\n\n"
        "## Language\n\n**Cancellation** — voiding an order.\n\n"
        "## Relationships\n\n## Flagged ambiguities\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        read_terms(ctx)


def test_read_terms_propagates_non_utf8_decode_error(tmp_path):
    """Failure contract (P4.1 final review): non-UTF-8 content raises rather
    than being silently treated as an empty glossary."""
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_bytes(b"# CONTEXT.md \xff\xfe not valid utf-8")
    with pytest.raises(UnicodeDecodeError):
        read_terms(ctx)


# ---------------------------------------------------------------------------
# split_lines_strict() — CRLF/CR/LF only, never the wider Unicode
# line-separator set str.splitlines() also breaks on (P4.1 final-review
# PR-gate, comment finding).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("eol", ["\n", "\r\n", "\r"])
def test_split_lines_strict_matches_splitlines_for_normal_content(eol):
    content = f"a{eol}b{eol}{eol}c"
    assert split_lines_strict(content) == content.splitlines()


def test_split_lines_strict_matches_splitlines_with_trailing_terminator():
    content = "a\nb\n"
    assert split_lines_strict(content) == content.splitlines() == ["a", "b"]


def test_split_lines_strict_empty_content_returns_empty_list():
    assert split_lines_strict("") == []


# Code points, not literal characters, so the source file never embeds a
# raw NEL/LS/PS byte (a typed exotic-Unicode character can silently get
# mangled by an editing tool's own encoding path -- safer to build these
# at runtime via chr()).
_NEL, _LS, _PS, _VT, _FF = (chr(0x85), chr(0x2028), chr(0x2029), chr(0x0B), chr(0x0C))


@pytest.mark.parametrize(
    "exotic", [_NEL, _LS, _PS, _VT, _FF], ids=["NEL", "LS", "PS", "VT", "FF"],
)
def test_split_lines_strict_preserves_exotic_unicode_separators(exotic):
    """A NEL/LS/PS/VT/FF character embedded in hand-authored prose is not a
    line boundary for this module's CRLF/CR/LF-only round-trip — unlike
    ``str.splitlines()``, which WOULD split here."""
    content = f"a{exotic}b" + "\n" + "c"
    assert split_lines_strict(content) == [f"a{exotic}b", "c"]
    # Prove this is a real behavioral difference from str.splitlines(),
    # not a redundant assertion.
    assert content.splitlines() != split_lines_strict(content)


def test_upsert_term_preserves_exotic_unicode_separator_in_an_untouched_entry(tmp_path):
    """An end-to-end proof against a hand-authored file (never run through
    ``sanitize_field``, which itself collapses any Unicode-whitespace
    character — NEL/LS/PS included — for NEWLY WRITTEN text): an EXISTING,
    untouched entry whose definition contains a PS character (U+2029) must
    round-trip byte-identical rather than being cut into an orphaned raw
    block by a splitlines()-based parse while a DIFFERENT term is upserted."""
    ctx = tmp_path / "CONTEXT.md"
    existing_definition = "a purchase" + _PS + "with an odd separator inside it."
    ctx.write_text(
        "# CONTEXT.md — Acme domain glossary\n\nAcme.\n\n"
        "## Language\n\n"
        f"**Order** — {existing_definition}\n\n"
        "## Relationships\n\n## Flagged ambiguities\n",
        encoding="utf-8",
    )

    result = upsert_term(ctx, term="Cancellation", definition="voiding an Order before it ships.")
    assert result["status"] == "appended"

    content = read(ctx)
    assert f"**Order** — {existing_definition}" in content
    assert "**Cancellation** — voiding an Order before it ships." in content
