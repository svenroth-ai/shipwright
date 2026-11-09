"""atomic-frs U2: the pure halves of ``fr_split`` - spec cut, tag rewrite and the conservation check."""

from __future__ import annotations

import pytest

from .fr_split_fixtures import GROUPING, MOVES, PY, _ACS, _cut, _spec
from lib.ac_catalog import parse_catalog
from lib.ac_move_map import parse_move_map, resolve_ac
from lib.fr_split_check import check_bindings, check_catalog, check_manifest, check_names, coupling
from lib.fr_split_spec import SplitError, split_spec
from lib.fr_split_tags import rewrite_tags
from lib.fr_table_reader import read_fr_rows

pytestmark = pytest.mark.covers("FR-01.10")  # nearest FR: atomic-frs tooling has no catalog AC of its own yet (catalog_gap, how-only)


"""atomic-frs U2: ``fr_split`` cuts one FR into several and proves nothing was lost, doubled or reworded."""


def test_split_moves_criteria_keeps_numbers_and_text_and_adds_row_section_and_move_map():
    new, moves, ids = _cut()
    assert ids == ["FR-01.03"]
    assert moves == {f"FR-01.01/AC0{n}": f"FR-01.03/AC0{n}" for n in (4, 5, 6)}
    old_acs, new_acs = parse_catalog(_spec())[0], parse_catalog(new)[0]
    assert new_acs["FR-01.03.AC05"] == old_acs["FR-01.01.AC05"] and "FR-01.01.AC05" not in new_acs
    assert {k for k in new_acs if k.startswith("FR-01.01")} == {"FR-01.01.AC01", "FR-01.01.AC02", "FR-01.01.AC03"}
    assert "| FR-01.03 | Core | Mail reminders | Must | Remind customers by mail. | code | unit (inferred) |" in new
    assert '<a id="fr-0103"></a>\n### FR-01.03 — Mail reminders' in new
    assert parse_move_map(new) == moves and resolve_ac("FR-01.01/AC04", parse_move_map(new)) == "FR-01.03/AC04"
    assert check_catalog(_spec(), new, moves, ids) == []


def test_split_keeps_crlf_endings_and_next_free_number_counts_removed_rows():
    removed = "\n## Removed Requirements\n\n| ID | Area | Name | Priority | Description | Basis | Layers |\n|---|---|---|---|---|---|---|\n| FR-01.03 | Core | Gone | Must | Old. | code | unit |\n"
    new, _, ids = split_spec(_spec(removed).replace("\n", "\r\n"), GROUPING)
    assert ids == ["FR-01.04"] and "\r\n" in new and "\n" not in new.replace("\r\n", "")


def test_split_can_reword_the_source_that_stays():
    g = {**GROUPING, "remaining": {"title": "Plan storage", "description": "Store plans."}}
    new, *_ = _cut(grouping=g)
    assert "| FR-01.01 | Core | Plan storage | Must | Store plans. |" in new and "### FR-01.01 — Plan storage" in new


@pytest.mark.parametrize("grouping,why", [
    ({"source": "FR-01.01", "parts": [{"title": "T", "description": "D", "acs": [4, 5]}]}, "at least three"),
    ({"source": "FR-01.01", "parts": [{"title": "T", "description": "D", "acs": [2, 3, 4, 5]}]}, "keep at least three"),
    ({"source": "FR-01.01", "parts": [{"title": "T", "description": "D", "acs": [4, 5, 9]}]}, "does not have"),
    ({"source": "FR-01.01", "parts": [{"title": "A", "description": "D", "acs": [4, 5, 6]}, {"title": "B", "description": "D", "acs": [6, 1, 2]}]}, "twice"),
    ({"source": "FR-01.01", "parts": [{"title": "", "description": "D", "acs": [4, 5, 6]}]}, "title and a description"),
    ({"source": "FR-01.01", "parts": []}, "no parts"),
    ({"source": "FR-09.09", "parts": [{"title": "T", "description": "D", "acs": [1, 2, 3]}]}, "no row"),
])
def test_unsafe_groupings_are_refused(grouping, why):
    with pytest.raises(SplitError, match=why):
        split_spec(_spec(), grouping)


def test_a_criterion_without_an_id_marker_is_refused_not_guessed():
    with pytest.raises(SplitError, match="without an"):
        split_spec(_spec().replace("[AC03] ", ""), GROUPING)


def test_python_tags_move_only_where_they_bind():
    out = rewrite_tags("tests/test_x.py", PY, MOVES)
    assert '@pytest.mark.covers("FR-01.03/AC04", "FR-01.01/AC01")' in out
    assert "# FR-01.03.AC05 explained here" in out
    assert 'FIXTURE = "FR-01.01/AC04 is only fixture data"' in out
    assert '@pytest.mark.covers("FR-01.01")' in out


def test_js_comment_tags_move_and_other_text_does_not():
    js = "// @covers FR-01.01/AC04\nit('x', () => {});\nconst s = 1; /* FR-01.01.AC05 */\n"
    out = rewrite_tags("e2e/a.spec.ts", js, MOVES)
    assert out == "// @covers FR-01.03/AC04\nit('x', () => {});\nconst s = 1; /* FR-01.03.AC05 */\n"
    assert rewrite_tags("e2e/a.spec.ts", js, {"FR-01.01/AC09": "FR-01.03/AC09"}) == js


def test_js_slashes_inside_a_string_are_not_a_comment():
    js = "const u = 'http://x'; const t = \"// FR-01.01/AC04\";\nconst b = `a /* FR-01.01/AC05\n still string */`; // FR-01.01/AC05\n"
    out = rewrite_tags("e2e/a.spec.ts", js, MOVES)
    assert out == js.replace("; // FR-01.01/AC05", "; // FR-01.03/AC05")


def test_rewrite_keeps_crlf_and_non_ascii_columns():
    src = '# café\r\n@pytest.mark.covers("é", "FR-01.01/AC04")\r\ndef test_a(): ...\r\n'
    assert rewrite_tags("t.py", src, MOVES) == src.replace("FR-01.01/AC04", "FR-01.03/AC04")


def test_check_catalog_catches_a_lost_a_reworded_and_a_doubled_criterion():
    new, moves, ids = _cut()
    assert any("missing" in p for p in check_catalog(_spec(), new.replace("[AC05]", "[AC55]"), moves, ids))
    assert any("wording" in p for p in check_catalog(_spec(), new.replace("address bounces", "address changes"), moves, ids))
    doubled = new.replace("<a id=\"fr-0102\"></a>", "- (E) [AC04] " + _ACS[4] + "\n\n<a id=\"fr-0102\"></a>")
    assert any("doubled" in p or "count" in p for p in check_catalog(_spec(), doubled, moves, ids))
    assert any("Move-Map" in p for p in check_catalog(_spec(), new.replace("| `FR-01.01/AC06` | `FR-01.03/AC06` |\n", ""), moves, ids))


def test_check_bindings_wants_the_same_tests_under_the_new_ids():
    old = {"FR-01.01.AC04": {"t.py::a"}, "FR-01.01.AC01": {"t.py::b"}}
    ok = {"FR-01.03.AC04": {"t.py::a"}, "FR-01.01.AC01": {"t.py::b"}}
    moves = {"FR-01.01/AC04": "FR-01.03/AC04"}
    assert check_bindings(old, ok, moves) == []
    assert check_bindings(old, {"FR-01.03.AC04": {"t.py::a"}}, moves)  # AC01 lost its test
    assert check_bindings(old, {**ok, "FR-01.01.AC04": {"t.py::a"}}, moves)  # old id still bound


def test_check_manifest_compares_layer_test_and_source_per_criterion():
    def m(fr, ac, test):
        return {"requirements": {fr: {"id": fr, "acs": {ac: {"tests": {"unit": [{"id": test, "tag_source": "pytest_marker"}]}}}}}}
    moves = {"FR-01.01/AC04": "FR-01.03/AC04"}
    assert check_manifest(m("FR-01.01", "AC04", "t::a"), m("FR-01.03", "AC04", "t::a"), moves) == []
    assert check_manifest(m("FR-01.01", "AC04", "t::a"), m("FR-01.03", "AC04", "t::OTHER"), moves)


def test_names_with_implementation_detail_and_shared_tests_are_problems():
    assert check_names([{"title": "Calls run_split_tool.py", "description": "Fine words."}], None)
    problems, notes = coupling({"A": ["x.AC1"], "B": ["x.AC2"]}, {"x.AC1": {"t.py::a"}, "x.AC2": {"t.py::a"}}, {})
    assert problems
    problems, notes = coupling({"A": ["x.AC1"], "B": ["x.AC2"]}, {"x.AC1": {"t.py::a"}, "x.AC2": {"t.py::b"}}, {})
    assert not problems and notes  # same test file: a note only


def test_the_move_map_section_is_invisible_to_the_requirement_readers():
    """The readers that parse spec.md (FR table, catalog, fold map) must neither see a requirement nor lose one in the new section."""
    from lib.ac_catalog import parse_fr_table
    from lib.fr_table_reader import read_fr_rows
    new, _, ids = _cut()
    assert [r.id for r in read_fr_rows(new)] == ["FR-01.01", "FR-01.02", *ids]
    assert sorted(parse_fr_table(new)) == ["FR-01.01", "FR-01.02", "FR-01.03"]
    assert sorted(parse_catalog(new)[1]) == ["FR-01.01", "FR-01.02", "FR-01.03"]
    assert "FR-Fold-Map" not in new


def test_prose_between_criteria_a_doubled_marker_and_a_taken_target_are_refused():
    with pytest.raises(SplitError, match="unexpected text"):
        split_spec(_spec().replace("  Second line of 2.", "Stray paragraph."), GROUPING)
    with pytest.raises(SplitError, match="twice"):
        split_spec(_spec().replace("[AC03]", "[AC02]"), GROUPING)
    first, *_ = _cut()
    again = {**GROUPING, "parts": [{**GROUPING["parts"][0], "acs": [4, 5, 6]}]}
    with pytest.raises(SplitError):  # AC4-6 are gone from the source now
        split_spec(first, again)


def test_a_row_without_a_closing_pipe_keeps_all_its_cells_and_a_short_row_is_refused():
    spec = _spec().replace("| code | unit (inferred) |\n| FR-01.02", "| code | unit (inferred)\n| FR-01.02", 1)
    new, *_ = split_spec(spec, GROUPING)
    assert "| FR-01.03 | Core | Mail reminders | Must | Remind customers by mail. | code | unit (inferred) |" in new
    short = _spec().replace("| FR-01.01 | Core | Plans and mail | Must | Does plans and mail. | code | unit (inferred) |", "| FR-01.01 | Core | Plans and mail |")
    with pytest.raises(SplitError, match="as many cells"):
        split_spec(short, GROUPING)


def test_a_sub_heading_under_the_source_is_refused_and_a_pipe_in_a_description_is_escaped():
    with pytest.raises(SplitError, match="sub-heading"):
        split_spec(_spec().replace("\n<a id=\"fr-0102\">", "\n#### Notes\nProse.\n\n<a id=\"fr-0102\">"), GROUPING)
    g = {"source": "FR-01.01", "parts": [{**GROUPING["parts"][0], "description": "Mail a | b."}]}
    new, *_ = split_spec(_spec(), g)
    assert r"Mail a \| b." in new
    assert [r.id for r in read_fr_rows(new)][-1] == "FR-01.03"


def test_remaining_needs_title_and_description():
    with pytest.raises(SplitError, match="remaining"):
        split_spec(_spec(), {**GROUPING, "remaining": {"title": "Kept", "description": ""}})


def test_two_parts_with_one_title_are_refused_and_document_order_is_kept():
    dup = {"source": "FR-01.01", "parts": [{"title": "X", "description": "D", "acs": [4, 5, 6]}, {"title": "X", "description": "D", "acs": [1, 2, 3]}]}
    with pytest.raises(SplitError, match="both called"):
        split_spec(_spec(), dup)
    swapped = _spec().replace("[AC05]", "[AC9X]").replace("[AC04]", "[AC05]").replace("[AC9X]", "[AC04]")  # AC05 now precedes AC04 in the file
    new, *_ = split_spec(swapped, GROUPING)
    part = new[new.index("### FR-01.03"):]
    assert part.index("[AC05]") < part.index("[AC04]")


def test_the_two_digit_number_limit_is_a_refusal_not_a_broken_spec():
    rows = "".join(f"| FR-01.{n} | Core | N{n} | Must | D. | code | unit |\n" for n in range(10, 100))
    spec = _spec().replace("\n## Acceptance Criteria", "\n" + rows + "\n## Acceptance Criteria", 1).replace("| FR-01.02 | Core | Other thing | Must | Does other thing. | code | unit (inferred) |\n", "")
    with pytest.raises(SplitError, match="no free two-digit"):
        split_spec(spec, GROUPING)


def test_a_form_feed_in_a_test_file_does_not_shift_the_rewrite():
    src = 'import pytest\n\x0c\nX = "FR-01.01/AC04"\n@pytest.mark.covers("FR-01.01/AC04")\ndef test_a(): ...\n'
    out = rewrite_tags("t.py", src, MOVES)
    assert 'X = "FR-01.01/AC04"' in out and '@pytest.mark.covers("FR-01.03/AC04")' in out


def test_a_parametrize_row_that_mentions_covers_is_test_input_not_a_tag():
    src = 'import pytest\n@pytest.mark.parametrize("s", ["covers FR-01.01/AC04"])\n@pytest.mark.covers("FR-01.01/AC04")\ndef test_a(s): ...\n'
    out = rewrite_tags("t.py", src, MOVES)
    assert '["covers FR-01.01/AC04"]' in out and 'covers("FR-01.03/AC04")' in out
