"""The three modes (ask / auto / off), the checked model lines, the code's own alternatives and the unconfirmed list. Hermetic: no provider, no key, temp dirs only."""

from __future__ import annotations

import json

import pytest

from shared.tests.ac_test_helpers import ans, cat_of, decided as _decided, git as _git, repo as _repo
from lib import ac_auto, ac_mode, ac_record as ar, ac_suggest as su
from tools import ac_decision as cli
from tools.verifiers import pre_build_ac_check as chk

_SPEC = ("### FR-01.03 - Saving drafts\n\n- (E) [AC05] Given a draft, when it is saved, then it is kept after a restart of the application.\n\n"
         "### FR-01.04 - Sharing drafts\n\n- (E) [AC01] Given a link, when it is opened, then the draft shows.\n\n"
         "### FR-01.05 - Billing\n\n- (E) [AC01] Given an invoice, when it is due, then it is sent.\n")
_CAT = cat_of(_SPEC)
_ADD = {"kind": "add", "new_text": "A saved draft survives a restart"}
_NONE = {"source": "model", "fr_id": None, "none": True, "line": "", "title": "How long a draft is kept", "sentence": "Say how long an unused draft stays."}


def _model(fr: str, **kw) -> dict:
    return {"source": "model", "fr_id": fr, "none": False, "line": "", "title": "", "sentence": "", "model": "stub/model", "prompt_sha": "sha256:" + "d" * 64, "reason": "", **kw}


# --- where the mode comes from -------------------------------------------------------------------------------------

@pytest.mark.covers("FR-01.11/AC49")
def test_the_mode_comes_from_the_flag_then_the_variable_then_the_project_then_the_default(tmp_path, monkeypatch):
    monkeypatch.delenv(ac_mode.ENV, raising=False)
    assert ac_mode.resolve_mode(tmp_path) == ("ask", "default")                                  # interactive: ask
    assert ac_mode.resolve_mode(tmp_path, unattended=True)[0] == "auto"                          # a unit that cannot ask: Shipwright's own pick
    (tmp_path / "shipwright_iterate_config.json").write_text(json.dumps({"ac_decision": {"mode": "ask"}}), encoding="utf-8")
    assert ac_mode.resolve_mode(tmp_path, unattended=True) == ("ask", "shipwright_iterate_config.json")      # the user can set ask explicitly, also unattended
    monkeypatch.setenv(ac_mode.ENV, "OFF")
    assert ac_mode.resolve_mode(tmp_path)[0] == "off"                                            # the variable (a campaign's setting) beats the project
    assert ac_mode.resolve_mode(tmp_path, cli="auto") == ("auto", "--ac-mode")                   # the flag beats both
    monkeypatch.setenv(ac_mode.ENV, "sometimes")
    with pytest.raises(ValueError, match="ask, auto, off"):
        ac_mode.resolve_mode(tmp_path)
    monkeypatch.delenv(ac_mode.ENV)
    (tmp_path / "shipwright_iterate_config.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="unreadable"):
        ac_mode.resolve_mode(tmp_path)                                                           # never a silent default


# --- auto: no question, every decision unconfirmed ------------------------------------------------------------------

@pytest.mark.covers("FR-01.11/AC49")
def test_auto_takes_the_model_pick_or_drafts_a_new_requirement_and_asks_nobody():
    r = _decided([_ADD, {"kind": "add", "new_text": "Orbits remain stable"}], _CAT, mode="auto", bind_id="b",
                 suggest=lambda n, it: _model("FR-01.04") if n == 0 else _NONE)
    assert r["status"] == "ok" and "questions" not in r
    first, second = r["resolved_items"]
    assert first["owner_fr"] == "FR-01.04" and second["new_fr"] == {"id": "FR-01.06", "title": "How long a draft is kept", "summary": "Say how long an unused draft stays."}
    assert second["owner_fr"] == "FR-01.06"
    for d in r["ac_decisions"]:
        assert d["mode"] == "auto-assigned" and d["unconfirmed"] is True and d["answered_via"] == "none" and d["note"]
    assert r["ac_decisions"][0]["suggestion_source"] == "model" and r["counts"]["unconfirmed"] == 2 and r["counts"]["asked"] == 0


@pytest.mark.covers("FR-01.11/AC49")
def test_auto_without_a_model_uses_the_best_match_by_shared_words_and_two_new_requirements_never_share_an_id():
    r = _decided([_ADD], _CAT, mode="auto", suggest=None)
    assert r["resolved_items"][0]["owner_fr"] == "FR-01.03"                                        # the deterministic best match
    two = _decided([{"kind": "add", "new_text": "Orbits remain stable"}, {"kind": "add", "new_text": "Tides rise slowly"}], _CAT, mode="auto")
    assert [i["new_fr"]["id"] for i in two["resolved_items"]] == ["FR-01.06", "FR-01.07"]
    assert two["resolved_items"][0]["new_fr"]["title"] == "Orbits remain stable"                  # no model draft: the criterion's own wording, no sentence


@pytest.mark.covers("FR-01.11/AC49")
def test_auto_passes_a_changed_or_removed_ac_through_and_lists_those_first():
    old = _CAT["acs"]["FR-01.03.AC05"]
    items = [_ADD, {"kind": "remove", "ac": "FR-01.03.AC05", "old_text": old}, {"kind": "change", "ac": "FR-01.04.AC01", "old_text": _CAT["acs"]["FR-01.04.AC01"], "new_text": "A shared link opens the draft"}]
    r = _decided(items, _CAT, mode="auto", suggest=lambda n, it: _model("FR-01.03"))
    assert r["status"] == "ok" and [d["kind"] for d in r["ac_decisions"]] == ["add", "remove", "change"]
    lines = r["unconfirmed_assignments"]
    assert lines[0].startswith("Assignments made without you") and len(lines) == 4
    assert lines[1].startswith("1. EXISTING CRITERION removed FR-01.03.AC05") and lines[2].startswith("2. EXISTING CRITERION changed FR-01.04.AC01") and lines[3].startswith("3. new criterion")
    assert ac_auto.unconfirmed_lines(_decided([{"kind": "exempt"}], _CAT, mode="auto")["ac_decisions"]) == []        # nothing assigned: no list


@pytest.mark.covers("FR-01.11/AC49")
def test_an_operator_answer_wins_over_auto_and_an_invalid_item_is_still_refused():
    q = _decided([_ADD], _CAT, bind_id="b")["questions"][0]
    r = _decided([_ADD], _CAT, mode="auto", bind_id="b", answers=[ans(q, "yes", "FR-01.03")])
    assert r["resolved_items"][0]["owner_fr"] == "FR-01.03" and r["ac_decisions"][0]["mode"] == "asked"      # asked and answered: not auto-assigned
    bad = _decided([{"kind": "add", "new_text": "Writes to shared/scripts/x.py"}], _CAT, mode="auto")
    assert bad["status"] == "invalid"                                                                            # the wording check is not a question: auto does not skip it


@pytest.mark.covers("FR-01.11/AC49")
def test_off_does_nothing_and_a_run_without_auto_still_asks():
    off = _decided([_ADD], _CAT, mode="off")
    assert off["status"] == "skipped" and "switched off" in off["note"] and "questions" not in off and "ac_decisions" not in off
    assert _decided([_ADD], _CAT, mode="ask", bind_id="b")["status"] == "ask"


# --- the checked model lines and the code's own alternatives --------------------------------------------------------

def _reply(**fields) -> dict:
    return su.propose("A draft is kept a year", {**_CAT, "fr_text": {}}, ".", transport=lambda m, t: json.dumps(fields), model="stub/model")


@pytest.mark.covers("FR-01.11/AC49")
def test_a_model_line_is_shown_only_when_code_finds_it_plain_and_short():
    ok = _reply(fr_id="FR-01.03", line="Keeping what the author wrote", title="Draft lifetime", sentence="Say how long a draft stays.")
    assert (ok["line"], ok["title"], ok["sentence"], ok["none"]) == ("Keeping what the author wrote", "Draft lifetime", "Say how long a draft stays.", False)
    long_line = _reply(fr_id="FR-01.03", line="one two three four five six seven eight nine ten eleven twelve thirteen")
    quoted = _reply(fr_id="FR-01.03", line='It says "keep" things', title="Uses `code` here", sentence="See [FR-01.03] for it.")
    assert long_line["line"] == "" and quoted["line"] == "" and quoted["title"] == "" and quoted["sentence"] == ""          # dropped, never repaired
    assert _reply(fr_id="FR-01.03", line=7, title=None)["line"] == ""
    none = _reply(fr_id=None, line="ignored when nothing fits")
    assert none["source"] == "model" and none["fr_id"] is None and none["none"] is True and none["line"] == ""


@pytest.mark.covers("FR-01.11/AC49")
def test_the_question_shows_the_name_a_checked_line_and_the_codes_alternatives_only_when_they_differ():
    sugg = _model("FR-01.04", line="Letting people see a draft")
    q = _decided([_ADD], _CAT, bind_id="b", suggest=lambda n, it: sugg)["questions"][0]
    assert 'Requirement FR-01.04: "Sharing drafts"\nIn plain words: Letting people see a draft\n' in q["question"]
    lines = q["question"].splitlines()
    assert any(ln.startswith("2 Add it to FR-01.03 instead: Saving drafts") for ln in lines)                      # the code's top choice differs from the model's pick
    assert q["options"]["2"] == {"choice": "yes", "text": "FR-01.03"} and lines[-1].endswith("need help.") and "create a new one" in lines[-2]
    same = _decided([_ADD], _CAT, bind_id="b", suggest=lambda n, it: _model("FR-01.03"))["questions"][0]
    assert "instead" not in same["question"] and "In plain words" not in same["question"]                    # they agree, and the model gave no line
    none = _decided([_ADD], _CAT, bind_id="b", suggest=lambda n, it: _NONE)["questions"][0]
    assert "New requirement: How long a draft is kept\nPurpose: Say how long an unused draft stays." in none["question"]
    assert none["options"]["1"] == {"choice": "new_fr", "text": "How long a draft is kept", "summary": "Say how long an unused draft stays."}
    assert "In plain words" not in none["question"] and none["question"].splitlines()[-1].endswith("need help.")


# --- the tool ---------------------------------------------------------------------------------------------------------

def _run(tmp_path, monkeypatch, capsys, *extra, env=None):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SHIPWRIGHT_AC_MODE", raising=False)
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    root = tmp_path / "repo"
    if not root.exists():
        root = _repo(tmp_path)
        (tmp_path / "ask.json").write_text(json.dumps({"items": [_ADD]}), encoding="utf-8")
    base = ["--project-root", str(root), "--from-json", str(tmp_path / "ask.json"), "--base-ref", "HEAD", "--run-id", "r1", "--no-suggest"]
    code = cli.main([*base, *extra])
    cap = capsys.readouterr()
    return code, (json.loads(cap.out) if cap.out.strip() else {}), cap.err, root


@pytest.mark.covers("FR-01.11/AC49")
def test_the_tool_defaults_to_auto_when_unattended_prints_the_list_and_an_explicit_ask_still_holds(tmp_path, monkeypatch, capsys):
    code, out, err, root = _run(tmp_path, monkeypatch, capsys, "--autonomous", "--sub-iterate-id", "Q1")
    assert code == 0 and out["status"] == "ok" and out["ac_mode"] == {"mode": "auto", "source": "default (unattended)"}
    assert out["ac_decisions"][0]["unconfirmed"] is True and "Assignments made without you" in err and out["unconfirmed_assignments"][1] in err
    code, out, err, _ = _run(tmp_path, monkeypatch, capsys, "--autonomous", "--sub-iterate-id", "Q1", "--ac-mode", "ask")
    assert code == 10 and out["status"] == "ask" and out["escalation"]["ac_questions"]                         # set ask explicitly: the unit holds as before
    code, out, _, _ = _run(tmp_path, monkeypatch, capsys, "--autonomous", "--sub-iterate-id", "Q1", env={"SHIPWRIGHT_AC_MODE": "ask"})
    assert code == 10
    code, out, err, _ = _run(tmp_path, monkeypatch, capsys)                                                    # interactive: ask
    assert code == 10 and out["ac_mode"]["mode"] == "ask" and "Assignments" not in err


@pytest.mark.covers("FR-01.11/AC49")
def test_the_tool_off_mode_does_nothing_and_a_bad_value_is_an_error(tmp_path, monkeypatch, capsys):
    code, out, _, root = _run(tmp_path, monkeypatch, capsys, "--ac-mode", "off")
    assert code == 0 and out["status"] == "skipped" and "ac_decisions" not in out and out["ac_mode"]["mode"] == "off"
    (root / "shipwright_iterate_config.json").write_text(json.dumps({"ac_decision": {"mode": "off"}}), encoding="utf-8")
    code, out, _, _ = _run(tmp_path, monkeypatch, capsys, "--autonomous")                                       # no unit id needed: nothing is held
    assert code == 0 and out["ac_mode"]["source"] == "shipwright_iterate_config.json"
    (root / "shipwright_iterate_config.json").write_text(json.dumps({"ac_decision": {"mode": "maybe"}}), encoding="utf-8")
    code, _, err, _ = _run(tmp_path, monkeypatch, capsys)
    assert code == 2 and "ask, auto, off" in err


@pytest.mark.covers("FR-01.11/AC49")
def test_an_auto_record_is_appended_and_f11_skips_when_the_decision_is_off(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD")
    r = _decided([_ADD], cat_of(_SPEC), mode="auto")
    ar.append_record(root, "iterate-2026-11-02-auto", r)                                                  # auto decisions are frozen like any other
    last = ar.read_records(root, "iterate-2026-11-02-auto")[-1]
    assert last["decisions"][0]["unconfirmed"] is True and last["decisions"][0]["mode"] == "auto-assigned"
    monkeypatch.setattr(chk, "_work_event", lambda rt, rid: {"source": "iterate"})
    monkeypatch.setattr(chk, "_branch_base_commit", lambda rt, c: base)
    monkeypatch.setenv("SHIPWRIGHT_AC_MODE", "off")
    res = chk.check_pre_build_ac_recorded(root, "iterate-2026-11-02-auto", base)
    assert res.ok and "Q1 off: mode=off (source=env)" in res.detail
