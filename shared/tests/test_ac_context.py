"""The Part line (the project's own words), the requirement text from the spec, and the "Don't understand, need help" answer."""

from __future__ import annotations

import json

import pytest

from shared.tests.ac_test_helpers import BASE_SPEC, ans, cat_of, git as _git, repo as _repo
from lib import ac_catalog as cat
from lib import ac_context as ctx
from lib import ac_decision as ad
from tools import ac_decision as cli

_ADD = {"kind": "add", "new_text": "A saved draft survives a restart"}
_TABLE = ("| ID | Area | Name | Priority | Description |\n|---|---|---|---|---|\n"
          "| FR-01.03 | Drafts | Saving drafts | Must | Keep every draft the author has saved, also after a restart. |\n"
          "| FR-01.04 | Adopted | Sharing drafts | Should | Let the author share a draft by link. |\n\n")
_SPEC = _TABLE + "### FR-01.03 - Saving drafts\n\n- (E) [AC05] Given a draft, when saved, then it is kept.\n\n### FR-01.04 - Sharing drafts\n\n- (E) [AC01] Given a link, when opened, then the draft shows.\n"


@pytest.mark.covers("FR-01.11/AC49")
def test_the_part_is_the_specs_own_grouping_then_the_top_level_directory_then_nothing():
    grouped = {"groups": {"FR-01.03": "Drafts", "FR-01.04": "Sharing"}}
    assert ctx.part_line(["FR-01.03", "FR-01.04"], grouped, ["plugins/x/y.py"]) == "Part: Drafts, Sharing"          # the spec's grouping wins over paths
    assert ctx.part_line(["FR-01.03"], {}, ["web/screens/a.tsx", "api/services/b.py", "README.md", "docs/x.md", "tests/t.py"]) == "Part: api, web"
    assert ctx.part_line([], {}, ["plugins/shipwright-build/a.py", "plugins\\shipwright-iterate\\b.py", "plugins/shipwright-build/c.py"]) == "Part: plugins/shipwright-build, plugins/shipwright-iterate"
    for unknown in (None, [], ["README.md"], ["docs/guide.md", "tests/t.py", ".github/ci.yml", "CHANGELOG-unreleased.d/feat/x.md"], [7, None], "plugins/x/y.py"):
        assert ctx.part_line(["FR-09.09"], {}, unknown) == ""                                                      # never invented: no line at all
    assert "plugin" not in ctx.part_line(["FR-01.03"], {}, ["web/a.tsx"]).lower()                                  # no hard-coded word


@pytest.mark.covers("FR-01.11/AC49")
def test_the_catalog_gives_the_exact_requirement_text_and_the_grouping_the_project_already_has(tmp_path):
    root = _repo(tmp_path, _SPEC)
    catalog = cat.load_catalog(root, _git(root, "rev-parse", "HEAD"))
    assert cat.fr_text("FR-01.03", catalog) == "Keep every draft the author has saved, also after a restart."
    assert catalog["groups"] == {"FR-01.03": "Drafts"}                                                           # "Adopted" names no part: left out
    assert cat.parse_fr_table(_SPEC)["FR-01.04"] == {"area": "Adopted", "description": "Let the author share a draft by link."}
    assert cat.fr_text("FR-01.03", cat_of(BASE_SPEC)) == "Saving drafts" and cat.fr_text("FR-09.09", cat_of(BASE_SPEC)) == ""   # no table: the heading title; unknown: nothing
    assert cat.parse_fr_table("| a | b |\n| FR-01.01 | x |\n") == {}                                              # no header row: nothing guessed
    split = _repo(tmp_path / "s", BASE_SPEC)
    named = split / ".shipwright" / "planning" / "02-web-ui"
    named.mkdir(parents=True)
    (named / "spec.md").write_text("### FR-02.01 - Screens\n\n- (E) [AC01] Given a user, when opened, then a screen shows.\n", encoding="utf-8")
    _git(split, "add", "-A")
    _git(split, "commit", "-qm", "split")
    assert cat.load_catalog(split, "HEAD")["groups"] == {"FR-02.01": "web-ui"}                                  # no Area column: the split's own name


@pytest.mark.covers("FR-01.11/AC49")
def test_the_question_carries_the_part_from_the_spec_or_the_paths():
    catalog = cat.parse_catalog(_SPEC)
    full = cat_of(_SPEC) | {"fr_text": {"FR-01.03": "Keep every draft the author has saved, also after a restart."}, "groups": {"FR-01.03": "Drafts"}}
    q = ad.decide([_ADD], full, paths=["web/a.tsx"])["questions"][0]["question"]
    assert "\nPart: Drafts\nNew acceptance criterion:" in q and 'Requirement FR-01.03: "Keep every draft the author has saved, also after a restart."' in q
    plain = ad.decide([_ADD], cat_of(_SPEC), paths=["web/a.tsx"])["questions"][0]["question"]
    assert "\nPart: web\n" in plain and catalog
    assert "Part:" not in ad.decide([_ADD], cat_of(_SPEC))["questions"][0]["question"]


@pytest.mark.covers("FR-01.11/AC49")
def test_dont_understand_asks_the_agent_to_explain_and_the_new_wording_is_asked_again():
    catalog = cat_of(BASE_SPEC)
    asked = []
    q = ad.decide([_ADD], catalog, bind_id="b")["questions"][0]
    assert q["question"].splitlines()[-1] == "4 Don't understand, need help." and q["options"]["4"] == {"choice": "explain"}
    reply = ad.decide([_ADD], catalog, bind_id="b", answers=[ans(q, "explain")], suggest=lambda n, it: asked.append(n))
    assert reply["status"] == "explain" and reply["explain"][0]["item"] == 0 and "everyday words" in reply["explain"][0]["message"] and not asked      # a resume never calls the model
    assert not reply.get("resolved_items")
    moved = cat_of(BASE_SPEC + "\n### FR-01.09 - Extra\n\n- (E) [AC01] Given x, when y, then z.\n")
    assert ad.decide([_ADD], moved, bind_id="b", answers=[ans(q, "explain")])["status"] == "explain"                  # the stored options still match on a moved catalog
    reworded = {**_ADD, "new_text": "A draft you saved is still there after you restart the app"}
    again = ad.decide([reworded], catalog, bind_id="b", answers=[ans(q, "explain")])
    assert again["status"] == "ask" and again["questions"][0]["question_sha256"] != q["question_sha256"]               # a new wording is a new question
    forged = ans(q, "explain")
    forged["options"] = {"1": {"choice": "explain"}}
    asked_again = ad.decide([_ADD], catalog, bind_id="b", answers=[forged])                                           # an agent-written option map is not the signed one: it settles nothing
    assert asked_again["status"] == "ask" and asked_again["questions"][0]["question_sha256"] == q["question_sha256"]


@pytest.mark.covers("FR-01.11/AC49")
def test_every_question_ends_with_the_help_option_and_the_numbers_run_in_order():
    catalog = cat_of(BASE_SPEC)
    old = catalog["acs"]["FR-01.03.AC05"]
    items = [{"kind": "change", "ac": "FR-01.03.AC05", "old_text": old, "new_text": "A draft is kept for a year"}, {"kind": "remove", "ac": "FR-01.03.AC05", "old_text": old},
             {"kind": "add", "new_fr": {"id": "FR-01.30", "title": "Offline use"}, "new_text": "The app works offline"}, _ADD, {"kind": "add", "new_text": "Orbits remain stable"}]
    for item, count in zip(items, (3, 3, 3, 4, 3)):
        q = ad.decide([item], catalog)["questions"][0]
        numbered = [ln for ln in q["question"].splitlines() if ln[:2] in {f"{n} " for n in range(1, 6)}]
        assert [ln[0] for ln in numbered] == [str(n) for n in range(1, count + 1)] and numbered[-1] == f"{count} Don't understand, need help."
        assert list(q["options"]) == [str(n) for n in range(1, count + 1)] and q["options"][str(count)] == {"choice": "explain"}
        assert q["question"].startswith("Shipwright keeps a list of requirements (FRs).") and "\n\nDoes this fit?\n" in q["question"]


@pytest.mark.covers("FR-01.11/AC49")
def test_the_decide_tool_exits_11_on_help_and_takes_an_option_number(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                                         # the worktree this suite runs in is a campaign unit: attended only from elsewhere
    root = _repo(tmp_path)
    ask = tmp_path / "ask.json"
    ask.write_text(json.dumps({"items": [_ADD]}), encoding="utf-8")
    base = ["--project-root", str(root), "--from-json", str(ask), "--base-ref", "HEAD", "--run-id", "r1", "--no-suggest"]
    out = tmp_path / "d.json"
    assert cli.main([*base, "--out", str(out)]) == 10
    answers = tmp_path / "a.json"
    assert cli.main(["answer", "--decided", str(out), "--item", "0", "--choice", "4", "--answers", str(answers)]) == 0
    assert cli.main([*base, "--answers", str(answers)]) == 11
    assert cli.main(["answer", "--decided", str(out), "--item", "0", "--choice", "explain", "--answers", str(answers)]) == 0
    assert cli.main(["answer", "--decided", str(out), "--item", "0", "--choice", "9", "--answers", str(answers)]) == 2             # not an option of this question
    assert cli.main(["answer", "--decided", str(out), "--item", "0", "--choice", "2", "--answers", str(answers)]) == 0
    assert cli.main([*base, "--answers", str(answers)]) == 2                                                                      # "No": the work goes back to the chat
