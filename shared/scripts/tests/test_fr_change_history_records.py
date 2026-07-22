"""FR change-history: how a single record is read (campaign S7).

Relation, labelling, summary fallback, amendments, record boundaries, coverage.
The outcome/ordering half is in ``test_fr_change_history.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._fr_history_fixtures import project, work  # noqa: E402

from lib.fr_change_history import (  # noqa: E402
    RELATION_AFFECTED,
    RELATION_INTRODUCED,
    STATUS_NO_CHANGES,
    change_history_for_fr,
)


# --------------------------------------------------------------------------
# Relation, labelling, summary fallback
# --------------------------------------------------------------------------

def test_new_frs_is_reported_as_introduced_and_wins_a_tie(tmp_path):
    root = project(tmp_path, [
        work(new_frs=["FR-01.01"], affected_frs=["FR-01.01"], adr_id="run-mint"),
    ])
    change = change_history_for_fr(root, "FR-01.01").changes[0]
    assert change.relation == RELATION_INTRODUCED


def test_affected_frs_is_reported_as_affected(tmp_path):
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    assert change_history_for_fr(root, "FR-01.01").changes[0].relation == RELATION_AFFECTED


def test_a_requirement_introduced_and_never_touched_again_reads_as_exactly_that(tmp_path):
    """The FR-01.15 shape: one ``introduced``, no ``affected``.

    The query must make that legible rather than smooth it into an ordinary
    history — a reader asking where a requirement came from wants the minting
    change named. (This docstring previously justified itself by saying
    compliance D1/D3 flag the shape as a gap; since iterate-2026-07-21 they do
    not, because a tested mint now counts as coverage and delivery. The
    fixture here is an UNTESTED mint, so it is unaffected either way.)
    """
    root = project(tmp_path, [
        work(new_frs=["FR-01.01"], adr_id="run-mint"),
        work(id="evt-other", affected_frs=["FR-01.02"], adr_id="run-other"),
    ])
    changes = change_history_for_fr(root, "FR-01.01").changes
    assert [c.relation for c in changes] == [RELATION_INTRODUCED]


def test_an_event_with_no_run_id_falls_back_to_its_event_id(tmp_path):
    root = project(tmp_path, [work(id="evt-anon", affected_frs=["FR-01.01"])])
    change = change_history_for_fr(root, "FR-01.01").changes[0]
    assert change.run_id == ""
    assert change.label == "evt-anon"


def test_run_id_field_is_accepted_where_adr_id_is_absent(tmp_path):
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], run_id="run-via-runid")])
    assert change_history_for_fr(root, "FR-01.01").changes[0].label == "run-via-runid"


def test_adr_id_wins_over_run_id_when_both_are_present(tmp_path):
    root = project(tmp_path, [
        work(affected_frs=["FR-01.01"], adr_id="run-adr", run_id="run-other"),
    ])
    assert change_history_for_fr(root, "FR-01.01").changes[0].label == "run-adr"


def test_summary_falls_back_to_description(tmp_path):
    root = project(tmp_path, [
        work(affected_frs=["FR-01.01"], adr_id="r", description="the terse one"),
    ])
    assert change_history_for_fr(root, "FR-01.01").changes[0].summary == "the terse one"


def test_summary_is_preferred_over_description(tmp_path):
    root = project(tmp_path, [
        work(affected_frs=["FR-01.01"], adr_id="r",
             summary="the operator sentence", description="the terse one"),
    ])
    assert change_history_for_fr(root, "FR-01.01").changes[0].summary == "the operator sentence"


def test_a_blank_or_non_string_fr_entry_never_matches(tmp_path):
    root = project(tmp_path, [work(affected_frs=["", "   ", None, 7], adr_id="run-junk")])
    assert change_history_for_fr(root, "FR-01.01").status == STATUS_NO_CHANGES


def test_a_non_list_fr_field_is_ignored_rather_than_raising(tmp_path):
    root = project(tmp_path, [work(affected_frs="FR-01.01", adr_id="run-str")])
    assert change_history_for_fr(root, "FR-01.01").status == STATUS_NO_CHANGES


def test_a_padded_fr_entry_still_matches(tmp_path):
    root = project(tmp_path, [work(affected_frs=["  FR-01.01 "], adr_id="run-pad")])
    assert change_history_for_fr(root, "FR-01.01").changes[0].label == "run-pad"


def test_a_prefix_of_the_queried_id_does_not_match(tmp_path):
    """``FR-01.01`` must not be answered by an event naming ``FR-01.011``."""
    root = project(tmp_path, [work(affected_frs=["FR-01.011"], adr_id="run-longer")])
    assert change_history_for_fr(root, "FR-01.01").status == STATUS_NO_CHANGES
