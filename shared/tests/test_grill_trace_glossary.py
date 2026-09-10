"""Tests for shared/scripts/tools/grill_trace_glossary.py — the known-term
collection (union of shared/glossary.md + a target project's CONTEXT.md) used
by the grill-trace gate's undefined-term STOP. Split out of
test_verify_grill_trace_completeness.py when parse_glossary_terms /
collect_known_terms moved to their own module (external code review, P4.2).
"""

from __future__ import annotations

import tools.grill_trace_glossary as glossary_mod
from tools.grill_trace_glossary import (
    check_glossary_source_available,
    collect_known_terms,
    parse_glossary_terms,
)


def test_collect_known_terms_reads_glossary_bullets_and_context_language(tmp_path):
    glossary = tmp_path / "glossary.md"
    glossary.write_text(
        "# Glossary\n\n## Core mechanics\n\n"
        "- **Allowlist** — the bloat baseline file.\n"
        "- **Ratchet** — measured LOC exceeds the frozen value.\n",
        encoding="utf-8",
    )
    context = tmp_path / "CONTEXT.md"
    context.write_text(
        "# CONTEXT.md — Acme domain glossary\n\nAcme sells widgets.\n\n"
        "## Language\n\n**Order** — a confirmed purchase.\n",
        encoding="utf-8",
    )

    terms = collect_known_terms(glossary, context)

    assert terms == {"Allowlist", "Ratchet", "Order"}


def test_collect_known_terms_tolerates_a_missing_context_md(tmp_path):
    """A fresh project (or one P4.1's generator has not run against yet)
    legitimately has no CONTEXT.md — that contributes zero terms, not an
    error. A missing shared/glossary.md is the different, non-legitimate
    case check_glossary_source_available exists to catch."""
    glossary = tmp_path / "glossary.md"
    glossary.write_text("- **Order** — a confirmed purchase.\n", encoding="utf-8")

    terms = collect_known_terms(glossary, tmp_path / "does-not-exist" / "CONTEXT.md")

    assert terms == {"Order"}


def test_parse_glossary_terms_ignores_a_missing_file(tmp_path):
    assert parse_glossary_terms(tmp_path / "does-not-exist.md") == set()


def test_parse_glossary_terms_dedupes_a_repeated_mid_sentence_bold_phrase(tmp_path):
    """A bold phrase referenced again mid-sentence elsewhere in the glossary's
    own prose (not a new bullet entry) must not produce a second, distinct
    term — the set naturally dedupes, and no false term is introduced."""
    content = (
        "## Section\n\n"
        "- **Real Term** — a bullet-anchored entry, referencing "
        "a **Real Term** again mid-line.\n"
    )
    path = tmp_path / "glossary.md"
    path.write_text(content, encoding="utf-8")

    assert parse_glossary_terms(path) == {"Real Term"}


def test_check_glossary_source_available_passes_when_the_file_exists(tmp_path):
    glossary = tmp_path / "glossary.md"
    glossary.write_text("- **Order** — a confirmed purchase.\n", encoding="utf-8")

    result = check_glossary_source_available(glossary)

    assert result.ok is True


def test_check_glossary_source_available_fails_when_the_file_is_missing(tmp_path):
    """Unlike a missing CONTEXT.md, a missing shared/glossary.md means the
    Shipwright install itself is broken — external code review (P4.2) found
    the original code silently degraded this to an empty term set instead
    of surfacing it."""
    result = check_glossary_source_available(tmp_path / "does-not-exist.md")

    assert result.ok is False
    assert "does not exist" in result.detail


def test_check_glossary_source_available_fails_when_the_path_is_a_directory(tmp_path):
    """Round 3 (PR #705 review): ``.exists()`` is also True for a directory —
    a glossary *path* that resolves to a directory (e.g. a broken install
    that created the parent but never wrote the file) reproduces the same
    silent-non-read failure class as a missing file, and must fail here
    rather than crash or misreport downstream as ``malformed_context``.
    Portable across platforms (unlike a permission-denied simulation), so
    this is the primary regression case for the "exists but unreadable"
    failure family."""
    glossary_dir = tmp_path / "glossary.md"
    glossary_dir.mkdir()

    result = check_glossary_source_available(glossary_dir)

    assert result.ok is False
    assert "not a file" in result.detail
    assert "does not exist" not in result.detail


def test_check_glossary_source_available_fails_when_the_file_is_unreadable(
    tmp_path, monkeypatch,
):
    """A glossary path that exists and is a regular file but cannot actually
    be read (permissions, a locked handle, ...) must still fail here — the
    exact gap PR #705 round 3 found: the original code stopped at
    ``.exists()`` and never attempted a real read, so this case fell through
    to a later, misleadingly-named ``malformed_context`` failure (or, with
    no grill-traces recorded yet, was never surfaced at all). Simulated via
    a monkeypatch rather than ``os.chmod`` — a real chmod-based denial is not
    reliable on Windows CI, but replacing the module's own read call exercises
    the identical except-branch a real ``PermissionError`` would take."""
    glossary = tmp_path / "glossary.md"
    glossary.write_text("- **Order** — a confirmed purchase.\n", encoding="utf-8")

    def _denied(_path):
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(glossary_mod, "durable_read_bytes", _denied)

    result = check_glossary_source_available(glossary)

    assert result.ok is False
    assert "could not be read" in result.detail
    assert "does not exist" not in result.detail
    assert "not a file" not in result.detail


def test_check_glossary_source_available_fails_on_undecodable_content(
    tmp_path, monkeypatch,
):
    """The read succeeding but the decode failing (non-UTF-8 bytes) is the
    same failure family — surfaced here too, not left for
    ``collect_known_terms`` to trip over later."""
    glossary = tmp_path / "glossary.md"
    glossary.write_text("- **Order** — a confirmed purchase.\n", encoding="utf-8")

    monkeypatch.setattr(glossary_mod, "durable_read_bytes", lambda _path: b"\xff\xfe\x00")

    result = check_glossary_source_available(glossary)

    assert result.ok is False
    assert "could not be read" in result.detail
