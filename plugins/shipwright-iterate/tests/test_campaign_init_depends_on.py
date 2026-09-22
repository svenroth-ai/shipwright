"""``campaign_init.py``'s ``depends_on`` write-time validation
(campaign-dag-scheduler R1): charset + structural hard-reject on new rows,
``stacked`` branch_strategy warning (non-blocking), and the generated
``campaign.md`` / ``status.json`` shape.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "tools"))

from campaign_init import init_campaign  # noqa: E402


@pytest.fixture
def project(tmp_path):
    return tmp_path


class TestDependsOnWrite:
    def test_valid_graph_writes_depends_on_column_and_field(self, project):
        subs = [
            {"id": "A", "slug": "alpha", "title": "First"},
            {"id": "B", "slug": "bravo", "title": "Second", "depends_on": ["A"]},
        ]
        result = init_campaign(project, "demo", "intent", subs, "serial")
        campaign_dir = Path(result["campaign_dir"])

        md = (campaign_dir / "campaign.md").read_text(encoding="utf-8")
        assert "| ID | Slug | Title | Status | Depends On |" in md
        assert "| B | bravo | Second | pending | A |" in md

        status = json.loads((campaign_dir / "status.json").read_text(encoding="utf-8"))
        by_id = {s["id"]: s for s in status["sub_iterates"]}
        assert by_id["A"]["depends_on"] == []
        assert by_id["B"]["depends_on"] == ["A"]
        assert by_id["A"]["merged_commit"] is None

    def test_self_dependency_rejected(self, project):
        subs = [{"id": "A", "slug": "alpha", "depends_on": ["A"]}]
        with pytest.raises(ValueError, match="depends on itself"):
            init_campaign(project, "demo", "intent", subs, "serial")

    def test_unknown_dependency_rejected(self, project):
        subs = [{"id": "A", "slug": "alpha", "depends_on": ["ZZZ"]}]
        with pytest.raises(ValueError, match="unknown id"):
            init_campaign(project, "demo", "intent", subs, "serial")

    def test_cycle_rejected(self, project):
        subs = [
            {"id": "A", "slug": "alpha", "depends_on": ["B"]},
            {"id": "B", "slug": "bravo", "depends_on": ["A"]},
        ]
        with pytest.raises(ValueError, match="cycle"):
            init_campaign(project, "demo", "intent", subs, "serial")

    def test_duplicate_id_rejected(self, project):
        subs = [
            {"id": "A", "slug": "alpha"},
            {"id": "A", "slug": "alpha2"},
        ]
        with pytest.raises(ValueError, match="duplicate"):
            init_campaign(project, "demo", "intent", subs, "serial")

    def test_charset_violation_rejected_at_write_time(self, project):
        # Unlike the READ side (safe_project_campaign_status), write-time
        # treats a charset violation as a hard reject too. Match the actual
        # finding text, not just "charset" — that word also appears in this
        # wrapper's own static boilerplate ("charset and structural
        # violations are both hard errors here"), so a bare "charset" match
        # would still pass even if the finding were misclassified as
        # structural (code review finding, low).
        subs = [{"id": "bad--id", "slug": "x"}]
        with pytest.raises(ValueError, match="charset: invalid id"):
            init_campaign(project, "demo", "intent", subs, "serial")

    def test_traversal_slug_rejected_at_write_time(self, project):
        # 3f-bis remediation (code review finding, medium, security):
        # `slug` feeds `filename = f"{id}-{slug}.md"` / `spec_path`
        # unvalidated before this fix — a traversal slug could write
        # outside the campaign directory.
        subs = [{"id": "A", "slug": "../../../../evil"}]
        with pytest.raises(ValueError, match="safe-path"):
            init_campaign(project, "demo", "intent", subs, "serial")

    def test_traversal_campaign_slug_rejected_at_write_time(self, project):
        # 3f-bis remediation (doubt review finding, medium, security):
        # `campaign_slug` is the MORE powerful sibling of the `slug` fix
        # above — it picks the campaign's ROOT directory, not just a file
        # inside it.
        subs = [{"id": "A", "slug": "alpha"}]
        with pytest.raises(ValueError, match="campaign_slug"):
            init_campaign(project, "../../../../evil", "intent", subs, "serial")

    def test_id_slug_join_collision_rejected_at_write_time(self, project):
        # 3f-bis remediation (doubt review finding, medium): `id` and `slug`
        # are each individually charset-safe, but the generated spec
        # filename joins them with a single `-` — an interior character
        # BOTH operands may contain — so distinct, individually-valid pairs
        # can collide on one filename and silently clobber each other.
        subs = [
            {"id": "A", "slug": "b-c"},
            {"id": "A-b", "slug": "c"},
        ]
        with pytest.raises(ValueError, match="collide"):
            init_campaign(project, "demo", "intent", subs, "serial")

    def test_non_dict_sub_iterate_rejected_at_write_time(self, project):
        # Doubt review finding (medium): a non-dict element (e.g.
        # `--sub-iterates '["x"]'`) previously raised an uncaught
        # AttributeError on `.get`, past this function's ValueError-only
        # contract.
        with pytest.raises(ValueError, match="must be a JSON object"):
            init_campaign(project, "demo", "intent", ["x"], "serial")

    def test_depends_on_must_be_a_list_not_a_string(self, project):
        # Code review finding (medium): list("AB") == ["A", "B"] silently
        # re-splits a bare string into characters instead of raising.
        subs = [{"id": "A", "slug": "alpha"}, {"id": "B", "slug": "bravo", "depends_on": "A"}]
        with pytest.raises(ValueError, match="must be a JSON list"):
            init_campaign(project, "demo", "intent", subs, "serial")

    def test_depends_on_must_contain_only_strings(self, project):
        subs = [{"id": "A", "slug": "alpha"}, {"id": "B", "slug": "bravo", "depends_on": [5]}]
        with pytest.raises(ValueError, match="must be a JSON list"):
            init_campaign(project, "demo", "intent", subs, "serial")

    def test_depends_on_non_list_non_string_raises_valueerror_not_typeerror(self, project):
        # A bare int previously reached `list(5)` -> TypeError, escaping
        # main()'s `except ValueError` boundary uncaught (code review finding).
        subs = [{"id": "A", "slug": "alpha"}, {"id": "B", "slug": "bravo", "depends_on": 5}]
        with pytest.raises(ValueError, match="must be a JSON list"):
            init_campaign(project, "demo", "intent", subs, "serial")

    def test_stacked_strategy_warns_not_rejects(self, project, capsys):
        subs = [{"id": "A", "slug": "alpha"}, {"id": "B", "slug": "bravo"}]
        result = init_campaign(project, "demo", "intent", subs, "stacked")
        assert result["branch_strategy"] == "stacked"  # not rejected
        err = capsys.readouterr().err
        assert "stacked" in err.lower() and "deprecated" in err.lower()

    def test_title_pipe_is_escaped_in_campaign_md_table(self, project):
        # 3f-bis remediation (code review finding, medium): an unescaped `|`
        # in `title` shifts every later cell in that markdown-table row —
        # parse_campaign_skeleton's header-indexed column_map reads the
        # shifted text as the NEXT column, e.g. Status's "pending" landing in
        # Depends On, or (worse) an unrelated cell being misread as a
        # dependency id with no error at all.
        subs = [
            {"id": "A", "slug": "alpha", "title": "Compare A | B tradeoffs"},
            {"id": "B", "slug": "bravo", "title": "Second", "depends_on": ["A"]},
        ]
        result = init_campaign(project, "demo", "intent", subs, "serial")
        campaign_dir = Path(result["campaign_dir"])
        md = (campaign_dir / "campaign.md").read_text(encoding="utf-8")
        assert "| A | alpha | Compare A \\| B tradeoffs | pending |  |" in md
        assert "| B | bravo | Second | pending | A |" in md

        from lib.campaign_status import parse_campaign_skeleton

        rows = parse_campaign_skeleton(md)
        by_id = {r["id"]: r for r in rows}
        assert by_id["A"]["depends_on"] == []
        assert by_id["B"]["depends_on"] == ["A"]

    def test_title_trailing_backslash_roundtrips_and_does_not_corrupt_columns(self, project):
        # Doubt-review remediation (medium): a single-char lookbehind
        # (`(?<!\\)\|`) only inspects the ONE char before a `|`, so a title
        # ending in a literal, UNESCAPED backslash immediately adjacent to
        # the real delimiter would still merge the next cell into the title.
        # Escaping `\` -> `\\` at write time (ahead of `|` -> `\|`) plus a
        # pair-consuming scan at read time (any `\` + the next char is one
        # unit, not a fixed-width lookbehind) closes this for any content
        # this writer itself produces.
        subs = [
            {"id": "A", "slug": "alpha", "title": "Ends with backslash\\"},
            {"id": "B", "slug": "bravo", "title": "Second", "depends_on": ["A"]},
        ]
        result = init_campaign(project, "demo", "intent", subs, "serial")
        campaign_dir = Path(result["campaign_dir"])
        md = (campaign_dir / "campaign.md").read_text(encoding="utf-8")

        from lib.campaign_status import parse_campaign_skeleton

        rows = parse_campaign_skeleton(md)
        by_id = {r["id"]: r for r in rows}
        assert by_id["A"]["title"] == "Ends with backslash\\"
        assert by_id["A"]["depends_on"] == []
        assert by_id["B"]["depends_on"] == ["A"]

    def test_no_depends_on_key_defaults_empty_everywhere(self, project):
        subs = [{"id": "A", "slug": "alpha"}, {"id": "B", "slug": "bravo"}]
        result = init_campaign(project, "demo", "intent", subs, "serial")
        status = json.loads((Path(result["campaign_dir"]) / "status.json").read_text(encoding="utf-8"))
        assert all(s["depends_on"] == [] for s in status["sub_iterates"])
