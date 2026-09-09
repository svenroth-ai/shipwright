"""``--avoid`` preservation / ``--clear-avoid`` tests for
shared/scripts/tools/write_context_term.py's ``upsert_term``.

Split out of ``test_write_context_term.py`` to keep both files under the
300-LOC bloat-baseline guideline. Covers the code-review finding (P4.1,
Stage-2 review round): re-sharpening a term WITHOUT repeating ``--avoid``
must not silently delete its existing ``_Avoid_`` line — interview-
protocol.md documents re-sharpening as safe to call with only
``--term``/``--definition``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.write_context_term import upsert_term


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_reupsert_without_avoid_keeps_existing_avoid_line(tmp_path):
    """Omitting --avoid on a re-sharpen must NOT silently delete an existing
    _Avoid_ line (code review, P4.1) — interview-protocol.md documents
    re-sharpening as safe to call with only --term/--definition."""
    ctx = tmp_path / "CONTEXT.md"
    upsert_term(ctx, term="Order", definition="v1", avoid="cart.")
    result = upsert_term(ctx, term="Order", definition="v2")
    assert result["status"] == "updated"
    content = read(ctx)
    assert "**Order** — v2" in content
    assert "_Avoid_ cart." in content


def test_reupsert_with_new_avoid_replaces_existing_avoid_line(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    upsert_term(ctx, term="Order", definition="v1", avoid="cart.")
    result = upsert_term(ctx, term="Order", definition="v2", avoid="basket.")
    assert result["status"] == "updated"
    content = read(ctx)
    assert "_Avoid_ basket." in content
    assert "_Avoid_ cart." not in content


def test_clear_avoid_deletes_the_existing_avoid_line(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    upsert_term(ctx, term="Order", definition="v1", avoid="cart.")
    result = upsert_term(ctx, term="Order", definition="v2", clear_avoid=True)
    assert result["status"] == "updated"
    content = read(ctx)
    assert "**Order** — v2" in content
    assert "_Avoid_" not in content


def test_avoid_and_clear_avoid_together_is_rejected(tmp_path):
    ctx = tmp_path / "CONTEXT.md"
    with pytest.raises(ValueError):
        upsert_term(ctx, term="Order", definition="v1", avoid="cart.", clear_avoid=True)
    assert not ctx.exists()
