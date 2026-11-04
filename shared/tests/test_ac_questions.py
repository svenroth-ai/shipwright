"""The operator's question: resume by stable content (hold, answer, moved base, tampered options), unchanged items, the lettered pick list, the gloss."""

from __future__ import annotations

import argparse
import json

import pytest

from shared.tests.ac_test_helpers import PROMISE as _PROMISE
from shared.tests.ac_test_helpers import ans, cat_of, commit as _commit, decided as _decided, git as _git, repo as _repo
from lib import ac_catalog as cat
from lib import ac_decision as ad
from lib import ac_gloss
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
    held = tmp_path / "result.json"
    held.write_text(json.dumps(escalation), encoding="utf-8")
    answers = tmp_path / "answers.json"
    assert cli.main(["answer", "--decided", str(held), "--item", "0", "--choice", "A", "--answers", str(answers)]) == 0   # the operator
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


# --- 13: the plain-language pick list ----------------------------------------------------------------------------

_AREAS = ("### FR-01.03 - Saving drafts\n\n- (E) [AC05] Given a draft, when it is saved, then it is kept after a restart of the application.\n\n"
          "### FR-01.04 - Sharing drafts\n\n- (E) [AC01] Given a link, when it is opened, then the draft shows.\n\n"
          "### FR-01.05 - Billing\n\n- (E) [AC01] Given an invoice, when it is due, then it is sent.\n")


@pytest.mark.covers("FR-01.11/AC49")
def test_a_no_owner_question_is_a_lettered_pick_list_in_everyday_words():
    catalog = cat_of(_AREAS)
    r = ad.decide([{"kind": "add", "new_text": "A saved draft survives a restart"}], catalog, bind_id="b")
    q = r["questions"][0]
    text = q["question"]
    for jargon in ("feature", "FR-", "feature id"):
        assert jargon not in text
    assert text.startswith("This change adds a new promise: A saved draft survives a restart.\nWhich requirement would this promise belong to?")  # no model: the fixed wording
    lines = text.splitlines()[2:]
    assert lines[0].startswith("A Saving drafts: ") and "It is kept after a restart" in lines[0]
    assert lines[-4].startswith("C Somewhere new") and lines[-3].startswith("D It is not a promise") and lines[-2].startswith("E Not wanted:") and lines[-1].startswith("F I do not understand")
    assert q["options"]["A"] == {"choice": "yes", "text": "FR-01.03"} and q["options"]["C"] == {"choice": "other"} and q["options"]["D"] == {"choice": "not_a_promise"}
    assert q["options"]["F"] == {"choice": "explain"}
    again = ad.decide([{"kind": "add", "new_text": "A saved draft survives a restart"}], catalog, bind_id="b")["questions"][0]
    assert again == q                                                   # deterministic
    none = ad.decide([{"kind": "add", "new_text": "Orbits remain stable"}], catalog)["questions"][0]
    assert none["question"].splitlines()[2].startswith("A Applies to several areas") and none["options"]["A"] == {"choice": "cross_cutting"}   # no single owning area: its own requirement first
    assert none["question"].splitlines()[3].startswith("B An area that already exists") and none["options"]["B"] == {"choice": "yes"}


@pytest.mark.covers("FR-01.11/AC49")
def test_picking_new_area_or_not_a_promise_or_a_name_resolves_or_explains():
    catalog = cat_of(_AREAS)
    item = {"kind": "add", "new_text": "A saved draft survives a restart"}
    q = ad.decide([item], catalog, bind_id="b")["questions"][0]

    def go(choice, text=""):
        return ad.decide([item], catalog, bind_id="b", answers=[ans(q, choice, text)])
    assert "needs the name" in go("other")["errors"][0]
    made = go("other", "Offline mode")                                  # "Somewhere new" works: the name becomes a new area (next free id)
    assert made["status"] == "ok" and made["resolved_items"][0]["new_fr"] == {"id": "FR-01.06", "title": "Offline mode"} and made["resolved_items"][0]["owner_fr"] == "FR-01.06"
    assert go("other", "Uses plan_writer")["status"] == "invalid"        # the new area's title must read as an outcome
    assert "not a promise" in go("not_a_promise")["errors"][0]
    assert go("yes", "FR-01.04")["resolved_items"][0]["owner_fr"] == "FR-01.04"
    assert go("yes", "No such area")["status"] == "invalid" and "not one of the options" in go("yes", "No such area")["errors"][0]


@pytest.mark.covers("FR-01.11/AC49")
def test_the_gloss_explains_at_most_two_jargon_terms_once_and_only_from_the_data_file(tmp_path):
    g = ac_gloss.load_glossary()
    assert {"commit", "pull request", "stack profile", "gate", "phase", "pipeline", "review model", "build", "deployment", "coordinator"} <= set(g)
    text = "A commit is checked at the gate before the pull request opens, and the commit is kept"
    assert ac_gloss.jargon_terms(text) == ["commit", "gate", "pull request"]
    out = ac_gloss.gloss(text)
    assert out.startswith(" (commit: ") and "gate: " in out and "pull request" not in out and out.count(";") == 1 and out.count("commit:") == 1
    assert ac_gloss.gloss("Drafts are kept") == "" and ac_gloss.gloss("") == ""
    assert ac_gloss.jargon_terms("Commits are saved") == ["commit"] and ac_gloss.jargon_terms("a decommissioned thing") == []
    bad = tmp_path / "g.json"
    bad.write_text("{not json", encoding="utf-8")
    assert ac_gloss.load_glossary(bad) == {} and ac_gloss.load_glossary(tmp_path / "none.json") == {}
    custom = {"widget": "a small part"}
    assert ac_gloss.gloss("The widget works", custom) == " (widget: a small part)"
    q = ad.decide([{"kind": "add", "new_text": "Every commit is checked by a gate"}], cat_of(_AREAS))["questions"][0]["question"]
    assert "a saved snapshot of the work" in q.splitlines()[0] and "an automatic check" in q.splitlines()[0]
    assert "(commit: a saved snapshot" in ad.render_question({"kind": "change", "old_text": "Every commit is kept", "new_text": "Every commit is kept long"})   # a changed or removed promise explains its jargon too
    assert "(claude review: " in ad.render_question({"kind": "remove", "old_text": "Adopting a project sets up the automatic Claude review on every pull request"})


@pytest.mark.covers("FR-01.11/AC49")
def test_candidate_areas_rank_by_shared_words_and_the_blurb_is_one_short_line():
    catalog = cat_of(_AREAS)
    assert [fr for fr, _ in cat.candidates("Drafts are saved and shared", catalog)] == ["FR-01.03", "FR-01.04"]
    assert cat.candidates("nothing alike here", catalog) == []
    assert cat.area_blurb("FR-01.04", catalog) == "The draft shows."
    assert cat.area_blurb("FR-01.03", {"acs": {"FR-01.03.AC01": "- [AC01] " + "word " * 60}}) == ""   # too long: the name alone
    assert cat.area_blurb("FR-01.03", {"acs": {"FR-01.03.AC01": "- [AC01] Given x, when y, then it is kept — built, tested and reviewed."}}) == "It is kept."
    assert cat.area_blurb("FR-09.09", catalog) == ""

# --- resume binds to stable content: a moved base and tampered options -------------------------------------------

_MODEL = {"source": "model", "original_promise": _PROMISE, "plain_promise": "A draft you saved is still there after the application restarts.",
          "areas": [{"fr_id": "FR-01.03", "plain_description": "How drafts are kept."}], "model": "stub/model", "prompt_sha": "sha256:" + "c" * 64}


def _signed(q: dict, choice: str, text: str) -> dict:
    sha = q["question_sha256"]
    meta = {k: v for k, v in q.items() if k.startswith("suggestion_")}
    return {**ans(q, choice, text), **meta, "via": "operator", "signature": ac_hold.sign(ac_hold.load_key(create=True), sha, choice, text)}


@pytest.mark.covers("FR-01.11/AC49")
def test_a_signed_answer_survives_a_moved_base_and_never_calls_the_model_again():
    item = {"kind": "add", "new_text": _PROMISE}
    held = ad.decide([item], cat_of(_AREAS), bind_id="b", suggest=lambda n, it: _MODEL)["questions"][0]
    assert "In plain words: A draft you saved is still there" in held["question"] and held["suggestion_source"] == "model"
    entry = _signed(held, "yes", held["options"]["A"]["text"])
    moved = cat_of(_AREAS + "### FR-01.06 - A sibling unit added this area\n\n- (E) [AC01] Given x, when y, then z.\n")   # the base moved between hold and resume
    calls = []
    r = ad.decide([item], moved, bind_id="b", answers=[entry], suggest=lambda n, it: calls.append(n))
    assert calls == [] and r["status"] == "ok" and r["resolved_items"][0]["owner_fr"] == "FR-01.03"
    d = r["ac_decisions"][0]
    assert d["answered_via"] == "operator" and d["suggestion_source"] == "model" and d["suggestion_plain_promise"] == _MODEL["plain_promise"] and d["suggestion_model"] == "stub/model"
    assert r["resolved_items"][0]["new_text"] == _PROMISE                # the frozen text is the agent's


@pytest.mark.covers("FR-01.11/AC49")
def test_a_tampered_options_map_is_refused_and_a_forged_one_never_becomes_operator_signed():
    item = {"kind": "add", "new_text": _PROMISE}
    held = ad.decide([item], cat_of(_AREAS), bind_id="b")["questions"][0]
    honest = _signed(held, "yes", "FR-01.03")
    tampered = {**honest, "options": {**honest["options"], "A": {"choice": "yes", "text": "FR-01.05"}}}      # a letter map an agent rewrote
    r = ad.decide([item], cat_of(_AREAS), bind_id="b", answers=[tampered])
    assert r["status"] == "invalid" and "different question" in r["errors"][0]
    forged_opts = {"A": {"choice": "yes", "text": "FR-01.05"}}
    forged = {**honest, "options": forged_opts, "question_sha256": ac_hold.question_sha("b", 0, "add", {"old": "", "new": _PROMISE, "title": ""}, forged_opts), "text": "FR-01.05"}
    attended = ad.decide([item], cat_of(_AREAS), bind_id="b", answers=[forged])           # the sha is recomputed, but the signature is the honest one
    assert attended["ac_decisions"][0]["answered_via"] == "self-reported"
    unattended = ad.decide([item], cat_of(_AREAS), bind_id="b", unattended=True, answers=[forged])
    assert unattended["status"] == "invalid" and "operator channel" in unattended["errors"][0]
    off_list = {**honest, "text": "FR-01.05", "signature": ac_hold.sign(ac_hold.load_key(), held["question_sha256"], "yes", "FR-01.05")}   # signed, but not one of the options shown
    assert "not one of the options" in ad.decide([item], cat_of(_AREAS), bind_id="b", answers=[off_list])["errors"][0]
