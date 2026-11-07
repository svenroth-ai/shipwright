"""The operator's question: resume by stable content (hold, answer, moved base, tampered options), unchanged items, the numbered question."""

from __future__ import annotations

import argparse
import json

import pytest

from shared.tests.ac_test_helpers import PROMISE as _PROMISE
from shared.tests.ac_test_helpers import ans, cat_of, commit as _commit, decided as _decided, git as _git, repo as _repo
from lib import ac_catalog as cat
from lib import ac_decision as ad
from lib import ac_hold
from lib import ac_record as ar
from tools import ac_decision as cli
from tools.verifiers import pre_build_ac_check as chk

_RUN = "iterate-2026-11-01-q1-round3"
_BASE_SPEC = "### FR-01.03 - Saving drafts\n\n- (E) [AC05] Given a draft, when saved, then it is kept.\n\n### FR-01.04 - Sharing drafts\n\n- (E) [AC01] Given a link, when opened, then the draft shows.\n"


# --- 11: hold -> answer -> pending -> complete, with the same question hashes --------------------------------

@pytest.mark.covers("FR-01.11/AC49")
def test_resume_path_hold_answer_pending_complete(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from lib.autonomous_loop import cmd_record
    from lib.loop_mark import cmd_mark
    root = _repo(tmp_path)
    ask = tmp_path / "ask.json"
    ask.write_text(json.dumps({"items": [{"kind": "add", "new_text": _PROMISE}]}), encoding="utf-8")
    stable = "camp--Q1"
    common = ["--project-root", str(root), "--from-json", str(ask), "--base-ref", "HEAD", "--sub-iterate-id", "Q1", "--bind-id", stable]
    decided = tmp_path / "decided.json"
    assert cli.main([*common, "--autonomous", "--run-id", "run-attempt-0", "--out", str(decided)]) == 10
    escalation = json.loads(decided.read_text(encoding="utf-8"))["escalation"]
    state = tmp_path / "loop_state.json"
    state.write_text(json.dumps({"loop_id": "loop-1", "kind": "sub_iterate", "units": [
        {"id": "Q1", "status": "running", "attempt": 0, "attempt_id": "A0", "branch": "b", "finished_at": None, "commit": None}]}), encoding="utf-8")
    args = argparse.Namespace(state=str(state), unit="Q1", attempt_id="A0", result=json.dumps(escalation))
    assert cmd_record(args) == 0 and json.loads(state.read_text(encoding="utf-8"))["units"][0]["status"] == "held"
    assert json.loads(state.read_text(encoding="utf-8"))["units"][0]["reason_code"] == "ac_question_requires_operator"   # the row says why it is held
    held = tmp_path / "result.json"
    held.write_text(json.dumps(escalation), encoding="utf-8")
    answers = tmp_path / "answers.json"
    assert cli.main(["answer", "--decided", str(held), "--item", "0", "--choice", "1", "--answers", str(answers)]) == 0   # the operator
    assert cmd_mark(argparse.Namespace(state=str(state), unit="Q1", status="pending", reason="answered", operator="sven", reason_code=None,
                                       merged_commit=None, force=True, confirm_no_task_running=True, campaign_worktree=None)) == 0
    # the unit is claimed again under a NEW attempt and a NEW run id; the stable id keeps the question hashes equal
    rows = json.loads(state.read_text(encoding="utf-8"))
    rows["units"][0].update({"status": "running", "attempt": 1, "attempt_id": "A1"})
    state.write_text(json.dumps(rows), encoding="utf-8")
    capsys.readouterr()
    assert cli.main([*common, "--autonomous", "--run-id", "run-attempt-1", "--answers", str(answers), "--out", str(decided)]) == 0
    result = json.loads(decided.read_text(encoding="utf-8"))
    assert result["status"] == "ok" and result["ac_decisions"][0]["answered_via"] == "operator" and result["resolved_items"][0]["owner_fr"] == "FR-01.03"
    done = argparse.Namespace(state=str(state), unit="Q1", attempt_id="A1", result=json.dumps(
        {"status": "complete", "commit": "abc", "tests_passed": 1, "tests_total": 1, "branch": "b"}))
    assert cmd_record(done) == 0 and json.loads(state.read_text(encoding="utf-8"))["units"][0]["status"] == "built"
    capsys.readouterr()


# --- 12: unchanged = observable files change, the promise stays ---------------------------------------------

@pytest.mark.covers("FR-01.11/AC49")
def test_unchanged_needs_an_existing_ac_and_a_file_list_and_has_its_own_bucket():
    catalog = cat_of(_BASE_SPEC)
    ok = _decided([{"kind": "unchanged", "ac": "FR-01.03.AC05", "files": ["shared/scripts/a.py", "shared/scripts/b.py"]}])
    assert ok["status"] == "ok" and ok["counts"]["unchanged"] == 1 and ok["counts"]["auto"] == 0 and ok["ac_decisions"][0]["kind"] == "unchanged"
    assert ad.frozen_fields(ok["resolved_items"][0])["files"] == ["shared/scripts/a.py", "shared/scripts/b.py"]
    for bad in ({"kind": "unchanged", "ac": "FR-01.03.AC05"}, {"kind": "unchanged", "ac": "FR-01.03.AC05", "files": []},
                {"kind": "unchanged", "ac": "FR-01.03.AC05", "files": [3]}, {"kind": "unchanged", "ac": "FR-09.09.AC01", "files": ["a.py"]},
                {"kind": "unchanged", "files": ["a.py"]}):
        assert ad.decide([bad], catalog)["status"] == "invalid"


@pytest.mark.covers("FR-01.11/AC49")
def test_the_unchanged_record_is_checked_against_the_diff_and_a_test_naming_the_ac(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD")
    monkeypatch.setattr(chk, "_work_event", lambda r, rid: {"source": "iterate"})
    monkeypatch.setattr(chk, "_branch_base_commit", lambda r, c: base)
    _commit(root, {"shared/scripts/a.py": "x = 1\n", "shared/scripts/b.py": "y = 1\n"})
    ar.append_record(root, _RUN, _decided([{"kind": "unchanged", "ac": "FR-01.03.AC05", "files": ["shared/scripts/a.py"]}]))
    head = _commit(root, {}, amend=True)
    detail = chk.check_pre_build_ac_recorded(root, _RUN, head).detail
    assert "shared/scripts/b.py" in detail and "no test file in the diff mentions" in detail and "not a behaviour-preserving refactor" in detail
    ar.record_path(root, _RUN).unlink()
    ar.append_record(root, _RUN, _decided([{"kind": "unchanged", "ac": "FR-01.03.AC05", "files": ["shared/scripts/a.py", "shared/scripts/b.py"]}]))
    head = _commit(root, {"shared/tests/test_a.py": '@pytest.mark.covers("FR-01.03/AC05")\n'}, amend=True)
    assert chk.check_pre_build_ac_recorded(root, _RUN, head).ok


# --- 13: the question: finding, exact wording, numbered options, help last ----------------------------------------

_AREAS = ("### FR-01.03 - Saving drafts\n\n- (E) [AC05] Given a draft, when it is saved, then it is kept after a restart of the application.\n\n"
          "### FR-01.04 - Sharing drafts\n\n- (E) [AC01] Given a link, when it is opened, then the draft shows.\n\n"
          "### FR-01.05 - Billing\n\n- (E) [AC01] Given an invoice, when it is due, then it is sent.\n")


@pytest.mark.covers("FR-01.11/AC49")
def test_a_new_ac_without_an_owner_is_one_best_fitting_requirement_with_numbered_options_help_last():
    catalog = cat_of(_AREAS)
    r = ad.decide([{"kind": "add", "new_text": "A saved draft survives a restart"}], catalog, bind_id="b")
    q = r["questions"][0]
    text = q["question"]
    assert text.startswith("Shipwright keeps a list of requirements (FRs).")
    assert "Finding: this change adds a new acceptance criterion to an existing requirement.\n" in text
    assert 'New acceptance criterion: "A saved draft survives a restart"\nRequirement FR-01.03: "Saving drafts"\n\nDoes this fit?\n' in text      # the agent's wording, unchanged
    assert text.splitlines()[-4:] == ["1 Yes, add it there.", "2 No, wrong requirement. (You tell the agent in the chat which one.)", "3 No requirement fits, create a new one.", "4 Don't understand, need help."]
    assert q["options"] == {"1": {"choice": "yes", "text": "FR-01.03"}, "2": {"choice": "no"}, "3": {"choice": "new_fr", "text": "A saved draft survives a restart", "again": True}, "4": {"choice": "explain"}}
    for gone in ("In plain words", "Somewhere new", "not a promise", "Not wanted", "Where does it belong"):
        assert gone not in text
    assert ad.decide([{"kind": "add", "new_text": "A saved draft survives a restart"}], catalog, bind_id="b")["questions"][0] == q      # deterministic


@pytest.mark.covers("FR-01.11/AC49")
def test_a_changed_or_removed_ac_shows_the_exact_old_and_new_wording_and_the_requirements_own_text():
    spec = ("| ID | Area | Name | Priority | Description |\n|---|---|---|---|---|\n| FR-01.03 | Drafts | Saving drafts | Must | Keep every draft the author has saved, also after a restart. |\n\n"
            "### FR-01.03 - Saving drafts\n\n- (E) [AC05] Given a draft, when saved, then it is kept.\n")
    catalog = cat_of(spec) | {"fr_text": {"FR-01.03": "Keep every draft the author has saved, also after a restart."}, "groups": {"FR-01.03": "Drafts"}}
    old = catalog["acs"]["FR-01.03.AC05"]
    changed = ad.decide([{"kind": "change", "ac": "FR-01.03.AC05", "old_text": old, "new_text": "A draft is kept for a year"}], catalog)["questions"][0]["question"]
    assert "Finding: this change changes an existing acceptance criterion.\nPart: Drafts\n" in changed and changed.endswith("2 No. (You tell the agent in the chat what you want instead.)\n3 Don't understand, need help.")
    assert 'Requirement FR-01.03: "Saving drafts"' in changed and "Keep every draft" not in changed      # the requirement's name, not its long text
    removed = ad.decide([{"kind": "remove", "ac": "FR-01.03.AC05", "old_text": old}], catalog)["questions"][0]
    assert "Finding: this change removes an acceptance criterion." in removed["question"] and "Acceptance criterion that no longer holds:" in removed["question"]
    assert removed["question"].endswith("1 Yes, that is intended.\n2 No, keep it. (The change is then reworked.)\n3 Don't understand, need help.")
    assert removed["options"] == {"1": {"choice": "yes"}, "2": {"choice": "no"}, "3": {"choice": "explain"}}


@pytest.mark.covers("FR-01.11/AC49")
def test_a_requirement_that_does_not_exist_yet_is_created_from_a_declared_area_or_when_nothing_fits():
    catalog = cat_of(_AREAS)
    none = ad.decide([{"kind": "add", "new_text": "Orbits remain stable"}], catalog, bind_id="b")["questions"][0]
    assert "Finding: this change needs a requirement that does not exist yet." in none["question"] and "Requirement FR" not in none["question"] and "New requirement: Orbits remain stable" in none["question"]      # nothing fits: a drafted name, no existing one
    assert none["question"].splitlines()[-3:] == ["1 Yes, create it.", "2 No. (You tell the agent in the chat what you want instead.)", "3 Don't understand, need help."]
    made = ad.decide([{"kind": "add", "new_text": "Orbits remain stable"}], catalog, bind_id="b", answers=[ans(none, "new_fr", "Orbits remain stable")])
    assert made["status"] == "ok" and made["resolved_items"][0]["new_fr"] == {"id": "FR-01.06", "title": "Orbits remain stable"} and made["resolved_items"][0]["owner_fr"] == "FR-01.06"
    declared = ad.decide([{"kind": "add", "new_text": "Offline use works", "new_fr": {"id": "FR-01.30", "title": "Offline use"}}], catalog)["questions"][0]
    assert "New requirement: Offline use" in declared["question"] and "needs a requirement that does not exist yet" in declared["question"]
    assert declared["options"]["1"] == {"choice": "yes"}


@pytest.mark.covers("FR-01.11/AC49")
def test_answers_resolve_decline_or_name_a_requirement_and_no_hands_the_work_back_to_the_chat():
    catalog = cat_of(_AREAS)
    item = {"kind": "add", "new_text": "A saved draft survives a restart"}
    q = ad.decide([item], catalog, bind_id="b")["questions"][0]

    def go(choice, text=""):
        return ad.decide([item], catalog, bind_id="b", answers=[ans(q, choice, text)])
    assert go("yes", "FR-01.03")["resolved_items"][0]["owner_fr"] == "FR-01.03"
    again = go("new_fr", _PROMISE)                                                                           # "no requirement fits": one more question shows the drafted requirement
    assert again["status"] == "ask" and "New requirement: " + _PROMISE in again["questions"][0]["question"] and again["questions"][0]["options"]["1"] == {"choice": "yes"}
    final = ad.decide([item], catalog, bind_id="b", answers=[ans(q, "new_fr", _PROMISE), ans(again["questions"][0], "yes")])
    assert final["status"] == "ok" and final["resolved_items"][0]["new_fr"]["id"] == "FR-01.06" and final["resolved_items"][0]["owner_fr"] == "FR-01.06"
    declined = go("no")
    assert declined["status"] == "invalid" and "ask them in the chat" in declined["errors"][0]
    assert go("yes", "No such area")["status"] == "invalid" and "not one of the options" in go("yes", "No such area")["errors"][0]
    assert go("other", "x")["status"] == "invalid"                                                              # the removed answers are gone
    nofit = ad.decide([{"kind": "add", "new_text": "Orbits remain stable"}], catalog, bind_id="b")["questions"][0]
    assert ad.decide([{"kind": "add", "new_text": "Orbits remain stable"}], catalog, bind_id="b", answers=[ans(nofit, "yes", "FR-01.04")])["status"] == "invalid"   # 'yes' is not an option there


@pytest.mark.covers("FR-01.11/AC49")
def test_candidates_rank_by_shared_words():
    catalog = cat_of(_AREAS)
    assert [fr for fr, _ in cat.candidates("Drafts are saved and shared", catalog)] == ["FR-01.03", "FR-01.04"]
    assert cat.candidates("nothing alike here", catalog) == []


# --- resume binds to stable content: a moved base and tampered options -------------------------------------------

_MODEL = {"source": "model", "fr_id": "FR-01.04", "model": "stub/model", "prompt_sha": "sha256:" + "c" * 64, "reason": ""}


def _signed(q: dict, choice: str, text: str) -> dict:
    sha = q["question_sha256"]
    meta = {k: v for k, v in q.items() if k.startswith("suggestion_")}
    return {**ans(q, choice, text), **meta, "via": "operator", "signature": ac_hold.sign(ac_hold.load_key(create=True), sha, choice, text)}


@pytest.mark.covers("FR-01.11/AC49")
def test_a_signed_answer_survives_a_moved_base_and_never_calls_the_model_again():
    item = {"kind": "add", "new_text": _PROMISE}
    held = ad.decide([item], cat_of(_AREAS), bind_id="b", suggest=lambda n, it: _MODEL)["questions"][0]
    assert 'Requirement FR-01.04: "Sharing drafts"' in held["question"] and held["suggestion_source"] == "model" and held["suggestion_fr_id"] == "FR-01.04"    # the model's pick, validated
    entry = _signed(held, "yes", held["options"]["1"]["text"])
    moved = cat_of(_AREAS + "### FR-01.06 - A sibling unit added this requirement\n\n- (E) [AC01] Given x, when y, then z.\n")   # the base moved between hold and resume
    calls = []
    r = ad.decide([item], moved, bind_id="b", answers=[entry], suggest=lambda n, it: calls.append(n))
    assert calls == [] and r["status"] == "ok" and r["resolved_items"][0]["owner_fr"] == "FR-01.04"
    d = r["ac_decisions"][0]
    assert d["answered_via"] == "operator" and d["suggestion_source"] == "model" and d["suggestion_fr_id"] == "FR-01.04" and d["suggestion_model"] == "stub/model"
    assert r["resolved_items"][0]["new_text"] == _PROMISE                # the frozen text is the agent's
    wrong = ad.decide([item], cat_of(_AREAS), bind_id="b", suggest=lambda n, it: {**_MODEL, "fr_id": "FR-99.99"})["questions"][0]
    assert 'Requirement FR-01.03: "Saving drafts"' in wrong["question"]    # an id the catalog does not have is never shown: the deterministic best match is


@pytest.mark.covers("FR-01.11/AC49")
def test_a_tampered_options_map_is_refused_and_a_forged_one_never_becomes_operator_signed():
    item = {"kind": "add", "new_text": _PROMISE}
    held = ad.decide([item], cat_of(_AREAS), bind_id="b")["questions"][0]
    honest = _signed(held, "yes", "FR-01.03")
    tampered = {**honest, "options": {**honest["options"], "1": {"choice": "yes", "text": "FR-01.05"}}}      # an option map an agent rewrote
    r = ad.decide([item], cat_of(_AREAS), bind_id="b", answers=[tampered])
    assert r["status"] == "invalid" and "different question" in r["errors"][0]
    forged_opts = {"1": {"choice": "yes", "text": "FR-01.05"}}
    forged = {**honest, "options": forged_opts, "question_sha256": ac_hold.question_sha("b", 0, "add", {"old": "", "new": _PROMISE, "title": ""}, forged_opts), "text": "FR-01.05"}
    attended = ad.decide([item], cat_of(_AREAS), bind_id="b", answers=[forged])           # the sha is recomputed, but the signature is the honest one
    assert attended["ac_decisions"][0]["answered_via"] == "self-reported"
    unattended = ad.decide([item], cat_of(_AREAS), bind_id="b", unattended=True, answers=[forged])
    assert unattended["status"] == "invalid" and "operator channel" in unattended["errors"][0]
    off_list = {**honest, "text": "FR-01.05", "signature": ac_hold.sign(ac_hold.load_key(), held["question_sha256"], "yes", "FR-01.05")}   # signed, but not one of the options shown
    assert "not one of the options" in ad.decide([item], cat_of(_AREAS), bind_id="b", answers=[off_list])["errors"][0]
