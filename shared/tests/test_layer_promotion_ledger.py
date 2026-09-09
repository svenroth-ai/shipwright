"""Pins ``lib.layer_promotion_ledger``'s shape, atomicity and history semantics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.layer_promotion_ledger import (
    ACTIONS,
    DECIDED_BY,
    ConcurrentLedgerEditError,
    append_decision,
    default_ledger,
    evidence_fingerprint,
    fingerprint_drifted,
    latest_decision,
    load_ledger,
    load_ledger_with_snapshot,
    write_ledger,
)


def test_load_ledger_missing_file_returns_a_fresh_default(tmp_path):
    ledger = load_ledger(tmp_path / "does-not-exist.json")
    assert ledger == default_ledger()


def test_write_then_load_round_trips(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = default_ledger()
    append_decision(ledger, "FR-01.01", action="promoted", decided_by="tool",
                     required_layers=["unit"], reason="evidence green")
    write_ledger(path, ledger)
    reloaded = load_ledger(path)
    assert reloaded == ledger
    assert latest_decision(reloaded, "FR-01.01")["action"] == "promoted"


def test_write_ledger_is_atomic_no_tmp_file_left_behind(tmp_path):
    path = tmp_path / "ledger.json"
    write_ledger(path, default_ledger())
    assert path.is_file()
    assert not path.with_name(path.name + ".tmp").exists()


def test_load_ledger_rejects_wrong_schema_version(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps({"schema_version": 999, "decisions": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        load_ledger(path)


def test_load_ledger_rejects_a_non_ledger_document(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps({"unrelated": True}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_ledger(path)


def test_load_ledger_rejects_an_unrecognised_action(tmp_path):
    # Stage-2 code-review Low 1+2, P3.5 post-push round: `append_decision`
    # validates the closed ACTIONS vocabulary on write; nothing previously
    # validated it on read. A hand-typo'd or foreign `action` (here
    # "demote", not "demoted") must fail closed here, not fall through
    # `evaluate_fr`'s literal-string branches as if the FR had no entry at
    # all -- silently reopening it to a second automated promotion.
    path = tmp_path / "ledger.json"
    path.write_text(
        json.dumps({
            "schema_version": 1,
            "decisions": {"FR-01.01": [{"action": "demote", "decided_by": "operator"}]},
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="FR-01.01"):
        load_ledger(path)


def test_load_ledger_rejects_a_non_list_decision_history(tmp_path):
    # Second symptom of the same gap: `latest_decision` assumes
    # `decisions[fr_id]` is a list -- a corrupted scalar value must fail
    # closed with the ledger's own ValueError, not a raw AttributeError.
    path = tmp_path / "ledger.json"
    path.write_text(
        json.dumps({"schema_version": 1, "decisions": {"FR-01.01": "promoted"}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="FR-01.01"):
        load_ledger(path)


def test_load_ledger_rejects_a_non_dict_history_entry(tmp_path):
    # A list of non-dicts (e.g. bare strings) must also fail closed rather
    # than raise a raw AttributeError/KeyError once something calls
    # `.get("action")` on it.
    path = tmp_path / "ledger.json"
    path.write_text(
        json.dumps({"schema_version": 1, "decisions": {"FR-01.01": ["promoted"]}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="FR-01.01"):
        load_ledger(path)


def test_latest_decision_is_the_last_appended_not_the_first(tmp_path):
    ledger = default_ledger()
    append_decision(ledger, "FR-01.11", action="promoted", decided_by="tool",
                     required_layers=["unit"], reason="first")
    append_decision(ledger, "FR-01.11", action="demoted", decided_by="operator",
                     reason="operator vetoed it later")
    assert latest_decision(ledger, "FR-01.11")["action"] == "demoted"
    # History is never overwritten — both entries survive.
    assert len(ledger["decisions"]["FR-01.11"]) == 2


def test_latest_decision_unknown_fr_is_none():
    assert latest_decision(default_ledger(), "FR-99.99") is None


def test_append_decision_rejects_unknown_action():
    ledger = default_ledger()
    with pytest.raises(ValueError):
        append_decision(ledger, "FR-01.01", action="approved", decided_by="tool", reason="x")


def test_append_decision_rejects_unknown_decided_by():
    ledger = default_ledger()
    with pytest.raises(ValueError):
        append_decision(ledger, "FR-01.01", action="promoted", decided_by="ai",
                         required_layers=["unit"], reason="x")


def test_evidence_fingerprint_is_stable_under_key_reordering():
    node_a = {"coverage": {"unit": "ok"}, "tests": {"unit": []}, "title": "A"}
    node_b = {"title": "A", "tests": {"unit": []}, "coverage": {"unit": "ok"}}
    assert evidence_fingerprint(node_a) == evidence_fingerprint(node_b)


def test_evidence_fingerprint_changes_when_coverage_changes():
    node_a = {"coverage": {"unit": "ok"}, "tests": {}}
    node_b = {"coverage": {"unit": "MISSING"}, "tests": {}}
    assert evidence_fingerprint(node_a) != evidence_fingerprint(node_b)


def test_closed_vocabularies_are_exactly_two_each():
    assert set(ACTIONS) == {"promoted", "demoted"}
    assert set(DECIDED_BY) == {"tool", "operator"}


def test_fingerprint_drifted_false_when_evidence_is_unchanged():
    node = {"coverage": {"unit": "ok"}, "tests": {}}
    entry = {"action": "promoted", "evidence_fingerprint": evidence_fingerprint(node)}
    assert fingerprint_drifted(entry, node) is False


def test_fingerprint_drifted_true_when_coverage_moved_on():
    node_then = {"coverage": {"unit": "ok"}, "tests": {}}
    node_now = {"coverage": {"unit": "MISSING"}, "tests": {}}
    entry = {"action": "demoted", "evidence_fingerprint": evidence_fingerprint(node_then)}
    assert fingerprint_drifted(entry, node_now) is True


def test_fingerprint_drifted_false_when_there_is_no_entry_or_no_recorded_fingerprint():
    node = {"coverage": {"unit": "ok"}, "tests": {}}
    assert fingerprint_drifted(None, node) is False
    assert fingerprint_drifted({"action": "promoted"}, node) is False


def test_evidence_fingerprint_is_stable_under_link_list_reordering():
    # Stage-2 code-review finding (P3.5 post-push round). Originally pinned a
    # dedicated link-sort step (`_link_sort_key`); since the round-4 post-push
    # doubt-review fix, `evidence_fingerprint` hashes only the two AGGREGATE
    # derived facts (`highest_ok_layer`, `bound_but_absent_layers`), which
    # never examine link identity or order at all -- so this invariant now
    # holds unconditionally, a strictly stronger guarantee than the sort-key
    # this test originally exercised. Kept as a regression pin either way.
    link_a = {"id": "t::a", "path": "t::a", "ac_id": "AC01"}
    link_b = {"id": "t::b", "path": "t::b", "ac_id": "AC02"}
    node_forward = {"coverage": {"unit": "ok"}, "tests": {"unit": [link_a, link_b]}}
    node_reversed = {"coverage": {"unit": "ok"}, "tests": {"unit": [link_b, link_a]}}
    assert evidence_fingerprint(node_forward) == evidence_fingerprint(node_reversed)


def test_evidence_fingerprint_is_stable_under_reordering_of_links_sharing_id_path_and_ac_id():
    # Low finding, Stage-3 doubt-review round 3, P3.5 post-push round. Same
    # note as the test above: the round-4 post-push doubt-review fix removed
    # `_link_sort_key` entirely -- link order/identity no longer participates
    # in the fingerprint at all, so this now holds unconditionally rather
    # than because of a specific tie-break key. Kept as a regression pin.
    link_marker = {"id": "t::a", "path": "t::a", "ac_id": "AC01", "tag_source": "marker"}
    link_comment = {"id": "t::a", "path": "t::a", "ac_id": "AC01", "tag_source": "comment"}
    node_forward = {"coverage": {"unit": "ok"}, "tests": {"unit": [link_marker, link_comment]}}
    node_reversed = {"coverage": {"unit": "ok"}, "tests": {"unit": [link_comment, link_marker]}}
    assert evidence_fingerprint(node_forward) == evidence_fingerprint(node_reversed)


def test_evidence_fingerprint_agrees_across_raw_content_that_differs_but_derives_the_same_facts():
    # Round-4 post-push doubt-review fix, HIGH (the core regression this
    # fingerprint change exists to close): two nodes whose RAW `tests` link
    # content differs (simulating the OS/marker-selection variance
    # `compare_traceability_manifest.py` documents as inherent) but whose
    # DERIVED facts (highest_ok_layer, bound_but_absent_layers) agree must
    # fingerprint IDENTICALLY -- this is what makes an operator's demoted
    # veto exitable only on a genuinely new evidence state, not on every run.
    node_then = {
        "coverage": {"unit": "ok"},
        "tests": {"unit": [{"id": "t::a", "path": "t::a", "ac_id": "AC01", "status": "enabled", "executed": "pass"}]},
    }
    node_now = {
        "coverage": {"unit": "ok"},
        # Different link identity/count (a different test collected this
        # run), same derived facts: still one "ok" unit layer, nothing
        # bound-but-absent.
        "tests": {"unit": [
            {"id": "t::b", "path": "t::b", "ac_id": "AC01", "status": "enabled", "executed": "pass"},
            {"id": "t::c", "path": "t::c", "ac_id": "AC01", "status": "enabled", "executed": "pass"},
        ]},
    }
    assert evidence_fingerprint(node_then) == evidence_fingerprint(node_now)


def test_evidence_fingerprint_disagrees_when_a_bound_test_actually_goes_absent():
    # Inverse of the test above: a REAL change to the derived facts (a bound
    # test that was previously decided now shows no decided outcome at all)
    # must still move the digest.
    node_then = {
        "coverage": {"unit": "ok"},
        "tests": {"unit": [{"id": "t::a", "path": "t::a", "ac_id": "AC01", "status": "enabled", "executed": "pass"}]},
    }
    node_now = {
        "coverage": {"unit": "ok"},
        "tests": {"unit": [{"id": "t::a", "path": "t::a", "ac_id": "AC01", "status": "enabled", "executed": "not_run"}]},
    }
    assert evidence_fingerprint(node_then) != evidence_fingerprint(node_now)


def test_evidence_fingerprint_agrees_across_a_shallow_copy_that_only_touches_required_layers():
    # Stage-3 doubt-review round 2, P3.5 post-push round: `promote_required_
    # layers.plan_promotions` builds `eval_node = dict(node)` and reassigns
    # only `required_layers_source`/`required_layers` before handing it to
    # `evaluate_fr` -- `coverage`/`tests` stay the SAME nested objects on
    # both `node` and `eval_node` (a shallow copy). `evidence_fingerprint`'s
    # payload today covers only those two keys, so the two agree by
    # construction -- COINCIDENTALLY, not because anything enforces it. If
    # the payload is ever widened to include `required_layers` (a plausible
    # future extension per this function's own docstring), the two would
    # silently diverge -- a demoted veto's drift gate would start comparing
    # against a unioned value nothing ever recorded. This test exists so
    # that future widening fails LOUDLY here, not silently in production.
    node = {
        "id": "FR-01.11", "required_layers": ["unit"],
        "required_layers_source": "inferred_legacy",
        "coverage": {"unit": "ok"}, "tests": {"unit": []},
    }
    eval_node = dict(node)
    eval_node["required_layers_source"] = "explicit"
    eval_node["required_layers"] = sorted({*node["required_layers"], "integration"})

    assert node["required_layers"] != eval_node["required_layers"]
    assert evidence_fingerprint(node) == evidence_fingerprint(eval_node)


def test_write_ledger_refuses_a_concurrent_edit(tmp_path):
    # Stage-2 code-review finding (P3.5 post-push round): the ledger's own
    # load-append-write sequence had no guard, unlike the LESS load-bearing
    # spec.md write (layer_promotion_apply.ConcurrentSpecEditError). Mirrors
    # test_write_promotion_files_refuses_a_concurrent_edit's shape.
    path = tmp_path / "ledger.json"
    ledger = default_ledger()
    append_decision(ledger, "FR-01.01", action="promoted", decided_by="tool",
                     required_layers=["unit"], reason="evidence green")
    write_ledger(path, ledger)

    # One read, not two (Stage-4 code-review Medium finding, P3.5 post-push
    # round): a separate load + snapshot-read pair is the exact anti-pattern
    # `load_ledger_with_snapshot`'s docstring warns against.
    loaded, snapshot = load_ledger_with_snapshot(path)

    # An operator's veto lands on FR-01.11 between this load and this write.
    concurrent = load_ledger(path)
    append_decision(concurrent, "FR-01.11", action="demoted", decided_by="operator",
                     reason="evidence is misleading for a reason the manifest can't show")
    write_ledger(path, concurrent)

    append_decision(loaded, "FR-01.02", action="promoted", decided_by="tool",
                     required_layers=["unit"], reason="evidence green")
    with pytest.raises(ConcurrentLedgerEditError):
        write_ledger(path, loaded, expected_snapshot=snapshot)

    # The concurrent veto is preserved, not clobbered.
    on_disk = load_ledger(path)
    assert latest_decision(on_disk, "FR-01.11")["action"] == "demoted"
    assert "FR-01.02" not in on_disk["decisions"]


def test_write_ledger_expected_snapshot_none_means_file_must_still_be_absent(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = default_ledger()
    append_decision(ledger, "FR-01.01", action="promoted", decided_by="tool",
                     required_layers=["unit"], reason="evidence green")

    # Someone else creates the file between this caller's (imagined) load of
    # a not-yet-existing ledger and this write.
    write_ledger(path, default_ledger())

    with pytest.raises(ConcurrentLedgerEditError):
        write_ledger(path, ledger, expected_snapshot=None)


def test_write_ledger_with_matching_snapshot_succeeds(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = default_ledger()
    write_ledger(path, ledger)
    _, snapshot = load_ledger_with_snapshot(path)

    append_decision(ledger, "FR-01.01", action="promoted", decided_by="tool",
                     required_layers=["unit"], reason="evidence green")
    write_ledger(path, ledger, expected_snapshot=snapshot)

    assert latest_decision(load_ledger(path), "FR-01.01")["action"] == "promoted"


def test_load_ledger_with_snapshot_reads_exactly_once(tmp_path, monkeypatch):
    # Stage-4 code-review Medium finding, P3.5 post-push round: the whole
    # point of this function is closing the two-read TOCTOU window a
    # separate load + snapshot-read call pair opens -- pin that it actually
    # reads once, not merely that it returns a tuple.
    path = tmp_path / "ledger.json"
    ledger = default_ledger()
    append_decision(ledger, "FR-01.01", action="promoted", decided_by="tool",
                     required_layers=["unit"], reason="evidence green")
    write_ledger(path, ledger)

    read_calls = []
    real_read_bytes = Path.read_bytes

    def counting_read_bytes(self):
        read_calls.append(self)
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)

    loaded, snapshot = load_ledger_with_snapshot(path)

    assert len(read_calls) == 1
    assert loaded == ledger

    # The snapshot round-trips as `write_ledger`'s `expected_snapshot` --
    # unchanged since the read above, so no concurrent edit is detected.
    append_decision(loaded, "FR-01.02", action="promoted", decided_by="tool",
                     required_layers=["unit"], reason="evidence green")
    write_ledger(path, loaded, expected_snapshot=snapshot)

    assert latest_decision(load_ledger(path), "FR-01.02")["action"] == "promoted"


def test_load_ledger_with_snapshot_missing_file_returns_none_snapshot(tmp_path):
    ledger, snapshot = load_ledger_with_snapshot(tmp_path / "does-not-exist.json")
    assert ledger == default_ledger()
    assert snapshot is None
