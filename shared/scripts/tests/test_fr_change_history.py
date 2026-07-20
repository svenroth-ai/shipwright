"""The FR change-history query: outcomes and ordering (campaign S7).

Every behaviour ``lib/fr_change_history.py`` *claims* in a docstring is asserted
here against the code, on fixtures — not inferred from the live repo. Record
handling (relations, amendments, boundaries, coverage) is in
``test_fr_change_history_records.py``; the CLI in ``test_fr_history_cli.py``;
and the live-repo verification — does the query recover the history S6 deleted?
— in ``integration-tests/test_fr_change_history_recovers_compacted_history.py``.

Fixtures matter especially for ``no_recorded_changes``: every requirement in
this repo happens to have events, so that branch has NO live example. A branch
with no example is a branch nobody has seen run — which is how this campaign
previously shipped an unreachable red path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._fr_history_fixtures import SPEC_HEADER, project, work, write_events  # noqa: E402

from lib.fr_change_history import (  # noqa: E402
    STATUS_FOUND,
    STATUS_NO_CHANGES,
    STATUS_UNKNOWN_FR,
    change_history_for_fr,
)


# --------------------------------------------------------------------------
# The three outcomes
# --------------------------------------------------------------------------

def test_a_requirement_with_events_reports_found(tmp_path):
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    history = change_history_for_fr(root, "FR-01.01")
    assert history.status == STATUS_FOUND
    assert history.found is True
    assert [c.label for c in history.changes] == ["run-a"]


def test_a_real_requirement_with_no_events_is_no_recorded_changes_not_an_error(tmp_path):
    """The branch with no live example. An empty history is an ANSWER."""
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    history = change_history_for_fr(root, "FR-01.02")
    assert history.status == STATUS_NO_CHANGES
    assert history.changes == ()
    assert history.found is False
    assert history.existence_verified is True


def test_an_id_naming_no_requirement_is_unknown_not_an_empty_history(tmp_path):
    """The distinction the whole module exists for: typo != untouched."""
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    history = change_history_for_fr(root, "FR-99.99")
    assert history.status == STATUS_UNKNOWN_FR
    assert history.status != STATUS_NO_CHANGES


def test_an_unreadable_catalog_degrades_to_unverified_rather_than_unknown(tmp_path):
    """No specs on disk -> existence cannot be judged, so nothing is called a typo.

    Matches ``lib.fr_gates``' graduated write-side policy: the read side must
    not be stricter than the gate that admitted the data.
    """
    write_events(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    history = change_history_for_fr(tmp_path, "FR-77.77")
    assert history.existence_verified is False
    assert history.status == STATUS_NO_CHANGES


def test_a_catalog_that_parses_to_zero_rows_also_degrades_to_unverified(tmp_path):
    """Present-but-empty is the blind-scanner case, not 'every id is a typo'."""
    split = tmp_path / ".shipwright" / "planning" / "01-adopted"
    split.mkdir(parents=True)
    (split / "spec.md").write_text(SPEC_HEADER, encoding="utf-8")
    write_events(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    history = change_history_for_fr(tmp_path, "FR-01.01")
    assert history.existence_verified is False
    assert history.status == STATUS_FOUND


def test_the_queried_id_is_trimmed_before_lookup(tmp_path):
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    assert change_history_for_fr(root, "  FR-01.01  ").status == STATUS_FOUND


# --------------------------------------------------------------------------
# A retired requirement is still answerable (external review, Gemini #3/GPT #3)
# --------------------------------------------------------------------------

def test_an_id_absent_from_the_catalog_but_present_in_the_log_returns_its_history(tmp_path):
    """A retired requirement is not a typo.

    The catalog lists LIVE rows only (``read_active_fr_rows``), so judging on
    catalog membership alone would answer "no such requirement" about one that
    demonstrably existed and has recorded changes.
    """
    root = project(tmp_path,
                   [work(affected_frs=["FR-01.09"], adr_id="run-retired")],
                   fr_ids=("FR-01.01", "FR-01.02"))
    history = change_history_for_fr(root, "FR-01.09")
    assert history.status == STATUS_FOUND
    assert history.in_catalog is False
    assert [c.label for c in history.changes] == ["run-retired"]


def test_an_id_in_neither_the_catalog_nor_the_log_is_still_unknown(tmp_path):
    """Typo detection must survive the retired-requirement fix."""
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    history = change_history_for_fr(root, "FR-99.99")
    assert history.status == STATUS_UNKNOWN_FR
    assert history.in_catalog is False


def test_a_live_requirement_reports_in_catalog(tmp_path):
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    assert change_history_for_fr(root, "FR-01.01").in_catalog is True


def test_in_catalog_is_not_asserted_when_existence_is_unverifiable(tmp_path):
    """With nothing to check against, claiming 'not in the catalog' is a guess."""
    write_events(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    history = change_history_for_fr(tmp_path, "FR-01.01")
    assert history.existence_verified is False
    assert history.in_catalog is True


# --------------------------------------------------------------------------
# Unreadable records are surfaced, never swallowed
# --------------------------------------------------------------------------

def test_an_unreadable_fragment_is_counted_and_reported(tmp_path):
    """"No such change" and "the record could not be read" must not look alike."""
    root = project(tmp_path, [])
    good = json.dumps(work(id="evt-a", adr_id="run-a", affected_frs=["FR-01.01"]))
    (root / "shipwright_events.jsonl").write_text(
        good + "\n" + "{not json at all\n", encoding="utf-8"
    )
    history = change_history_for_fr(root, "FR-01.01")
    assert history.corrupt_fragments >= 1
    assert [c.label for c in history.changes] == ["run-a"], (
        "the readable records must still be returned"
    )


def test_a_clean_log_reports_no_fragments(tmp_path):
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    assert change_history_for_fr(root, "FR-01.01").corrupt_fragments == 0


def test_a_partially_written_trailing_record_does_not_crash_the_query(tmp_path):
    """The log is appended to while it is read, including by this campaign."""
    root = project(tmp_path, [])
    good = json.dumps(work(id="evt-a", adr_id="run-a", affected_frs=["FR-01.01"]))
    partial = '{"type": "work_completed", "id": "evt-b", "affec'
    (root / "shipwright_events.jsonl").write_text(good + "\n" + partial, encoding="utf-8")
    history = change_history_for_fr(root, "FR-01.01")
    assert [c.label for c in history.changes] == ["run-a"]


# --------------------------------------------------------------------------
# Ordering
# --------------------------------------------------------------------------

def test_events_are_ordered_by_instant_not_by_timestamp_string(tmp_path):
    """``08:00+02:00`` (=06:00Z) must precede ``07:30Z``; byte order disagrees."""
    root = project(tmp_path, [
        work(id="evt-late", ts="2026-03-01T07:30:00+00:00",
             affected_frs=["FR-01.01"], adr_id="run-0730z"),
        work(id="evt-early", ts="2026-03-01T08:00:00+02:00",
             affected_frs=["FR-01.01"], adr_id="run-0800plus2"),
    ])
    labels = [c.label for c in change_history_for_fr(root, "FR-01.01").changes]
    assert labels == ["run-0800plus2", "run-0730z"], (
        "ordering fell back to lexicographic string comparison"
    )


def test_a_z_suffixed_timestamp_is_accepted(tmp_path):
    root = project(tmp_path, [
        work(id="evt-a", ts="2026-03-01T09:00:00Z",
             affected_frs=["FR-01.01"], adr_id="run-z"),
        work(id="evt-b", ts="2026-03-01T08:00:00+00:00",
             affected_frs=["FR-01.01"], adr_id="run-offset"),
    ])
    labels = [c.label for c in change_history_for_fr(root, "FR-01.01").changes]
    assert labels == ["run-offset", "run-z"]


def test_a_naive_timestamp_is_read_as_utc(tmp_path):
    root = project(tmp_path, [
        work(id="evt-a", ts="2026-03-01T09:00:00+00:00",
             affected_frs=["FR-01.01"], adr_id="run-aware"),
        work(id="evt-b", ts="2026-03-01T08:00:00",
             affected_frs=["FR-01.01"], adr_id="run-naive"),
    ])
    labels = [c.label for c in change_history_for_fr(root, "FR-01.01").changes]
    assert labels == ["run-naive", "run-aware"]


def test_an_unparseable_timestamp_sorts_last_but_is_still_reported(tmp_path):
    """Dropping a record to keep a sort total is what this campaign stops."""
    root = project(tmp_path, [
        work(id="evt-bad", ts="not-a-date",
             affected_frs=["FR-01.01"], adr_id="run-bad"),
        work(id="evt-ok", ts="2026-03-01T09:00:00+00:00",
             affected_frs=["FR-01.01"], adr_id="run-ok"),
    ])
    labels = [c.label for c in change_history_for_fr(root, "FR-01.01").changes]
    assert labels == ["run-ok", "run-bad"]


def test_a_missing_timestamp_is_reported_too(tmp_path):
    events = [work(id="evt-nots", affected_frs=["FR-01.01"], adr_id="run-nots")]
    del events[0]["ts"]
    root = project(tmp_path, events)
    assert [c.label for c in change_history_for_fr(root, "FR-01.01").changes] == ["run-nots"]


def test_events_sharing_a_timestamp_tie_break_on_event_id(tmp_path):
    """A total order, so two runs of the same query cannot disagree."""
    root = project(tmp_path, [
        work(id="evt-b", ts="2026-03-01T09:00:00+00:00",
             affected_frs=["FR-01.01"], adr_id="run-b"),
        work(id="evt-a", ts="2026-03-01T09:00:00+00:00",
             affected_frs=["FR-01.01"], adr_id="run-a"),
    ])
    labels = [c.label for c in change_history_for_fr(root, "FR-01.01").changes]
    assert labels == ["run-a", "run-b"]


def test_the_queried_id_is_sanitised_by_the_library_not_only_by_the_cli(tmp_path):
    """FIX 2: the pair must be safe used directly, not safe by convention.

    ``change_history_for_fr`` and ``_render_text`` now both live in ``lib/`` and
    read as a usable pair. A caller that skips the CLI — which is where argv was
    folded — must not be able to get a raw escape into the rendered heading.
    """
    from lib.fr_history_render import _render_text

    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    history = change_history_for_fr(root, "FR-01.01\x1b[2J\nforged")

    assert "\x1b" not in history.fr_id
    assert "\n" not in history.fr_id
    assert "\x1b" not in _render_text(history, history.coverage)


def test_sanitising_the_queried_id_is_behaviour_neutral_for_a_normal_id(tmp_path):
    """CONTROL: a well-formed id is unchanged, so lookups still match."""
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    for raw in ("FR-01.01", "  FR-01.01  "):
        history = change_history_for_fr(root, raw)
        assert history.fr_id == "FR-01.01"
        assert history.status == STATUS_FOUND
