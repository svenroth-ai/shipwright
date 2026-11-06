"""The proposal inside the decide flow: when the model is asked at all, and the tool end to end (stubbed transport)."""

from __future__ import annotations

import json

import pytest

from shared.tests.ac_test_helpers import repo as _repo
from lib import ac_decision as ad
from lib import ac_hold
from lib import ac_suggest as su
from tools import ac_decision as cli

_PROMISE = "A draft that is older than 30 days is deleted unless the owner keeps it"
_CAT = {"acs": {"FR-01.03.AC01": "Given a draft, when saved, then it is kept."}, "frs": {"FR-01.03", "FR-01.04"},
        "titles": {"FR-01.03": "Saving drafts", "FR-01.04": "Sharing drafts"}, "unparsed": False}


@pytest.mark.covers("FR-01.11/AC49")
def test_decide_asks_the_suggester_only_for_a_question_it_renders_and_never_for_an_invalid_or_auto_item():
    asked = []

    def suggester(n, item):
        asked.append(n)
        return None
    items = [{"kind": "add", "owner_fr": "FR-01.03", "new_text": "A draft is kept"},                  # one owner: decided alone, no question
             {"kind": "add", "new_text": "Writes to shared/scripts/x.py"},                            # fails the wording check
             {"kind": "add", "new_text": _PROMISE}]                                                   # the only question
    r = ad.decide(items, _CAT, suggest=suggester)
    assert r["status"] == "invalid" and asked == [2]                                                    # never for the auto item (0) or the one that fails the wording check (1)
    asked.clear()
    r = ad.decide([items[0], items[2]], _CAT, suggest=suggester)
    assert r["status"] == "ask" and asked == [1]


def _tool_repo(tmp_path):
    root = _repo(tmp_path)
    ask = tmp_path / "ask.json"
    ask.write_text(json.dumps({"items": [{"kind": "add", "new_text": _PROMISE}]}), encoding="utf-8")
    return root, ask


@pytest.mark.covers("FR-01.11/AC49")
def test_the_decide_tool_uses_the_proposal_records_it_and_the_flags_and_nonce_work(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    root, ask = _tool_repo(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    sent = []
    monkeypatch.setattr(su, "default_transport", lambda: (lambda m, t: sent.append(1) or json.dumps({"fr_id": "FR-01.04"})))
    base = ["--project-root", str(root), "--from-json", str(ask), "--base-ref", "HEAD", "--run-id", "r1"]
    out = tmp_path / "decided.json"
    assert cli.main([*base, "--out", str(out)]) == 10
    q = json.loads(out.read_text(encoding="utf-8"))["questions"][0]
    assert q["suggestion_source"] == "model" and 'Requirement FR-01.04: "Sharing drafts"' in q["question"] and q["options"]["1"] == {"choice": "yes", "text": "FR-01.04"}
    answers = tmp_path / "a.json"
    assert cli.main(["answer", "--decided", str(out), "--item", "0", "--choice", "1", "--answers", str(answers)]) == 0           # the option NUMBER
    entry = json.loads(answers.read_text(encoding="utf-8"))["answers"][0]
    assert entry["suggestion_source"] == "model" and entry["options"] == q["options"] and ac_hold.signature_ok(ac_hold.load_key(), entry)
    before = len(sent)
    assert cli.main([*base, "--answers", str(answers), "--out", str(out)]) == 0                       # resume: the signed answer matches, the model is not asked again
    done = json.loads(out.read_text(encoding="utf-8"))
    assert len(sent) == before and done["ac_decisions"][0]["answered_via"] == "operator" and done["ac_decisions"][0]["suggestion_fr_id"] == "FR-01.04"
    assert done["counts"]["asked"] == 1 and done["resolved_items"][0]["new_text"] == _PROMISE and done["resolved_items"][0]["owner_fr"] == "FR-01.04"
    assert cli.main([*base, "--answers", str(answers), "--nonce", "2026-11-02T10:00:00Z"]) == 2         # another campaign nonce: the old answer does not carry over
    assert "different question" in capsys.readouterr().out
    plain = tmp_path / "plain.json"
    assert cli.main([*base, "--no-suggest", "--out", str(plain)]) == 10
    q2 = json.loads(plain.read_text(encoding="utf-8"))["questions"][0]
    assert "suggestion_source" not in q2 and 'Requirement FR-01.03: "Saving drafts"' in q2["question"]      # no model: the best match by shared words
    assert cli.main(["answer", "--decided", str(plain), "--item", "0", "--choice", "7", "--answers", str(answers)]) == 2   # not an option number of that question
