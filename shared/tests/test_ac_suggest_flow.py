"""The suggestion inside the decide flow: opt-outs that fail closed, the shared time budget, when the model is asked at all, and the tool (stubbed transport)."""

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
_GOOD = {"plain_promise": "A draft that is 30 days old or older is removed, unless the owner keeps it.", "areas": [{"fr_id": "FR-01.03", "plain_description": "How drafts are kept."}]}


@pytest.mark.covers("FR-01.11/AC49")
def test_every_opt_out_sends_nothing_and_an_unreadable_config_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    sent = []
    monkeypatch.setattr(su, "default_transport", lambda: (lambda m, t: sent.append(1) or json.dumps(_GOOD)))
    assert su.suggest(_PROMISE, _CAT, tmp_path, use_cache=False)["source"] == "model" and sent == [1]      # nothing configured: it is sent
    for value in ("0", "false", "OFF", "no"):
        monkeypatch.setenv(su.OFF_ENV, value)
        assert su._opted_out(tmp_path) is True
    monkeypatch.delenv(su.OFF_ENV)
    cfg = tmp_path / "shipwright_iterate_config.json"
    for body in ({"external_review": {"ac_suggest": False}}, {"external_review": {"feedback_iterations": 0}}):
        cfg.write_text(json.dumps(body), encoding="utf-8")
        out = su.suggest(_PROMISE, _CAT, tmp_path, use_cache=False)
        assert out["source"] == "fallback" and "switched off" in out["reason"]
    assert sent == [1]                                                                                   # no second send
    cfg.write_text(json.dumps({"external_review": {"ac_suggest": True}}), encoding="utf-8")
    assert su._opted_out(tmp_path) is False
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gateway.example")
    assert su._opted_out(tmp_path) is True
    monkeypatch.delenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL")
    import lib.external_review_config as erc
    monkeypatch.setattr(erc, "load_review_config", lambda **k: (_ for _ in ()).throw(ValueError("corrupt config")))
    assert su._opted_out(tmp_path) is True                                                               # any exception while reading the config: no send
    out = su.suggest(_PROMISE, _CAT, tmp_path, use_cache=False)
    assert out["source"] == "fallback" and sent == [1]


@pytest.mark.covers("FR-01.11/AC49")
def test_the_suggester_has_one_time_budget_and_skips_what_is_not_a_where_does_it_belong_question(monkeypatch):
    now = [0.0]
    item = {"kind": "add", "new_text": _PROMISE}
    s = su.make_suggester(_CAT, ".", budget=30, clock=lambda: now[0])
    assert s(0, {"kind": "change", "new_text": _PROMISE}) is None and s(0, {"kind": "add", "new_text": _PROMISE, "new_fr": {"id": "FR-01.30", "title": "x"}}) is None
    assert s(0, {"kind": "add", "new_text": ""}) is None and su.make_suggester({**_CAT, "titles": {}}, ".")(0, item) is None       # no area titles: nothing to suggest
    assert su.make_suggester({**_CAT, "unparsed": True}, ".")(0, item) is None and su.make_suggester(_CAT, ".", enabled=False)(0, item) is None
    seen = []
    monkeypatch.setattr(su, "suggest", lambda text, cat, root, **k: seen.append(k["timeout"]) or {"source": "fallback", "original_promise": text})
    assert s(0, item)["source"] == "fallback" and seen == [30]
    now[0] = 20.0
    s(1, item)
    assert seen[-1] == 10                                                                              # what is left of the shared 30 s
    now[0] = 29.0
    out = s(2, item)
    assert "time budget" in out["reason"] and len(seen) == 2                                           # used up: fall back, no call


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
def test_the_decide_tool_uses_the_suggestion_records_it_and_the_flags_and_nonce_work(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    root, ask = _tool_repo(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    sent = []
    monkeypatch.setattr(su, "default_transport", lambda: (lambda m, t: sent.append(1) or json.dumps(_GOOD)))
    base = ["--project-root", str(root), "--from-json", str(ask), "--base-ref", "HEAD", "--run-id", "r1"]
    out = tmp_path / "decided.json"
    assert cli.main([*base, "--out", str(out)]) == 10
    q = json.loads(out.read_text(encoding="utf-8"))["questions"][0]
    assert q["suggestion_source"] == "model" and f"{_PROMISE}.\nIn plain words: A draft that is 30 days old" in q["question"]
    answers = tmp_path / "a.json"
    assert cli.main(["answer", "--decided", str(out), "--item", "0", "--choice", "A", "--answers", str(answers)]) == 0
    entry = json.loads(answers.read_text(encoding="utf-8"))["answers"][0]
    assert entry["suggestion_source"] == "model" and entry["options"] == q["options"] and ac_hold.signature_ok(ac_hold.load_key(), entry)
    before = len(sent)
    assert cli.main([*base, "--answers", str(answers), "--out", str(out)]) == 0                       # resume: the signed answer matches, the model is not asked again
    done = json.loads(out.read_text(encoding="utf-8"))
    assert len(sent) == before and done["ac_decisions"][0]["answered_via"] == "operator" and done["ac_decisions"][0]["suggestion_source"] == "model"
    assert done["counts"]["asked"] == 1 and done["resolved_items"][0]["new_text"] == _PROMISE
    assert cli.main([*base, "--answers", str(answers), "--nonce", "2026-11-02T10:00:00Z"]) == 2         # another campaign nonce: the old answer does not carry over
    assert "different question" in capsys.readouterr().out
    plain = tmp_path / "plain.json"
    assert cli.main([*base, "--no-suggest", "--out", str(plain)]) == 10
    q2 = json.loads(plain.read_text(encoding="utf-8"))["questions"][0]
    assert "suggestion_source" not in q2 and "In plain words" not in q2["question"]
