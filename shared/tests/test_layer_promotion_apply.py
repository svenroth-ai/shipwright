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
