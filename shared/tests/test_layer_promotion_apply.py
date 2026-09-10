"""Pins ``lib.layer_promotion_apply``'s write-ordering and safety properties
(P3.5, campaign req3-04c-ac-identity-wave2)."""

from __future__ import annotations

import pytest

from lib.layer_promotion_apply import (
    ConcurrentSpecEditError,
    compute_promotion_writes,
    record_ledger_entries,
    write_promotion_files,
)
from lib.layer_promotion_ledger import default_ledger
from lib.fr_table_shape import FR_TABLE_HEADER, FR_TABLE_SEPARATOR


_SPEC_RELPATH = ".shipwright/planning/01-adopted/spec.md"


def _write_spec(tmp_path, row):
    spec_dir = tmp_path / ".shipwright" / "planning" / "01-adopted"
    spec_dir.mkdir(parents=True)
    doc = "\n".join([
        "# Spec", "", "## Functional Requirements", "",
        FR_TABLE_HEADER, FR_TABLE_SEPARATOR, row, "",
    ])
    (spec_dir / "spec.md").write_text(doc, encoding="utf-8")


def _promote_decision(fr_id, layers, node):
    return {
        "fr": fr_id, "action": "promote", "required_layers": layers,
        "highest_ok": layers[-1], "spec_path": _SPEC_RELPATH, "_node": node,
    }


def test_compute_promotion_writes_rejects_a_decision_with_no_spec_path():
    # external code review (glm/low, P3.5 round 3): a malformed manifest node
    # must fail loudly and specifically HERE, not later as a misattributed
    # IsADirectoryError once resolve_spec_path_within_root defaults it to
    # the project root itself.
    from lib.fr_layer_cell_writer import LayerCellWriteError

    decision = {
        "fr": "FR-01.01", "action": "promote", "required_layers": ["unit"],
        "highest_ok": "unit", "spec_path": "", "_node": {},
    }
    with pytest.raises(LayerCellWriteError, match="no spec_path"):
        compute_promotion_writes("/unused", [decision])


def test_write_promotion_files_refuses_a_concurrent_edit(tmp_path):
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    _write_spec(tmp_path, row)
    node = {"id": "FR-01.01", "coverage": {"unit": "ok"}, "tests": {}}
    decisions = [_promote_decision("FR-01.01", ["unit"], node)]

    computed = compute_promotion_writes(tmp_path, decisions)

    # Someone edits the file after planning but before the write lands.
    spec_path = tmp_path / _SPEC_RELPATH
    spec_path.write_text(
        spec_path.read_text(encoding="utf-8").replace("Adopted", "Proposed"),
        encoding="utf-8",
    )

    with pytest.raises(ConcurrentSpecEditError):
        write_promotion_files(tmp_path, computed["contents"], computed["originals"])
    # The concurrent edit itself is preserved, not clobbered.
    assert "Proposed" in spec_path.read_text(encoding="utf-8")


def test_write_promotion_files_writes_when_nothing_changed_underneath(tmp_path):
    row = "| FR-01.01 | Adopted | x | Must | y. | code | unit (inferred) |"
    _write_spec(tmp_path, row)
    node = {"id": "FR-01.01", "coverage": {"unit": "ok"}, "tests": {}}
    decisions = [_promote_decision("FR-01.01", ["unit"], node)]

    computed = compute_promotion_writes(tmp_path, decisions)
    written = write_promotion_files(tmp_path, computed["contents"], computed["originals"])

    assert written == [_SPEC_RELPATH]
    spec = (tmp_path / _SPEC_RELPATH).read_text(encoding="utf-8")
    assert "(inferred)" not in spec


def test_record_ledger_entries_appends_one_promoted_entry_per_decision():
    ledger = default_ledger()
    node = {"id": "FR-01.01", "coverage": {"unit": "ok"}, "tests": {}}
    decisions = [_promote_decision("FR-01.01", ["unit"], node)]

    record_ledger_entries(ledger, decisions, run_id="iterate-test")

    entry = ledger["decisions"]["FR-01.01"][-1]
    assert entry["action"] == "promoted"
    assert entry["decided_by"] == "tool"
    assert entry["run_id"] == "iterate-test"


def test_record_ledger_entries_has_no_ci_run_id_when_decision_carries_none():
    # A bare hand-built decision (no `ci_evidence` key, as every OTHER test in
    # this file uses) must not crash and must not fabricate a ci_run_id.
    ledger = default_ledger()
    node = {"id": "FR-01.01", "coverage": {"unit": "ok"}, "tests": {}}
    decisions = [_promote_decision("FR-01.01", ["unit"], node)]

    record_ledger_entries(ledger, decisions, run_id="iterate-test")

    entry = ledger["decisions"]["FR-01.01"][-1]
    assert "ci_run_id" not in entry


def test_record_ledger_entries_names_the_ci_run_and_fingerprints_the_ci_sourced_node():
    # AC-R5 + AC-R12 (P3.5 restart round 2): the ledger entry (a) fingerprints
    # `decision["_node"]` -- which the CALLER (promote_required_layers.py) is
    # responsible for setting to the CI-SOURCED node, never the raw committed
    # one -- and (b) names the CI run id from `decision["ci_evidence"]`, so a
    # later reader can see WHICH run confirmed this, not only a content hash.
    from lib.layer_promotion_ledger import evidence_fingerprint

    ledger = default_ledger()
    committed_node = {"id": "FR-01.01", "coverage": {"unit": "ok", "integration": "ok"}, "tests": {}}
    ci_sourced_node = {"id": "FR-01.01", "coverage": {"unit": "ok"}, "tests": {}}
    decision = _promote_decision("FR-01.01", ["unit"], ci_sourced_node)
    decision["ci_evidence"] = {"status": "confirmed", "run_id": 34316980804, "fr_confirmed": True}

    record_ledger_entries(ledger, [decision], run_id="iterate-test")

    entry = ledger["decisions"]["FR-01.01"][-1]
    assert entry["ci_run_id"] == 34316980804
    assert entry["evidence_fingerprint"] == evidence_fingerprint(ci_sourced_node)
    assert entry["evidence_fingerprint"] != evidence_fingerprint(committed_node)


def test_record_ledger_entries_has_no_anchor_commit_when_decision_carries_none():
    ledger = default_ledger()
    node = {"id": "FR-01.01", "coverage": {"unit": "ok"}, "tests": {}}
    decisions = [_promote_decision("FR-01.01", ["unit"], node)]

    record_ledger_entries(ledger, decisions, run_id="iterate-test")

    entry = ledger["decisions"]["FR-01.01"][-1]
    assert "anchor_commit" not in entry


def test_record_ledger_entries_names_the_anchor_commit_from_ci_evidence():
    # P3.4c: `promote_required_layers.plan_promotions` sets
    # `decision["ci_evidence"]["anchor_commit"]` to the commit evidence was
    # actually resolved against -- this is what lets a later ledger reader
    # see WHICH commit's tests ran, distinct from `ci_run_id` (which CI run).
    ledger = default_ledger()
    node = {"id": "FR-01.01", "coverage": {"unit": "ok"}, "tests": {}}
    decision = _promote_decision("FR-01.01", ["unit"], node)
    decision["ci_evidence"] = {"status": "confirmed", "run_id": 999, "fr_confirmed": True,
                                "anchor_commit": "b" * 40}

    record_ledger_entries(ledger, [decision], run_id="iterate-test")

    entry = ledger["decisions"]["FR-01.01"][-1]
    assert entry["anchor_commit"] == "b" * 40
