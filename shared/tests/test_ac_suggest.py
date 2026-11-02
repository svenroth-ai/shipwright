"""The model's plain wording and area suggestions: a validated display aid with a deterministic fallback (stubbed transport, never the live provider)."""

from __future__ import annotations

import json

import pytest

from lib import ac_decision as ad
from lib import ac_suggest as su
from tools import ac_decision as cli

_PROMISE = "A draft that is older than 30 days is deleted unless the owner keeps it"
_CAT = {"acs": {"FR-01.03.AC01": "Given a draft, when saved, then it is kept.", "FR-01.04.AC01": "Given a link, when opened, then the draft shows."},
        "frs": {"FR-01.03", "FR-01.04"}, "titles": {"FR-01.03": "Saving drafts", "FR-01.04": "Sharing drafts"}, "unparsed": False}
_GOOD = {"plain_promise": "A draft untouched for more than 30 days is removed, unless the owner keeps it.",
         "areas": [{"fr_id": "FR-01.03", "plain_description": "How drafts are saved and kept."}]}


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv(su.CACHE_ENV, str(tmp_path / "cache.json"))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", raising=False)


def _run(reply, **kw):
    calls = []

    def transport(messages, timeout):
        calls.append(messages)
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply)
    out = su.suggest(_PROMISE, _CAT, ".", transport=transport, model="stub/model", **kw)
    return out, calls


@pytest.mark.covers("FR-01.11/AC49")
def test_a_good_reply_is_used_and_the_record_keeps_both_wordings_the_model_and_the_prompt_sha():
    out, calls = _run(_GOOD)
    assert out["source"] == "model" and out["model"] == "stub/model" and out["prompt_sha"].startswith("sha256:")
    assert out["original_promise"] == _PROMISE and out["plain_promise"].startswith("A draft untouched")
    assert json.loads(calls[0][1]["content"])["promise"] == _PROMISE  # the model sees the original, plus the areas
    q = ad.render_question({"kind": "add", "new_text": _PROMISE}, _CAT, out)
    assert "A draft untouched for more than 30 days" in q and "A Saving drafts: How drafts are saved and kept." in q and "FR-01" not in q
    opts = ad.question_options({"kind": "add", "new_text": _PROMISE}, _CAT, out)
    assert opts["A"] == {"choice": "yes", "text": "FR-01.03"}  # the id stays in the machine answer only
    meta = ad._suggestion_meta(out)
    assert meta["suggestion_source"] == "model" and meta["suggestion_original_promise"] == _PROMISE and meta["suggestion_model"] == "stub/model" and "suggestion_prompt_sha" in meta


@pytest.mark.parametrize("reply, why", [
    ({**_GOOD, "areas": [{"fr_id": "FR-99.99", "plain_description": "Invented."}]}, "unknown area id"),
    ({**_GOOD, "plain_promise": "A draft untouched for a long time is removed, unless the owner keeps it."}, "30"),
    ({**_GOOD, "plain_promise": "A draft untouched for more than 30 days is removed whenever the owner agrees."}, "unless"),
    ({**_GOOD, "plain_promise": "A draft untouched for more than 30 days is removed unless the owner keeps it; see plan_review.py."}, "code-shaped"),
    ({**_GOOD, "areas": [{"fr_id": "FR-01.03", "plain_description": "One."}, {"fr_id": "FR-01.03", "plain_description": "Two."}]}, "twice"),
    ({**_GOOD, "areas": [{"fr_id": "FR-01.03", "plain_description": "x"}] * 1 + [{"fr_id": f"FR-01.0{i}", "plain_description": "y"} for i in (4, 5, 6)]}, "more than 3"),
    ({**_GOOD, "areas": []}, "no area"),
    ({**_GOOD, "plain_promise": "x" * 500}, "too long"),
    ("this is not json", "not a JSON object"),
    ("[1, 2]", "not a JSON object"),
])
@pytest.mark.covers("FR-01.11/AC49")
def test_every_rejected_reply_falls_back_with_its_reason(reply, why):
    out, _ = _run(reply)
    assert out["source"] == "fallback" and why in out["reason"]
    assert "plain_promise" not in out
    q = ad.render_question({"kind": "add", "new_text": _PROMISE}, _CAT, out)
    assert q.startswith(f"This change adds a new promise: {_PROMISE}")  # today's deterministic wording
    assert ad._suggestion_meta(out)["suggestion_source"] == "fallback"


@pytest.mark.covers("FR-01.11/AC49")
def test_a_timeout_a_missing_key_and_an_opt_out_fall_back_and_never_raise(monkeypatch, tmp_path):
    out, _ = _run(TimeoutError("read timed out"))
    assert out["source"] == "fallback" and "TimeoutError" in out["reason"]
    no_key = su.suggest(_PROMISE, _CAT, tmp_path, use_cache=False)
    assert no_key["source"] == "fallback" and "OPENROUTER_API_KEY" in no_key["reason"]
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    (tmp_path / "shipwright_iterate_config.json").write_text(json.dumps({"external_review": {"feedback_iterations": 0}}), encoding="utf-8")
    off = su.suggest(_PROMISE, _CAT, tmp_path, use_cache=False)
    assert off["source"] == "fallback" and "switched off" in off["reason"]


@pytest.mark.covers("FR-01.11/AC49")
def test_the_same_inputs_give_the_same_question_from_the_cache_so_an_answer_stays_bound():
    first, calls1 = _run(_GOOD)
    again, calls2 = _run({"plain_promise": "Something else.", "areas": []})
    assert calls1 and not calls2 and again["plain_promise"] == first["plain_promise"]  # the stored suggestion, no second call
    fresh, calls3 = _run({"plain_promise": "A draft untouched for more than 30 days is removed, unless the owner keeps it, always.", "areas": _GOOD["areas"]}, use_cache=False)
    assert calls3 and fresh["plain_promise"] != first["plain_promise"]


@pytest.mark.covers("FR-01.11/AC49")
def test_the_model_text_never_changes_what_is_frozen_and_a_picked_letter_resolves_to_the_catalog_area():
    sugg = su.suggest(_PROMISE, _CAT, ".", transport=lambda m, t: json.dumps(_GOOD), model="stub/model")
    items = [{"kind": "add", "new_text": _PROMISE}]
    first = ad.decide(items, _CAT, bind_id="b", suggestions={0: sugg})
    assert first["status"] == "ask" and first["questions"][0]["suggestion_source"] == "model"
    q = first["questions"][0]
    from lib.ac_hold import question_sha, sign
    ans = {"item": 0, "question_sha256": q["question_sha256"], "choice": "yes", "text": q["options"]["A"]["text"]}
    done = ad.decide(items, _CAT, answers=[ans], bind_id="b", suggestions={0: sugg})
    assert done["status"] == "ok" and done["resolved_items"][0]["new_text"] == _PROMISE and done["resolved_items"][0]["owner_fr"] == "FR-01.03"
    assert done["ac_decisions"][0]["suggestion_source"] == "model" and done["ac_decisions"][0]["suggestion_plain_promise"] == _GOOD["plain_promise"]
    assert q["question_sha256"] == question_sha(q["question"], "b", 0) and sign  # the sha binds the text the operator saw


@pytest.mark.covers("FR-01.11/AC49")
def test_suggestions_are_requested_only_for_an_add_that_will_be_asked_where_it_belongs(monkeypatch):
    seen = []
    monkeypatch.setattr(su, "suggest", lambda text, *a, **k: seen.append(text) or {"source": "fallback"})
    items = [{"kind": "add", "new_text": "A first promise."}, {"kind": "add", "owner_fr": "FR-01.03", "new_text": "Owned."},
             {"kind": "change", "ac": "FR-01.03.AC01", "new_text": "Changed."}, {"kind": "add", "new_fr": {"id": "FR-01.30", "title": "New"}, "new_text": "New area."},
             {"kind": "add", "new_text": "See plan_review.py"}]
    assert list(su.suggestions_for(items, _CAT, ".")) == [0] and seen == ["A first promise."]
    assert su.suggestions_for(items, _CAT, ".", enabled=False) == {} and su.suggestions_for(items, {**_CAT, "unparsed": True}, ".") == {}


@pytest.mark.covers("FR-01.11/AC49")
def test_the_prompt_file_carries_the_required_rules():
    text = su.prompt_text()
    for must in ("tech-savvy", "NOT a developer", "MEANING, not by shared words", "Never invent", "empty list", "nothing but the JSON", "Keep EVERY number",
                 "not\", \"never\", \"unless\", \"only\", \"at most\", \"at least\" and \"no\""):
        assert must in text, must


@pytest.mark.covers("FR-01.11/AC49")
def test_the_decide_tool_passes_the_suggestion_through_and_the_flag_turns_it_off(tmp_path, monkeypatch, capsys):
    import subprocess
    root = tmp_path / "r"
    (root / ".shipwright/planning/01-adopted").mkdir(parents=True)
    (root / ".shipwright/planning/01-adopted/spec.md").write_text("### FR-01.03 - Saving drafts\n\n- (E) [AC05] Given a draft, when saved, then it is kept.\n", encoding="utf-8")
    for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    ask = tmp_path / "ask.json"
    ask.write_text(json.dumps({"items": [{"kind": "add", "new_text": _PROMISE}]}), encoding="utf-8")
    monkeypatch.setattr(su, "default_transport", lambda: (lambda m, t: json.dumps({**_GOOD})))
    monkeypatch.setattr(su, "model_id", lambda: "stub/model")
    monkeypatch.setattr(su, "_opted_out", lambda root: False)
    code = cli.main(["--project-root", str(root), "--from-json", str(ask), "--base-ref", "HEAD", "--run-id", "r1"])
    out = json.loads(capsys.readouterr().out)
    assert code == 10 and out["questions"][0]["suggestion_source"] == "model" and "untouched for more than 30 days" in out["questions"][0]["question"]
    cli.main(["--project-root", str(root), "--from-json", str(ask), "--base-ref", "HEAD", "--run-id", "r1", "--no-suggest"])
    out = json.loads(capsys.readouterr().out)
    assert "suggestion_source" not in out["questions"][0]  # no model call, no suggestion recorded
    assert _PROMISE in out["questions"][0]["question"]
