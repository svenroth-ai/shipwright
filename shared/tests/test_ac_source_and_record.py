"""The per-item record fields (decided_by, confirmed), an unchanged AC named by a test that already exists at the base, and the visible source skip."""

from __future__ import annotations

import json

import pytest

from shared.tests.ac_test_helpers import BASE_SPEC, ans, cat_of, commit as _commit, decided as _decided, git as _git, repo as _repo
from lib import ac_record as ar
from tools.verifiers import pre_build_ac_check as chk

_RUN = "iterate-2026-11-02-fields"
_OLD = cat_of(BASE_SPEC)["acs"]["FR-01.03.AC05"]


# --- decided_by / confirmed on every item ------------------------------------------------------------------------------

@pytest.mark.covers("FR-01.11/AC49")
def test_every_auto_assigned_item_is_decided_by_auto_and_unconfirmed_and_shows_a_created_requirement():
    cat = cat_of(BASE_SPEC)
    items = [{"kind": "add", "new_text": "A saved draft survives a restart"}, {"kind": "add", "new_text": "Orbits remain stable"},
             {"kind": "change", "ac": "FR-01.03.AC05", "old_text": _OLD, "new_text": "A draft is kept for a year"}, {"kind": "remove", "ac": "FR-01.04.AC01", "old_text": cat["acs"]["FR-01.04.AC01"]},
             {"kind": "add", "new_text": "Offline use works", "new_fr": {"id": "FR-01.30", "title": "Offline use"}}]
    r = _decided(items, cat, mode="auto")
    assert r["status"] == "ok"
    assert [(d["decided_by"], d["confirmed"]) for d in r["ac_decisions"]] == [("auto", False)] * 5
    assert [i["decided_by"] for i in r["resolved_items"]] == ["auto"] * 5 and all(i["confirmed"] is False for i in r["resolved_items"])
    created = [d for d in r["ac_decisions"] if d.get("created_fr")]
    assert len(created) == 2 and all(d["assigned_fr"] for d in created)                                  # the record shows the requirement was created
    assert all(any(i.get("new_fr", {}).get("id") == d["assigned_fr"] for i in r["resolved_items"]) for d in created)
    assert all("decided_by=auto" in line or line.startswith("Assignments") for line in r["unconfirmed_assignments"])


@pytest.mark.covers("FR-01.11/AC49")
def test_an_answered_item_is_operator_confirmed_and_an_item_code_decided_alone_is_code_unconfirmed():
    cat = cat_of(BASE_SPEC)
    q = _decided([{"kind": "add", "new_text": "A saved draft survives a restart"}], cat, bind_id="b")["questions"][0]
    items = [{"kind": "add", "new_text": "A saved draft survives a restart"}, {"kind": "add", "owner_fr": "FR-01.03", "new_text": "A draft is kept"}, {"kind": "exempt"}]
    r = _decided(items, cat, bind_id="b", answers=[ans(q, "yes", "FR-01.03")])
    assert [d["mode"] for d in r["ac_decisions"]] == ["asked", "auto", "auto"]
    assert [(d["decided_by"], d["confirmed"]) for d in r["ac_decisions"]] == [("operator", True), ("code", False), ("code", False)]      # no question was shown for the last two
    assert [(i["decided_by"], i["confirmed"]) for i in r["resolved_items"]] == [("operator", True), ("code", False), ("code", False)]
    alone = _decided([items[1]], cat, mode="auto")                                                                                    # auto mode: a rule-decided item is code/false, not auto, and is not listed
    assert (alone["ac_decisions"][0]["decided_by"], alone["ac_decisions"][0]["confirmed"]) == ("code", False) and "unconfirmed_assignments" not in alone


@pytest.mark.covers("FR-01.11/AC49")
def test_the_fields_are_in_the_frozen_record_and_a_model_cannot_set_them(tmp_path):
    cat = cat_of(BASE_SPEC)
    spoof = {"kind": "add", "new_text": "A saved draft survives a restart", "decided_by": "operator", "confirmed": True}
    r = _decided([spoof], cat, mode="auto")
    assert r["resolved_items"][0]["decided_by"] == "auto" and r["resolved_items"][0]["confirmed"] is False       # code writes them, whatever the declaration said
    rec = ar.append_record(_repo(tmp_path), _RUN, r)
    assert rec["items"][0]["decided_by"] == "auto" and rec["items"][0]["confirmed"] is False
    assert json.loads(ar.record_path(tmp_path / "repo", _RUN).read_text(encoding="utf-8"))["items"][0]["confirmed"] is False


# --- unchanged: an AC named by a test that exists at the base -----------------------------------------------------------

def _unchanged_repo(tmp_path, base_test: str):
    root = _repo(tmp_path)
    if base_test:
        _commit(root, {"shared/tests/test_drafts.py": base_test})
    base = _git(root, "rev-parse", "HEAD")
    _commit(root, {"shared/scripts/a.py": "x = 1\n"})
    ar.append_record(root, _RUN, _decided([{"kind": "unchanged", "ac": "FR-01.03.AC05", "files": ["shared/scripts/a.py"]}]))
    return root, base, _commit(root, {}, amend=True)


@pytest.mark.covers("FR-01.11/AC49")
def test_an_unchanged_ac_named_only_by_an_untouched_test_at_the_base_does_not_warn(tmp_path):
    root, base, head = _unchanged_repo(tmp_path, '@pytest.mark.covers("FR-01.03/AC05")\ndef test_a(): pass\n')
    assert [p for p in ar.verify(root, _RUN, base, head) if "no test file" in p] == []
    a_dot = _unchanged_repo(tmp_path / "dot", "# checks FR-01.03.AC05\n")
    assert [p for p in ar.verify(a_dot[0], _RUN, a_dot[1], a_dot[2]) if "no test file" in p] == []


@pytest.mark.covers("FR-01.11/AC49")
def test_an_unchanged_ac_named_nowhere_warns_and_a_restore_still_needs_a_test_in_the_diff(tmp_path):
    root, base, head = _unchanged_repo(tmp_path, "def test_other(): pass\n")
    assert any("unchanged names FR-01.03.AC05, but no test file" in p for p in ar.verify(root, _RUN, base, head))
    other, obase, _ = _unchanged_repo(tmp_path / "r", '@pytest.mark.covers("FR-01.03/AC05")\n')
    ar.record_path(other, _RUN).unlink()
    ar.append_record(other, _RUN, _decided([{"kind": "restore", "restores_ac": "FR-01.03.AC05", "new_text": "A draft is kept"}]))
    ohead = _commit(other, {}, amend=True)
    assert any("restore names FR-01.03.AC05, but no test file in the diff mentions" in p for p in ar.verify(other, _RUN, obase, ohead))      # a base test does not satisfy a restore


# --- the source skip is visible; a campaign unit emits source iterate --------------------------------------------------

@pytest.mark.covers("FR-01.11/AC49")
def test_a_skipped_source_says_that_the_check_did_not_run(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setattr(chk, "_work_event", lambda r, rid: {"source": "manual"})
    res = chk.check_pre_build_ac_recorded(root, _RUN, _git(root, "rev-parse", "HEAD"))
    assert res.ok and "Q1 did not run: source=manual" in res.detail
    monkeypatch.setattr(chk, "_work_event", lambda r, rid: {})
    assert "Q1 did not run: source=unknown" in chk.check_pre_build_ac_recorded(root, _RUN, "").detail


@pytest.mark.covers("FR-01.11/AC49")
def test_a_campaign_unit_work_completed_event_always_has_source_iterate(tmp_path):
    from tools import finalize_iterate as fin
    root = _repo(tmp_path)
    extras = {"campaign": "ac-at-start", "sub_iterate_id": "Q1", "change_type": "tooling", "none_reason": "test", "source": "spoofed"}       # the campaign stamp, and a caller trying to set the source
    assert fin._record_event(root, "", _RUN, "campaign unit", extras)
    event = chk._work_event(root, _RUN)
    assert event["source"] == "iterate" and event["campaign"] == "ac-at-start" and event["sub_iterate_id"] == "Q1"          # the check is never skipped for a unit


# --- the mode actually used is durable: a flag reaches F11 -------------------------------------------------------------------

def _off_repo(tmp_path, monkeypatch, marker: bool):
    from tools import ac_decision as cli
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SHIPWRIGHT_AC_MODE", raising=False)                                           # the FLAG is the only source: no variable, no config
    root = _repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD")
    (tmp_path / "ask.json").write_text(json.dumps({"items": [{"kind": "add", "new_text": "A saved draft survives a restart"}]}), encoding="utf-8")
    if marker:
        assert cli.main(["--project-root", str(root), "--from-json", str(tmp_path / "ask.json"), "--base-ref", "HEAD", "--run-id", _RUN, "--ac-mode", "off"]) == 0
    head = _commit(root, {"shared/scripts/a.py": "x = 1"})                                              # git add -A also commits the marker the tool wrote
    return root, base, head


@pytest.mark.covers("FR-01.11/AC49")
def test_an_off_flag_writes_a_marker_and_f11_skips_with_a_visible_note(tmp_path, monkeypatch):
    root, base, head = _off_repo(tmp_path, monkeypatch, marker=True)
    assert json.loads((root / ".shipwright/planning/iterate" / _RUN / "ac-mode.json").read_text(encoding="utf-8")) == {"mode": "off", "run_id": _RUN, "source": "flag"}
    monkeypatch.setattr(chk, "_work_event", lambda r, rid: {"source": "iterate"})
    monkeypatch.setattr(chk, "_branch_base_commit", lambda r, c: base)
    res = chk.check_pre_build_ac_recorded(root, _RUN, head)
    assert res.ok and "Q1 off: mode=off (source=flag)" in res.detail                                  # an observable diff and no record, yet skipped


@pytest.mark.covers("FR-01.11/AC49")
def test_off_without_a_marker_still_warns_on_an_observable_diff_with_no_record(tmp_path, monkeypatch):
    root, base, head = _off_repo(tmp_path, monkeypatch, marker=False)
    monkeypatch.setattr(chk, "_work_event", lambda r, rid: {"source": "iterate"})
    monkeypatch.setattr(chk, "_branch_base_commit", lambda r, c: base)
    res = chk.check_pre_build_ac_recorded(root, _RUN, head)
    assert "no AC record exists" in res.detail and "Q1 off" not in res.detail
    monkeypatch.setenv("SHIPWRIGHT_AC_MODE", "off")                                                      # the variable alone is still seen without a marker
    assert "Q1 off: mode=off (source=env)" in chk.check_pre_build_ac_recorded(root, _RUN, head).detail
