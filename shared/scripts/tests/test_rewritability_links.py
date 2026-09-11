"""M7 (Rewritability) rationale-link classification (campaign
req3-04c-ac-identity-wave2, sub-iterate p3.8).

Three outcomes, never two — the same discipline
``lib/fr_change_history.py`` already applies (see that module's tests): a
requirement whose recorded changes never co-occur with a rationale-carrying
run is ``unlinked``; a requirement with NO recorded changes at all is
``could_not_determine``, a materially different (and much weaker) claim that
must never be silently folded into "confirmed unlinked".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._fr_history_fixtures import project, work  # noqa: E402

from lib.rewritability_links import (  # noqa: E402
    EventLogUnreadable,
    rationale_run_ids,
    scan_fr_rationale_links,
)


def _write_decision_drop(root: Path, run_id: str, name: str = "d_001.json") -> None:
    dd = root / ".shipwright" / "agent_docs" / "decision-drops"
    dd.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "date": "2026-09-01",
        "section": "Iterate — feature: test",
        "title": "A decision",
        "context": "Because.",
        "decision": "Did it.",
        "consequences": "Nothing changes.",
    }
    (dd / name).write_text(json.dumps(payload), encoding="utf-8")


def _write_decision_log(root: Path, *run_ids: str) -> None:
    agent_docs = root / ".shipwright" / "agent_docs"
    agent_docs.mkdir(parents=True, exist_ok=True)
    body = "\n".join(
        f"### ADR-{100 + i}: Something\n\n- **Run-ID:** {rid}\n"
        for i, rid in enumerate(run_ids)
    )
    (agent_docs / "decision_log.md").write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# rationale_run_ids
# ---------------------------------------------------------------------------


def test_rationale_run_ids_reads_pending_decision_drops(tmp_path):
    _write_decision_drop(tmp_path, "run-a")
    assert rationale_run_ids(tmp_path) == frozenset({"run-a"})


def test_rationale_run_ids_reads_aggregated_decision_log(tmp_path):
    _write_decision_log(tmp_path, "run-b")
    assert rationale_run_ids(tmp_path) == frozenset({"run-b"})


def test_rationale_run_ids_combines_and_dedups_both_sources(tmp_path):
    _write_decision_drop(tmp_path, "run-a")
    _write_decision_log(tmp_path, "run-a", "run-b")
    assert rationale_run_ids(tmp_path) == frozenset({"run-a", "run-b"})


def test_rationale_run_ids_empty_project_is_empty_set_not_an_error(tmp_path):
    assert rationale_run_ids(tmp_path) == frozenset()


def test_rationale_run_ids_ignores_a_malformed_drop_file(tmp_path):
    dd = tmp_path / ".shipwright" / "agent_docs" / "decision-drops"
    dd.mkdir(parents=True)
    (dd / "broken.json").write_text("{not json", encoding="utf-8")
    _write_decision_drop(tmp_path, "run-a", name="ok.json")
    assert rationale_run_ids(tmp_path) == frozenset({"run-a"})


def test_rationale_run_ids_ignores_a_drop_with_a_blank_decision_field(tmp_path):
    """External plan review (openai, medium): presence of a file is not
    evidence of a real rationale if the schema-required field is blank."""
    dd = tmp_path / ".shipwright" / "agent_docs" / "decision-drops"
    dd.mkdir(parents=True)
    payload = {
        "run_id": "run-a", "date": "2026-09-01", "section": "s",
        "title": "t", "context": "c", "decision": "   ", "consequences": "n",
    }
    (dd / "run-a_001.json").write_text(json.dumps(payload), encoding="utf-8")
    assert rationale_run_ids(tmp_path) == frozenset()


def test_pending_drop_run_ids_tolerates_an_unreadable_directory(tmp_path, monkeypatch):
    """External plan review (openai, HIGH): a filesystem fault on the
    decision-drops directory must degrade, never crash the advisory check."""
    _write_decision_drop(tmp_path, "run-a")

    def _raise(_dd):
        raise OSError("permission denied")

    monkeypatch.setattr("lib.rewritability_links.pending_drops", _raise)
    assert rationale_run_ids(tmp_path) == frozenset()


# ---------------------------------------------------------------------------
# scan_fr_rationale_links — the three outcomes
# ---------------------------------------------------------------------------


def test_a_requirement_whose_change_run_wrote_a_decision_drop_is_linked(tmp_path):
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    _write_decision_drop(root, "run-a")
    scan = scan_fr_rationale_links(root, ["FR-01.01"])
    assert scan.linked == ("FR-01.01",)
    assert scan.unlinked == ()
    assert scan.could_not_determine == ()


def test_a_requirement_with_changes_but_no_rationale_run_is_unlinked(tmp_path):
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    scan = scan_fr_rationale_links(root, ["FR-01.01"])
    assert scan.unlinked == ("FR-01.01",)
    assert scan.linked == ()
    assert scan.could_not_determine == ()


def test_a_requirement_with_no_recorded_changes_is_could_not_determine_not_unlinked(tmp_path):
    """The distinction this module exists for: no evidence != confirmed absence."""
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    scan = scan_fr_rationale_links(root, ["FR-01.02"])
    assert scan.could_not_determine == ("FR-01.02",)
    assert scan.unlinked == ()
    assert scan.linked == ()


def test_new_frs_relation_also_counts_toward_linkage(tmp_path):
    root = project(tmp_path, [work(new_frs=["FR-01.01"], adr_id="run-a")])
    _write_decision_drop(root, "run-a")
    scan = scan_fr_rationale_links(root, ["FR-01.01"])
    assert scan.linked == ("FR-01.01",)


def test_one_of_several_changing_runs_carrying_a_rationale_is_enough(tmp_path):
    root = project(tmp_path, [
        work(id="evt-1", affected_frs=["FR-01.01"], adr_id="run-a"),
        work(id="evt-2", affected_frs=["FR-01.01"], adr_id="run-b"),
    ])
    _write_decision_drop(root, "run-b")
    scan = scan_fr_rationale_links(root, ["FR-01.01"])
    assert scan.linked == ("FR-01.01",)


def test_corrupt_fragments_are_surfaced_not_swallowed(tmp_path):
    root = project(tmp_path, [work(affected_frs=["FR-01.01"], adr_id="run-a")])
    events_path = root / "shipwright_events.jsonl"
    # Append a corrupt trailing fragment — same shape the event-log reader
    # already tolerates elsewhere (undecodable / partial trailing record).
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write('{"type": "work_completed", "id": "evt-broken"\n')
    scan = scan_fr_rationale_links(root, ["FR-01.01"])
    assert scan.corrupt_fragments >= 1


def test_missing_event_log_is_could_not_determine_for_every_id(tmp_path):
    scan = scan_fr_rationale_links(tmp_path, ["FR-01.01", "FR-01.02"])
    assert scan.could_not_determine == ("FR-01.01", "FR-01.02")


def test_a_change_with_no_usable_run_id_is_unlinked_not_could_not_determine(tmp_path):
    """External code review (glm, low): an event naming an FR but carrying
    neither ``adr_id`` nor ``run_id`` used to be skipped entirely, silently
    reclassifying a real (if unattributable) recorded change as "no recorded
    change at all" — conflating two outcomes the three-outcome discipline
    exists to keep apart."""
    root = project(tmp_path, [work(affected_frs=["FR-01.01"])])  # no adr_id
    scan = scan_fr_rationale_links(root, ["FR-01.01"])
    assert scan.unlinked == ("FR-01.01",)
    assert scan.could_not_determine == ()
    assert scan.linked == ()


def test_run_id_bullet_regex_ignores_prose_and_fenced_mentions(tmp_path):
    """External code review (two independent providers, openai medium + glm
    low): the unanchored regex would read an unrelated ADR's prose or a
    quoted commit-message example as a real rationale record."""
    agent_docs = tmp_path / ".shipwright" / "agent_docs"
    agent_docs.mkdir(parents=True)
    body = (
        "### ADR-200: Some other decision\n\n"
        "This ADR's commit message quotes an EXAMPLE for illustration:\n\n"
        "```\n"
        "Run-ID: run-a\n"
        "**Run-ID:** run-a\n"
        "```\n\n"
        "The Context mentions Run-ID run-a in prose, not as a bullet.\n"
    )
    (agent_docs / "decision_log.md").write_text(body, encoding="utf-8")
    assert rationale_run_ids(tmp_path) == frozenset()


def test_event_log_unreadable_propagates_rather_than_degrading_to_empty(tmp_path, monkeypatch):
    def _raise(_root):
        raise EventLogUnreadable("boom")

    monkeypatch.setattr("lib.rewritability_links.read_work_events", _raise)
    try:
        scan_fr_rationale_links(tmp_path, ["FR-01.01"])
    except EventLogUnreadable:
        pass
    else:
        raise AssertionError("expected EventLogUnreadable to propagate")
