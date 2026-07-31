"""Tests for the ADR index RENDERER — shared/scripts/lib/adr_index.py.

Title source and listing rules. Writing (atomicity, locking) lives in
``test_adr_index_writing.py``; the call sites that drive it (iterate F3, the
release pass, the CLI) and the staleness drift guard live in
``test_adr_index_producers.py``.

`INDEX.md` is a committed derived view of the ADR spec folder. Before
iterate-2026-07-31-adr-index-producer it had no producer on the path that
changes it: `aggregate_decisions.aggregate()` refreshed it only as a
side-effect of folding decision-drops, so an ADR an iterate wrote straight
into the folder never reached the index until some later release pass
happened to have drops.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.adr_index import (
    ADR_INDEX_FILENAME,
    ADR_SPEC_FOLDER,
    read_adr_title,
    rebuild_adr_index,
    render_adr_index,
)


def _folder(root: Path) -> Path:
    folder = root / ADR_SPEC_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _adr(root: Path, name: str, body: str) -> Path:
    path = _folder(root) / name
    path.write_text(body, encoding="utf-8")
    return path


def _rows(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.startswith("- [")]


# ---------------------------------------------------------------- title source


def test_title_comes_from_the_h1_heading(tmp_path):
    """Ledger 4 / AC3 — the label is the ADR's own title, not the slug."""
    _adr(tmp_path, "104-tt6-shared-backfill-engine.md", "# ADR 104 — TT6 shared engine\n")
    out = render_adr_index(_folder(tmp_path))
    assert "- [ADR-104 — TT6 shared engine](104-tt6-shared-backfill-engine.md)" in out
    # the slug form must NOT survive — that is the bug being fixed
    assert "tt6 shared backfill engine" not in out


@pytest.mark.parametrize(
    "heading",
    [
        "# ADR-054 — Triage Producer Contract",
        "# ADR 054 — Triage Producer Contract",
        "# ADR-054: Triage Producer Contract",
        "# ADR 054: Triage Producer Contract",
    ],
)
def test_adr_number_prefix_is_stripped_in_every_observed_style(tmp_path, heading):
    """Ledger 4 — all four prefix styles present in the real folder."""
    path = _adr(tmp_path, "054-triage-producer-contract.md", heading + "\n")
    assert read_adr_title(path) == "Triage Producer Contract"


def test_falls_back_to_the_slug_when_there_is_no_heading(tmp_path):
    """Ledger 5 / AC3 — the slug is the safety net, not the common path."""
    path = _adr(tmp_path, "060-c2-doc-hygiene-detectors.md", "no heading here\n")
    assert read_adr_title(path) is None
    out = render_adr_index(_folder(tmp_path))
    assert "- [ADR-060 — c2 doc hygiene detectors]" in out


def test_h2_is_not_read_as_the_title(tmp_path):
    """Ledger 16 / R2 — `##` is not an H1."""
    path = _adr(tmp_path, "070-x.md", "## Not the title\n\n# The real title\n")
    assert read_adr_title(path) == "The real title"


def test_heading_inside_a_fenced_code_block_is_not_the_title(tmp_path):
    """Ledger 17 / R2 — a `# run this` shell comment is not an ADR title."""
    body = "```bash\n# run this script\n```\n\n# The real title\n"
    path = _adr(tmp_path, "071-x.md", body)
    assert read_adr_title(path) == "The real title"


def test_tilde_fenced_code_block_is_also_skipped(tmp_path):
    """Ledger 17 / R2 — `~~~` fences are valid CommonMark too."""
    path = _adr(tmp_path, "072-x.md", "~~~\n# not a title\n~~~\n\n# Real\n")
    assert read_adr_title(path) == "Real"


def test_longer_fence_is_not_closed_by_a_shorter_one(tmp_path):
    """Ledger 25 / external code review — CommonMark fence-length matching.

    A ```` block may legitimately contain a ``` line. Matching only the first
    three characters closed the fence early and promoted a heading that was
    still inside the code block. Reproduced before the fix.
    """
    body = "````\n```\n# NOT a title - still inside the fence\n````\n\n# The real title\n"
    path = _adr(tmp_path, "076-x.md", body)
    assert read_adr_title(path) == "The real title"


def test_heading_inside_yaml_front_matter_is_not_the_title(tmp_path):
    """Ledger 18 / R2 — front matter comments are not titles."""
    body = "---\n# just a yaml comment\ntitle: x\n---\n\n# The real title\n"
    path = _adr(tmp_path, "073-x.md", body)
    assert read_adr_title(path) == "The real title"


def test_four_digit_number_is_not_mis_stripped(tmp_path):
    """Ledger 19 / R2 — `ADR-1040` must not be read as `ADR-104`."""
    path = _adr(tmp_path, "1040-x.md", "# ADR-1040 Notes\n")
    assert read_adr_title(path) == "Notes"


def test_heading_that_is_only_a_prefix_falls_back_to_the_slug(tmp_path):
    """Ledger 20 / R2 — stripping must not yield an empty label."""
    path = _adr(tmp_path, "074-some-real-slug.md", "# ADR-074\n")
    assert read_adr_title(path) is None
    assert "- [ADR-074 — some real slug]" in render_adr_index(_folder(tmp_path))


def test_link_metacharacters_in_a_title_are_escaped(tmp_path):
    """Ledger 11 / AC7 — a `[` in a title must not corrupt the link."""
    _adr(tmp_path, "075-x.md", "# Fix [brackets] in titles\n")
    out = render_adr_index(_folder(tmp_path))
    assert "- [ADR-075 — Fix \\[brackets\\] in titles](075-x.md)" in out


def test_backslash_before_a_bracket_cannot_break_out_of_the_label(tmp_path):
    """Ledger 26 / AC7 — escaping brackets alone is not enough.

    `Title \\]` became `Title \\\\]`: markdown reads the doubled backslash as one
    literal backslash and the `]` goes live, closing the label early so the rest
    of the heading supplies its own destination. Backslashes must escape first.
    """
    _adr(tmp_path, "077-x.md", "# Title \\] injected](https://evil.example)\n")
    row = next(
        ln for ln in render_adr_index(_folder(tmp_path)).splitlines() if ln.startswith("- [")
    )
    assert row.endswith("](077-x.md)"), f"link destination was hijacked: {row}"
    assert "https://evil.example" not in row.split("](")[-1]


def test_destination_with_parens_uses_angle_brackets(tmp_path):
    """Ledger 27 — a `)` in a filename would otherwise end the destination early."""
    _adr(tmp_path, "078-weird (name).md", "# Weird\n")
    out = render_adr_index(_folder(tmp_path))
    assert "- [ADR-078 — Weird](<078-weird (name).md>)" in out


def test_ordinary_filenames_are_not_angle_wrapped(tmp_path):
    """The escape must not churn the 37 existing rows."""
    _adr(tmp_path, "079-plain-slug.md", "# Plain\n")
    assert "- [ADR-079 — Plain](079-plain-slug.md)" in render_adr_index(_folder(tmp_path))


# -------------------------------------------------------------------- listing


def test_duplicate_numbers_both_appear(tmp_path):
    """Ledger 6 / AC4 — two files legitimately share one number (real: 097)."""
    _adr(tmp_path, "097-bloat-b7-rule-e-test-growth.md", "# ADR-097: B7 Rule E\n")
    _adr(tmp_path, "097-bloat-exception-oss-backend.md", "# ADR-097: oss_backend\n")
    rows = _rows(render_adr_index(_folder(tmp_path)))
    assert len(rows) == 2
    assert all(row.startswith("- [ADR-097 — ") for row in rows)


def test_tie_order_is_stable_against_title_edits(tmp_path):
    """Ledger 7 / AC4 — ties break on filename, so retitling cannot reshuffle.

    The prototype for this change sorted ties by label and silently swapped the
    two `097-` rows the moment their titles changed. Ordering must depend on the
    file identity, not on editable prose.
    """
    a = _adr(tmp_path, "097-aaa.md", "# ADR-097: zzz last alphabetically\n")
    _adr(tmp_path, "097-bbb.md", "# ADR-097: aaa first alphabetically\n")
    before = _rows(render_adr_index(_folder(tmp_path)))
    a.write_text("# ADR-097: now sorts completely differently\n", encoding="utf-8")
    after = _rows(render_adr_index(_folder(tmp_path)))
    assert [r.split("](")[1] for r in before] == [r.split("](")[1] for r in after]
    assert before[0].endswith("(097-aaa.md)")


def test_numeric_sort_is_not_lexicographic(tmp_path):
    _adr(tmp_path, "099-a.md", "# ADR-099: a\n")
    _adr(tmp_path, "100-b.md", "# ADR-100: b\n")
    rows = _rows(render_adr_index(_folder(tmp_path)))
    assert rows[0].endswith("(099-a.md)") and rows[1].endswith("(100-b.md)")


def test_the_template_is_excluded(tmp_path):
    """Ledger 10 / AC6 — `_template-*.md` is not an ADR.

    Rendering the template's own heading would list a placeholder
    ("Bloat exception — `<path/to/file>` raised to <new>-LOC") as if it were a
    real decision.
    """
    _adr(tmp_path, "_template-bloat-exception.md", "# ADR-XXX: Bloat exception\n")
    _adr(tmp_path, "080-real.md", "# ADR-080: Real\n")
    rows = _rows(render_adr_index(_folder(tmp_path)))
    assert rows == ["- [ADR-080 — Real](080-real.md)"]


def test_the_skip_does_not_swallow_real_underscore_files(tmp_path):
    """The exclusion is `_template-`, NOT every `_`-prefixed file.

    An earlier version skipped all of them and silently delisted
    `_archive-agent-doc-updates.md` — real content the previous index did link.
    Delisting a document nobody decided to delist is a quiet loss.
    """
    _adr(tmp_path, "_archive-agent-doc-updates.md", "# Archive — Agent-Doc Update Backlog\n")
    _adr(tmp_path, "080-real.md", "# ADR-080: Real\n")
    rows = _rows(render_adr_index(_folder(tmp_path)))
    assert "- [Archive — Agent-Doc Update Backlog](_archive-agent-doc-updates.md)" in rows
    # freeform names sort after the numbered ADRs
    assert rows[0].endswith("(080-real.md)")


def test_index_itself_is_never_listed(tmp_path):
    _adr(tmp_path, "081-real.md", "# ADR-081: Real\n")
    folder = _folder(tmp_path)
    rebuild_adr_index(tmp_path)
    rebuild_adr_index(tmp_path)
    rows = _rows((folder / ADR_INDEX_FILENAME).read_text(encoding="utf-8"))
    assert rows == ["- [ADR-081 — Real](081-real.md)"]


def test_empty_folder_renders_the_placeholder(tmp_path):
    out = render_adr_index(_folder(tmp_path))
    assert "_No ADR specs yet." in out and not _rows(out)


def test_render_is_idempotent_and_lf_only(tmp_path):
    """LF-space is the contract: core.autocrlf=true makes the worktree CRLF."""
    _adr(tmp_path, "082-x.md", "# ADR-082: X\n")
    first = render_adr_index(_folder(tmp_path))
    assert first == render_adr_index(_folder(tmp_path))
    assert "\r" not in first and first.endswith("\n")
