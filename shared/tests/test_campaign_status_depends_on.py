"""``parse_campaign_skeleton``'s header-indexed rewrite + ``depends_on``
extraction, and ``project_campaign_status``'s carry-through of
``depends_on``/``merged_commit`` (campaign-dag-scheduler R1).
"""

from __future__ import annotations

from lib.campaign_status import parse_campaign_skeleton, project_campaign_status

MD_WITH_DEPENDS_ON = """---
campaign: demo
status: active
branch_strategy: serial
created: 2026-09-21T00:00:00+00:00
---

## Sub-Iterates

| ID | Slug | Title | Status | Depends On |
|---|---|---|---|---|
| A | alpha | First | pending |  |
| B | bravo | Second | pending | A |
| C | charlie | Third | pending | A, B |
"""

MD_NO_DEPENDS_ON_COLUMN = """---
campaign: demo
status: active
branch_strategy: serial
created: 2026-09-21T00:00:00+00:00
---

## Sub-Iterates

| ID | Slug | Title | Status |
|---|---|---|---|
| A | alpha | First | pending |
| B | bravo | Second | pending |
"""

MD_REORDERED_COLUMNS = """---
campaign: demo
---

## Sub-Iterates

| ID | Depends On | Slug | Status | Title |
|---|---|---|---|---|
| A |  | alpha | pending | First |
| B | A | bravo | pending | Second |
"""

MD_NO_HEADER_ROW = """---
campaign: demo
---

## Sub-Iterates

| A | alpha | First | pending |
| B | bravo | Second | pending |
"""


class TestParseSkeletonDependsOn:
    def test_extracts_comma_separated_ids(self):
        rows = parse_campaign_skeleton(MD_WITH_DEPENDS_ON)
        by_id = {r["id"]: r for r in rows}
        assert by_id["A"]["depends_on"] == []
        assert by_id["B"]["depends_on"] == ["A"]
        assert by_id["C"]["depends_on"] == ["A", "B"]

    def test_regression_no_depends_on_column_parses_unchanged(self):
        # An existing campaign.md with no "Depends On" column must still
        # parse id/slug/title correctly, with depends_on defaulting to [].
        rows = parse_campaign_skeleton(MD_NO_DEPENDS_ON_COLUMN)
        assert [r["id"] for r in rows] == ["A", "B"]
        assert rows[0] == {"id": "A", "slug": "alpha", "title": "First", "depends_on": []}
        assert rows[1] == {"id": "B", "slug": "bravo", "title": "Second", "depends_on": []}

    def test_header_indexed_survives_column_reorder(self):
        # Header-indexed lookup: id/slug/title/depends_on correct regardless
        # of physical column order in the table.
        rows = parse_campaign_skeleton(MD_REORDERED_COLUMNS)
        by_id = {r["id"]: r for r in rows}
        assert by_id["A"]["slug"] == "alpha"
        assert by_id["A"]["title"] == "First"
        assert by_id["A"]["depends_on"] == []
        assert by_id["B"]["depends_on"] == ["A"]

    def test_header_detected_when_id_column_is_not_first(self):
        # External Tier-3 PR review, blocking: header detection checked only
        # cells[0] == "id", so a header with ID in any OTHER position fell
        # through to the legacy positional fallback and misaligned columns.
        md = (
            "## Sub-Iterates\n\n"
            "| Slug | Title | ID | Depends On |\n"
            "|---|---|---|---|\n"
            "| alpha | First | A |  |\n"
            "| bravo | Second | B | A |\n"
        )
        rows = parse_campaign_skeleton(md)
        by_id = {r["id"]: r for r in rows}
        assert by_id["A"]["slug"] == "alpha"
        assert by_id["A"]["title"] == "First"
        assert by_id["A"]["depends_on"] == []
        assert by_id["B"]["depends_on"] == ["A"]

    def test_legacy_no_header_row_positional_fallback(self):
        rows = parse_campaign_skeleton(MD_NO_HEADER_ROW)
        assert rows[0] == {"id": "A", "slug": "alpha", "title": "First", "depends_on": []}
        assert rows[1] == {"id": "B", "slug": "bravo", "title": "Second", "depends_on": []}

    def test_markdown_emphasis_stripped_from_depends_on_tokens(self):
        md = MD_WITH_DEPENDS_ON.replace("| C | charlie | Third | pending | A, B |",
                                         "| C | charlie | Third | pending | **A**, `B` |")
        rows = parse_campaign_skeleton(md)
        by_id = {r["id"]: r for r in rows}
        assert by_id["C"]["depends_on"] == ["A", "B"]

    def test_escaped_pipe_in_title_does_not_shift_later_columns(self):
        # Code-review finding, medium: a literal `|` in title, escaped as
        # `\|` by the writer, must not be treated as a real delimiter.
        md = (
            "## Sub-Iterates\n\n"
            "| ID | Slug | Title | Status | Depends On |\n"
            "|---|---|---|---|---|\n"
            "| A | alpha | Compare A \\| B | pending |  |\n"
            "| B | bravo | Second | pending | A |\n"
        )
        rows = parse_campaign_skeleton(md)
        by_id = {r["id"]: r for r in rows}
        assert by_id["A"]["title"] == "Compare A | B"
        assert by_id["A"]["depends_on"] == []
        assert by_id["B"]["depends_on"] == ["A"]

    def test_escaped_trailing_backslash_before_delimiter_does_not_shift_columns(self):
        # Doubt-review finding, medium: a single-char-lookbehind split only
        # inspects the ONE char before `|`, so a title ending in an escaped
        # backslash (`\\` in the encoded text, one literal `\` decoded)
        # immediately adjacent to the real delimiter still mis-split under
        # that narrower rule. A pair-consuming scan must treat the writer's
        # `\\` -> `\` escape correctly regardless of adjacency.
        md = (
            "## Sub-Iterates\n\n"
            "| ID | Slug | Title | Status | Depends On |\n"
            "|---|---|---|---|---|\n"
            "| A | alpha | Ends with backslash\\\\ | pending |  |\n"
            "| B | bravo | Second | pending | A |\n"
        )
        rows = parse_campaign_skeleton(md)
        by_id = {r["id"]: r for r in rows}
        assert by_id["A"]["title"] == "Ends with backslash\\"
        assert by_id["A"]["depends_on"] == []
        assert by_id["B"]["depends_on"] == ["A"]


class TestBoundaryProbes:
    """Step 3.8 confidence calibration (touches_io_boundary): real empirical
    probes per boundary-probes.md's canonical categories for the new
    ``depends_on`` column. A leading BOM on a frontmatter-less file was a
    real, reproduced-then-fixed finding (see ``parse_campaign_skeleton``'s
    own docstring); the rest probed clean on the first pass — asymptote
    reached (one further probe after the BOM fix found nothing new)."""

    def test_utf8_bom_on_frontmatter_less_file(self):
        # Found & fixed: a BOM prefixing "## Sub-Iterates" (the literal
        # first line, when there's no YAML frontmatter ahead of it) broke
        # `stripped.startswith("## ")` section detection entirely, raising
        # a confusing "no table rows" error instead of parsing correctly.
        md = "﻿## Sub-Iterates\n\n| ID | Slug | Title | Status | Depends On |\n" \
             "|---|---|---|---|---|\n| A | alpha | First | pending |  |\n" \
             "| B | bravo | Second | pending | A |\n"
        rows = parse_campaign_skeleton(md)
        by_id = {r["id"]: r for r in rows}
        assert by_id["B"]["depends_on"] == ["A"]

    def test_utf8_bom_with_frontmatter_present(self):
        md = "﻿" + MD_WITH_DEPENDS_ON
        rows = parse_campaign_skeleton(md)
        by_id = {r["id"]: r for r in rows}
        assert by_id["C"]["depends_on"] == ["A", "B"]

    def test_crlf_line_endings(self):
        md = MD_WITH_DEPENDS_ON.replace("\n", "\r\n")
        rows = parse_campaign_skeleton(md)
        by_id = {r["id"]: r for r in rows}
        assert by_id["B"]["depends_on"] == ["A"]
        assert by_id["C"]["depends_on"] == ["A", "B"]

    def test_non_ascii_id_and_dependency(self):
        md = "## Sub-Iterates\n\n| ID | Slug | Title | Status | Depends On |\n" \
             "|---|---|---|---|---|\n| Ā | alpha | Fïrst | pending |  |\n" \
             "| B | bravo | Second | pending | Ā |\n"
        rows = parse_campaign_skeleton(md)
        by_id = {r["id"]: r for r in rows}
        assert by_id["B"]["depends_on"] == ["Ā"]

    def test_whitespace_only_depends_on_cell_is_empty(self):
        md = MD_WITH_DEPENDS_ON.replace("| A | alpha | First | pending |  |",
                                         "| A | alpha | First | pending |    |")
        rows = parse_campaign_skeleton(md)
        by_id = {r["id"]: r for r in rows}
        assert by_id["A"]["depends_on"] == []


class TestProjectCampaignStatusCarryThrough:
    def _committed(self):
        return {
            "campaign": "demo", "sub_iterates": [
                {"id": "A", "slug": "alpha", "status": "pending"},
                {"id": "B", "slug": "bravo", "status": "pending", "merged_commit": None},
            ],
        }

    def test_depends_on_carried_from_live_skeleton(self):
        status, _ = project_campaign_status(MD_WITH_DEPENDS_ON, self._committed(), [], "demo")
        by_id = {s["id"]: s for s in status["sub_iterates"]}
        assert by_id["B"]["depends_on"] == ["A"]
        assert by_id["C"]["depends_on"] == ["A", "B"]

    def test_merged_commit_carried_from_committed_status(self):
        committed = self._committed()
        committed["sub_iterates"][1]["merged_commit"] = "sha-b"
        status, _ = project_campaign_status(MD_WITH_DEPENDS_ON, committed, [], "demo")
        by_id = {s["id"]: s for s in status["sub_iterates"]}
        assert by_id["B"]["merged_commit"] == "sha-b"
        assert by_id["A"]["merged_commit"] is None

    def test_skeleton_override_used_for_frozen_reversion(self):
        # `skeleton=` lets a caller (lib.campaign_graph) pass an already
        # frozen-contract-reverted skeleton without a re-parse undoing it.
        rows = parse_campaign_skeleton(MD_WITH_DEPENDS_ON)
        for r in rows:
            if r["id"] == "B":
                r["depends_on"] = []  # simulate a frozen-contract revert
        status, _ = project_campaign_status(MD_WITH_DEPENDS_ON, self._committed(), [], "demo", skeleton=rows)
        by_id = {s["id"]: s for s in status["sub_iterates"]}
        assert by_id["B"]["depends_on"] == []  # reflects the OVERRIDE, not a re-parse
