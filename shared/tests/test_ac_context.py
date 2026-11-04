"""The question's context: Affects, cross-cutting first option, the new wording, "I do not understand", the shown-only-if-different gloss, Already in the catalog."""

from __future__ import annotations

import json

import pytest

from shared.tests.ac_test_helpers import BASE_SPEC, ans, cat_of, repo as _repo
from lib import ac_context as ctx
from lib import ac_decision as ad
from lib import ac_gloss
from lib import ac_suggest as su
from tools import ac_decision as cli

_ADD = {"kind": "add", "new_text": "A saved draft survives a restart"}
_SPEC = ("### FR-01.03 - Saving drafts\n\n- (E) [AC05] Given a draft, when it is saved, then it is kept after a restart of the application.\n\n"
         "### FR-01.04 - Stack profile choice\n\n- (E) [AC01] Given a new project, when a stack profile is picked, then its defaults apply.\n\n"
         "### FR-01.05 - Billing\n\n- (E) [AC01] Given an invoice, when it is due, then it is sent.\n")
_TWO = ["plugins/shipwright-build/scripts/a.py", "plugins/shipwright-iterate/skills/x.md"]


@pytest.mark.covers("FR-01.11/AC49")
def test_affects_names_the_touched_plugins_in_plain_words_and_is_omitted_when_unknown():
    assert ctx.affects_line(_TWO) == "Affects: Build phase, Iterate."
    assert ctx.affects_line(["plugins\\shipwright-build\\x.py", "plugins/shipwright-build/y.py"]) == "Affects: Build phase."      # any slash style, each plugin once
    for unknown in ([], None, "plugins/shipwright-build/x.py", ["shared/scripts/x.py", "docs/guide.md"], ["plugins/shipwright-nope/x.py"],
                    [*_TWO, "plugins/shipwright-nope/x.py"], [7, None]):                                                              # nothing mapped, or one plugin without a plain name: no line at all
        assert ctx.affects_line(unknown) == ""
    assert ctx.is_cross_cutting(_TWO) and not ctx.is_cross_cutting(_TWO[:1]) and not ctx.is_cross_cutting(None)


@pytest.mark.covers("FR-01.11/AC49")
def test_a_change_across_two_plugins_or_with_no_owning_area_offers_its_own_requirement_first():
    catalog = cat_of(_SPEC)
    one = ad.decide([_ADD], catalog, paths=_TWO[:1])["questions"][0]
    assert "A Applies to several areas" not in one["question"] and one["options"]["A"] == {"choice": "yes", "text": "FR-01.03"}      # one plugin, a fitting area: only the area list
    two = ad.decide([_ADD], catalog, paths=_TWO)["questions"][0]
    lines = two["question"].splitlines()
    assert lines[1] == "Affects: Build phase, Iterate." and lines[2] == "Which requirement would this promise belong to?"
    assert lines[3] == "A Applies to several areas: make it its own requirement." and lines[4].startswith("B Saving drafts")
    assert two["options"]["A"] == {"choice": "cross_cutting"} and two["options"]["B"] == {"choice": "yes", "text": "FR-01.03"}
    other = ad.decide([{"kind": "add", "new_text": "Orbits remain stable", "files": _TWO[:1]}], catalog)["questions"][0]          # no fitting area at all
    assert other["options"]["A"] == {"choice": "cross_cutting"} and "Affects: Build phase." in other["question"]                      # declared files feed the line too


@pytest.mark.covers("FR-01.11/AC49")
def test_picking_its_own_requirement_mints_a_cross_cutting_requirement_in_the_record():
    catalog = cat_of(_SPEC)
    q = ad.decide([_ADD], catalog, bind_id="b", paths=_TWO)["questions"][0]
    done = ad.decide([_ADD], catalog, bind_id="b", paths=_TWO, answers=[ans(q, "cross_cutting")])
    assert done["status"] == "ok"
    item = done["resolved_items"][0]
    assert item["new_fr"] == {"id": "FR-01.06", "title": _ADD["new_text"], "cross_cutting": True} and item["owner_fr"] == "FR-01.06"
    assert done["ac_decisions"][0]["cross_cutting"] is True and done["ac_decisions"][0]["answer"] == "cross_cutting"
    assert ad.frozen_fields(item)["new_fr"]["cross_cutting"] is True
    named = ad.decide([_ADD], catalog, bind_id="b", paths=_TWO, answers=[ans(q, "cross_cutting", "Drafts survive restarts")])["resolved_items"][0]
    assert named["new_fr"]["title"] == "Drafts survive restarts"
    change = {"kind": "change", "ac": "FR-01.03.AC05", "old_text": _SPEC.split("[AC05] ")[1].split("\n")[0], "new_text": "A draft is kept for a year"}
    cq = ad.decide([change], catalog, bind_id="b")["questions"][0]
    assert "applies to several areas" in ad.decide([change], catalog, bind_id="b", answers=[ans(cq, "cross_cutting")])["errors"][0]


@pytest.mark.covers("FR-01.11/AC49")
def test_every_question_offers_i_do_not_understand_and_asks_which_requirement():
    catalog = cat_of(BASE_SPEC)
    old = catalog["acs"]["FR-01.03.AC05"]
    kinds = [{"kind": "change", "ac": "FR-01.03.AC05", "old_text": old, "new_text": "A draft is kept for a year"}, {"kind": "remove", "ac": "FR-01.03.AC05", "old_text": old},
             {"kind": "add", "new_fr": {"id": "FR-01.30", "title": "Offline use"}, "new_text": "The app works offline"}, _ADD]
    for item in kinds:
        q = ad.decide([item], catalog)["questions"][0]
        assert "I do not understand this, please explain." in q["question"]
        assert "Where does it belong" not in q["question"]
    assert "Which requirement would this promise belong to?" in q["question"] and {"choice": "explain"} in q["options"].values()


@pytest.mark.covers("FR-01.11/AC49")
def test_i_do_not_understand_asks_the_agent_to_reword_and_the_new_wording_is_asked_again():
    catalog = cat_of(BASE_SPEC)
    asked = []
    q = ad.decide([_ADD], catalog, bind_id="b")["questions"][0]
    reply = ad.decide([_ADD], catalog, bind_id="b", answers=[ans(q, "explain")], suggest=lambda n, it: asked.append(n))
    assert reply["status"] == "explain" and reply["explain"][0]["item"] == 0 and "plainer words" in reply["explain"][0]["message"] and not asked      # a resume never calls the model
    assert not reply.get("resolved_items")
    moved = cat_of(BASE_SPEC + "\n### FR-01.09 - Extra\n\n- (E) [AC01] Given x, when y, then z.\n")
    assert ad.decide([_ADD], moved, bind_id="b", answers=[ans(q, "explain")])["status"] == "explain"                  # the stored options still match on a moved catalog
    reworded = {**_ADD, "new_text": "A draft you saved is still there after you restart the app"}
    again = ad.decide([reworded], catalog, bind_id="b", answers=[ans(q, "explain")])
    assert again["status"] == "ask" and again["questions"][0]["question_sha256"] != q["question_sha256"]               # a new wording is a new question
    forged = ans(q, "explain")
    forged["options"] = {"A": {"choice": "explain"}}
    asked_again = ad.decide([_ADD], catalog, bind_id="b", answers=[forged])                                           # an agent-written option map is not the signed one: it settles nothing
    assert asked_again["status"] == "ask" and asked_again["questions"][0]["question_sha256"] == q["question_sha256"]


@pytest.mark.covers("FR-01.11/AC49")
def test_the_decide_tool_exits_11_on_explain_and_accepts_the_letter(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                                         # the worktree this suite runs in is a campaign unit: attended only from elsewhere
    root = _repo(tmp_path)
    ask = tmp_path / "ask.json"
    ask.write_text(json.dumps({"items": [_ADD]}), encoding="utf-8")
    base = ["--project-root", str(root), "--from-json", str(ask), "--base-ref", "HEAD", "--run-id", "r1", "--no-suggest"]
    out = tmp_path / "d.json"
    assert cli.main([*base, "--out", str(out)]) == 10
    q = json.loads(out.read_text(encoding="utf-8"))["questions"][0]
    letter = next(k for k, v in q["options"].items() if v == {"choice": "explain"})
    answers = tmp_path / "a.json"
    assert cli.main(["answer", "--decided", str(out), "--item", "0", "--choice", letter, "--answers", str(answers)]) == 0
    assert cli.main([*base, "--answers", str(answers)]) == 11
    assert cli.main(["answer", "--decided", str(out), "--item", "0", "--choice", "explain", "--answers", str(answers)]) == 0


@pytest.mark.covers("FR-01.11/AC49")
def test_the_plain_wording_is_shown_only_when_it_differs_meaningfully():
    original = "A draft that is older than 30 days is deleted unless the owner keeps it"
    assert not ctx.differs(original, original) and not ctx.differs(original, original + ".")
    assert not ctx.differs(original, "A draft that is older than 30 days is removed unless the owner keeps it")                  # one word swapped
    assert ctx.differs(original, "A draft that is 30 days old or older is removed, unless the owner keeps it.")
    assert not ctx.differs("", "")
    item = {"kind": "add", "new_text": original}
    same = {"source": "model", "plain_promise": original + ".", "areas": [], "original_promise": original}
    assert "In plain words" not in ad.render_question(item, cat_of(_SPEC), same)
    rewritten = {**same, "plain_promise": "After 30 days a draft that nobody has chosen to keep is removed for good."}
    q = ad.render_question(item, cat_of(_SPEC), rewritten)
    assert q.splitlines()[0] == f"This change adds a new promise: {original}." and q.splitlines()[1].startswith("In plain words: After 30 days")
    jargon = {"kind": "add", "new_text": "A stack profile is chosen before a commit"}                                          # no gloss shown: the glossary explains the jargon instead
    text = ad.render_question(jargon, cat_of(_SPEC), {**same, "plain_promise": "A stack profile is chosen before a commit."})
    assert "In plain words" not in text and "stack profile: the ready-made set of technology choices" in text


@pytest.mark.covers("FR-01.11/AC49")
def test_the_catalog_lines_list_requirements_with_the_same_key_phrase_and_are_omitted_when_none():
    catalog = cat_of(_SPEC)
    assert ctx.related_titles("A new stack profile is picked for every project", catalog) == ["Stack profile choice"]
    assert ctx.related_titles("Orbits remain stable", catalog) == [] and ctx.related_titles("", catalog) == [] and ctx.related_titles("the and of", catalog) == []
    crowded = cat_of("".join(f"### FR-01.{i:02d} - Area {i}\n\n- (E) [AC01] Given x, when the operator sees the board, then y.\n\n" for i in range(1, 7)))
    assert ctx.related_titles("The operator sees the board", crowded) == []                                                      # a phrase every area has says nothing about one
    q = ad.render_question({"kind": "add", "new_text": "A new stack profile is picked for every project"}, catalog, None)
    assert "\nAlready in the catalog: Stack profile choice.\n" in q
    assert "Already in the catalog" not in ad.render_question(_ADD, catalog, None)
    assert "Already in the catalog" not in ad.render_question({"kind": "change", "old_text": "a", "new_text": "b"}, catalog, None)       # only a new promise has a likely twin


@pytest.mark.covers("FR-01.11/AC49")
def test_the_glossary_explains_claude_review_outside_reviewers_and_command_and_the_prompt_demands_explained_jargon():
    terms = ac_gloss.load_glossary()
    for term in ("claude review", "outside reviewers", "command"):
        assert term in terms and len(terms[term]) > 20
    text = "The Claude review and the outside reviewers run before the command is typed"
    assert ac_gloss.jargon_terms(text) == ["claude review", "outside reviewers", "command"]
    prompt = su.prompt_text()
    for word in ("reviewer", "stack profile", "command", "merged", "deployment", "coordinator"):
        assert f'"{word}"' in prompt
    assert "EXPLAINED" in prompt and len(prompt.splitlines()) <= 400
