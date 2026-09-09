"""Tests for shared/scripts/tools/context_md_format.py — the continuation-
line absorption fix (doubt-reviewer D3) and the public ``read_terms()`` API
(doubt-reviewer D4), both from the P4.1 Stage-3 review round.
"""

from __future__ import annotations

from pathlib import Path

from tools.context_md_format import Term, parse_language_entries, read_terms
from tools.write_context_term import upsert_term


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Continuation-line absorption (D3) — shared/context-format.md §2's own
# worked Cancellation example wraps across two lines with no blank
# separator and no _Avoid_ line.
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
    "- A Customer has many Orders; an Order belongs to exactly one Customer.\n\n"
    "## Flagged ambiguities\n\n"
    '- "account" resolved to mean Customer.\n'
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
