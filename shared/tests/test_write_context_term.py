"""Unit tests for shared/scripts/tools/write_context_term.py's ``upsert_term``.

CLI/subprocess ("wired path") tests live in the sibling
``test_write_context_term_cli.py`` — split to keep both files under the
300-LOC bloat-baseline guideline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.write_context_term import upsert_term


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# find_context_file() was inlined into main() (code review, P4.1); its
# --project-root -> CONTEXT.md resolution is now covered end-to-end by
# test_write_context_term_cli.py::test_wired_cli_sharpens_a_term_into_context_md.


# ---------------------------------------------------------------------------
# upsert_term — creation
# ---------------------------------------------------------------------------

def test_creates_context_md_when_missing(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    result = upsert_term(
        ctx,
        term="Order",
        definition="a customer's confirmed purchase of one or more items.",
        project_name="Acme",
        summary="Acme is an order-management tool.",
    )
    assert result["status"] == "created"
    content = read(ctx)
    assert content.startswith("# CONTEXT.md — Acme domain glossary\n")
    assert "Acme is an order-management tool." in content
    assert "## Language" in content
    assert "## Relationships" in content
    assert "## Flagged ambiguities" in content
    assert "**Order** — a customer's confirmed purchase of one or more items." in content


def test_created_file_has_no_avoid_line_when_not_given(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    upsert_term(ctx, term="Order", definition="a confirmed purchase.")
    assert "_Avoid_" not in read(ctx)


def test_avoid_line_written_when_given(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    upsert_term(
        ctx,
        term="Order",
        definition="a confirmed purchase.",
        avoid='"cart" for a confirmed order — a cart is unconfirmed.',
    )
    content = read(ctx)
    assert '_Avoid_ "cart" for a confirmed order — a cart is unconfirmed.' in content
    assert content.index("_Avoid_") > content.index("**Order**")


def test_default_project_name_derived_from_dir(tmp_path):
    proj = tmp_path / "my-app"
    proj.mkdir()
    ctx = proj / "CONTEXT.md"
    upsert_term(ctx, term="Order", definition="x")
    assert "# CONTEXT.md — my-app domain glossary" in read(ctx)


# ---------------------------------------------------------------------------
# upsert_term — append a second term (AC4: no corruption/duplication)
# ---------------------------------------------------------------------------

def test_second_term_is_appended_not_duplicated(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    upsert_term(ctx, term="Order", definition="a confirmed purchase.")
    upsert_term(ctx, term="Cancellation", definition="voiding an Order before it ships.")
    content = read(ctx)
    assert content.count("**Order**") == 1
    assert content.count("**Cancellation**") == 1
    # Order preserved: first term still precedes the second.
    assert content.index("**Order**") < content.index("**Cancellation**")


def test_third_term_does_not_corrupt_first_two(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    upsert_term(ctx, term="Order", definition="a confirmed purchase.")
    upsert_term(ctx, term="Cancellation", definition="voiding an Order before it ships.")
    upsert_term(ctx, term="Customer", definition="the paying party on an Order.")
    content = read(ctx)
    for term in ("Order", "Cancellation", "Customer"):
        assert content.count(f"**{term}**") == 1


# ---------------------------------------------------------------------------
# upsert_term — update in place
# ---------------------------------------------------------------------------

def test_re_sharpening_a_term_updates_in_place(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    upsert_term(ctx, term="Order", definition="an old, imprecise definition.")
    result = upsert_term(ctx, term="Order", definition="a customer's confirmed purchase.")
    assert result["status"] == "updated"
    content = read(ctx)
    assert content.count("**Order**") == 1
    assert "a customer's confirmed purchase." in content
    assert "an old, imprecise definition." not in content


def test_update_preserves_other_terms(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    upsert_term(ctx, term="Order", definition="v1")
    upsert_term(ctx, term="Cancellation", definition="v1")
    upsert_term(ctx, term="Order", definition="v2")
    content = read(ctx)
    assert "**Cancellation** — v1" in content
    assert "**Order** — v2" in content
    assert "**Order** — v1" not in content


# avoid-preservation / --clear-avoid tests live in the sibling
# test_write_context_term_avoid.py.

# ---------------------------------------------------------------------------
# upsert_term — idempotency (AC1)
# ---------------------------------------------------------------------------

def test_rerun_with_unchanged_term_is_byte_identical(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    upsert_term(ctx, term="Order", definition="a confirmed purchase.", avoid="cart.")
    before = read(ctx)
    result = upsert_term(ctx, term="Order", definition="a confirmed purchase.", avoid="cart.")
    after = read(ctx)
    assert result["status"] == "unchanged"
    assert before == after


def test_rerun_with_two_unchanged_terms_is_byte_identical(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    upsert_term(ctx, term="Order", definition="a confirmed purchase.")
    upsert_term(ctx, term="Cancellation", definition="voiding an order.")
    before = read(ctx)
    upsert_term(ctx, term="Order", definition="a confirmed purchase.")
    upsert_term(ctx, term="Cancellation", definition="voiding an order.")
    after = read(ctx)
    assert before == after


# ---------------------------------------------------------------------------
# upsert_term — preserves hand-written content
# ---------------------------------------------------------------------------

def test_preserves_relationships_and_flagged_ambiguities_content(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text(
        "# CONTEXT.md — Acme domain glossary\n\n"
        "Acme is an order-management tool.\n\n"
        "## Language\n\n"
        "**Order** — a confirmed purchase.\n\n"
        "## Relationships\n\n"
        "- A Customer has many Orders.\n\n"
        "## Flagged ambiguities\n\n"
        '- "account" resolved to mean Customer.\n',
        encoding="utf-8",
    )
    upsert_term(ctx, term="Cancellation", definition="voiding an Order before it ships.")
    content = read(ctx)
    assert "- A Customer has many Orders." in content
    assert '- "account" resolved to mean Customer.' in content
    assert "**Cancellation**" in content


def test_preserves_hand_written_prose_in_language_section(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text(
        "# CONTEXT.md — Acme domain glossary\n\n"
        "Acme is an order-management tool.\n\n"
        "## Language\n\n"
        "Some hand-written note that isn't a **Term** — definition line.\n\n"
        "## Relationships\n\n## Flagged ambiguities\n",
        encoding="utf-8",
    )
    upsert_term(ctx, term="Order", definition="a confirmed purchase.")
    content = read(ctx)
    assert "Some hand-written note that isn't a **Term** — definition line." in content
    assert "**Order** — a confirmed purchase." in content


def test_hand_written_entry_position_untouched_by_a_new_term(tmp_path):
    """A hand-written entry keeps its position — a new tool-written term is
    appended after it, never reordered in front of it."""
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text(
        "# CONTEXT.md — Acme domain glossary\n\nAcme.\n\n"
        "## Language\n\n"
        "A hand-written note, not a **Term** — line.\n\n"
        "## Relationships\n\n## Flagged ambiguities\n",
        encoding="utf-8",
    )
    upsert_term(ctx, term="Order", definition="a confirmed purchase.")
    content = read(ctx)
    assert content.index("A hand-written note") < content.index("**Order**")


# ---------------------------------------------------------------------------
# External plan review findings (P4.1) — sanitization + validation
# ---------------------------------------------------------------------------

def test_embedded_newline_in_definition_is_collapsed_to_one_line(tmp_path):
    """A stray newline in free text would otherwise be mis-parsed as a
    second entry on the next run — must not defeat idempotency."""
    ctx = tmp_path / "CONTEXT.md"
    upsert_term(ctx, term="Order", definition="a confirmed\npurchase\r\nof items.")
    content = read(ctx)
    assert "**Order** — a confirmed purchase of items." in content
    assert content.count("**Order**") == 1
    # Re-running with the same (unsanitized) input is still a no-op.
    before = content
    upsert_term(ctx, term="Order", definition="a confirmed\npurchase\r\nof items.")
    assert read(ctx) == before


def test_blank_term_is_rejected(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    with pytest.raises(ValueError):
        upsert_term(ctx, term="   ", definition="x")
    assert not ctx.exists()


def test_blank_definition_is_rejected(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    with pytest.raises(ValueError):
        upsert_term(ctx, term="Order", definition="\n\n")
    assert not ctx.exists()


def test_term_containing_entry_delimiter_is_rejected(tmp_path):
    """A term containing '**' would corrupt the next parse (external code
    review, P4.1) — reject it outright rather than silently mis-round-trip."""
    ctx = tmp_path / "CONTEXT.md"
    with pytest.raises(ValueError):
        upsert_term(ctx, term="Bad** — injected", definition="x")
    assert not ctx.exists()


def test_existing_crlf_file_keeps_crlf_on_update(tmp_path):
    """Updating one term must not silently rewrite the whole file's line
    endings (external code review, P4.1)."""
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_bytes(
        b"# CONTEXT.md \xe2\x80\x94 Acme domain glossary\r\n\r\nAcme.\r\n\r\n"
        b"## Language\r\n\r\n**Order** \xe2\x80\x94 a confirmed purchase.\r\n\r\n"
        b"## Relationships\r\n\r\n## Flagged ambiguities\r\n"
    )
    upsert_term(ctx, term="Cancellation", definition="voiding an Order before it ships.")
    raw = ctx.read_bytes()
    assert b"\r\n" in raw
    assert b"\n" not in raw.replace(b"\r\n", b"")
    assert "**Cancellation**" in read(ctx)


def test_project_name_and_summary_are_sanitized_on_creation(tmp_path):
    """An embedded newline in --project-name/--summary must not inject a
    heading/entry into a freshly created file (external code review, P4.1)."""
    ctx = tmp_path / "CONTEXT.md"
    upsert_term(
        ctx, term="Order", definition="x",
        project_name="Acme\n## Language\n**Evil** — injected",
        summary="one\nline\nsummary",
    )
    content = read(ctx)
    lines = content.splitlines()
    # sanitization must prevent a REAL heading/entry from being parsed out of
    # the injected text — it need not scrub the substring from free-text prose
    heading_lines = [ln for ln in lines if ln == "## Language"]
    entry_lines = [ln for ln in lines if ln.startswith("**Evil**")]
    assert len(heading_lines) == 1
    assert entry_lines == []
    assert "one line summary" in content


def test_duplicate_heading_in_existing_file_is_rejected(tmp_path):
    """A malformed hand-edited file with two '## Language' headings must not
    silently drop the first occurrence's content (external code review, P4.1)."""
    ctx = tmp_path / "CONTEXT.md"
    ctx.write_text(
        "# CONTEXT.md — Acme domain glossary\n\nAcme.\n\n"
        "## Language\n\n**Order** — a confirmed purchase.\n\n"
        "## Language\n\n**Cancellation** — voiding an order.\n\n"
        "## Relationships\n\n## Flagged ambiguities\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        upsert_term(ctx, term="Refund", definition="returning money for a cancelled order.")
