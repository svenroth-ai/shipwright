"""The model's only job - proposing ONE requirement for a new acceptance criterion: validation, the pin, the transport, every opt-out, the budget (stubbed, never the live provider)."""

from __future__ import annotations

import json
import sys

import pytest

from lib import ac_suggest as su

_PROMISE = "A draft that is older than 30 days is deleted unless the owner keeps it"
_CAT = {"acs": {"FR-01.03.AC01": "Given a draft, when saved, then it is kept.", "FR-01.04.AC01": "Given a link, when opened, then the draft shows."},
        "frs": {"FR-01.03", "FR-01.04"}, "titles": {"FR-01.03": "Saving drafts", "FR-01.04": "Sharing drafts"}, "fr_text": {"FR-01.03": "Keep every saved draft."}, "unparsed": False}


def _run(reply, promise=_PROMISE, **kw):
    calls = []

    def transport(messages, timeout):
        calls.append(messages)
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply)
    return su.propose(promise, _CAT, ".", transport=transport, model=kw.pop("model", "stub/model"), **kw), calls


@pytest.mark.covers("FR-01.11/AC49")
def test_a_reply_naming_a_real_requirement_is_used_and_the_request_carries_the_text_as_data():
    out, calls = _run({"fr_id": "FR-01.04"})
    assert out["source"] == "model" and out["fr_id"] == "FR-01.04" and out["model"] == "stub/model" and out["prompt_sha"].startswith("sha256:")
    payload = json.loads(calls[0][1]["content"])
    assert payload["acceptance_criterion"] == _PROMISE and {r["fr_id"] for r in payload["requirements"]} == {"FR-01.03", "FR-01.04"}
    assert {"fr_id": "FR-01.03", "title": "Saving drafts"} in payload["requirements"]                  # the id and the title are all that is sent about a requirement
    assert set(payload) == {"acceptance_criterion", "requirements"} and all(set(r) == {"fr_id", "title"} for r in payload["requirements"])
    assert "Keep every saved draft" not in calls[0][1]["content"] and "when saved, then it is kept" not in calls[0][1]["content"]   # no requirement text, no criteria
    prompt = su.prompt_text()
    assert "DATA" in prompt and len(prompt.splitlines()) <= 40 and "gloss" not in prompt.lower()          # the prompt is short and asks for one id only


@pytest.mark.covers("FR-01.11/AC49")
@pytest.mark.parametrize("reply, why", [
    ({"fr_id": "FR-99.99"}, "unknown requirement id"), ({"fr_id": 7}, "unknown requirement id"), ({}, "no fr_id"),
    ("this is not json", "not a JSON object"), ("[1, 2]", "not a JSON object"), ("", "not a JSON object"), ("null", "not a JSON object"),
])
def test_a_reply_that_names_no_real_requirement_falls_back_with_its_reason(reply, why):
    out, _ = _run(reply)
    assert out["source"] == "fallback" and out["fr_id"] is None and why in out["reason"]


@pytest.mark.covers("FR-01.11/AC49")
def test_the_model_is_pinned_and_a_model_that_needs_a_zero_retention_rule_is_refused(monkeypatch):
    assert su.MODEL == "anthropic/claude-haiku-5.5"
    for model in ("deepseek/deepseek-v4-pro", "z-ai/glm-5.3", "Z-AI/GLM-5.3"):
        out, calls = _run({"fr_id": "FR-01.03"}, model=model)
        assert out["source"] == "fallback" and "zero-data-retention" in out["reason"] and calls == []
    seen = []
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(su._load_transport(), "call_openrouter", lambda key, model, messages, timeout: seen.append(model) or json.dumps({"fr_id": "FR-01.03"}))
    monkeypatch.setattr(su, "_opted_out", lambda root: False)
    assert su.propose(_PROMISE, _CAT, ".")["fr_id"] == "FR-01.03" and seen == [su.MODEL]                    # not the PR review's default
    monkeypatch.setattr(su, "MODEL", "z-ai/glm-5.3")
    assert "zero-data-retention" in su.propose(_PROMISE, _CAT, ".")["reason"] and seen == ["anthropic/claude-haiku-5.5"]


@pytest.mark.covers("FR-01.11/AC49")
def test_the_transport_module_is_loaded_once_registered_before_it_runs_and_a_missing_file_is_a_fallback(monkeypatch, tmp_path):
    first = su._load_transport()
    assert su._load_transport() is first and sys.modules[su._TRANSPORT_NAME] is first
    monkeypatch.delitem(sys.modules, su._TRANSPORT_NAME)
    monkeypatch.setattr(su, "_TRANSPORT_PATH", tmp_path / "gone.py")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(su, "_opted_out", lambda root: False)
    out = su.propose(_PROMISE, _CAT, ".")
    assert out["source"] == "fallback" and "FileNotFoundError" in out["reason"] and su._TRANSPORT_NAME not in sys.modules
    (tmp_path / "boom.py").write_text("raise RuntimeError('import failed')\n", encoding="utf-8")
    monkeypatch.setattr(su, "_TRANSPORT_PATH", tmp_path / "boom.py")
    assert "import failed" in su.propose(_PROMISE, _CAT, ".")["reason"] and su._TRANSPORT_NAME not in sys.modules      # a failed import leaves nothing registered


@pytest.mark.covers("FR-01.11/AC49")
def test_a_timeout_and_a_missing_key_fall_back_and_never_raise(monkeypatch):
    out, _ = _run(TimeoutError("read timed out"))
    assert out["source"] == "fallback" and "TimeoutError" in out["reason"]
    monkeypatch.setattr(su, "_opted_out", lambda root: False)
    no_key = su.propose(_PROMISE, _CAT, ".")
    assert no_key["source"] == "fallback" and "OPENROUTER_API_KEY" in no_key["reason"]


@pytest.mark.covers("FR-01.11/AC49")
def test_every_opt_out_sends_nothing_and_an_unreadable_config_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    sent = []
    monkeypatch.setattr(su, "default_transport", lambda: (lambda m, t: sent.append(1) or json.dumps({"fr_id": "FR-01.03"})))
    assert su.propose(_PROMISE, _CAT, tmp_path)["source"] == "model" and sent == [1]                         # nothing configured: it is sent
    for value in ("0", "false", "OFF", "no"):
        monkeypatch.setenv(su.OFF_ENV, value)
        assert su._opted_out(tmp_path) is True
    monkeypatch.delenv(su.OFF_ENV)
    cfg = tmp_path / "shipwright_iterate_config.json"
    for body in ({"external_review": {"ac_suggest": False}}, {"external_review": {"feedback_iterations": 0}}):
        cfg.write_text(json.dumps(body), encoding="utf-8")
        out = su.propose(_PROMISE, _CAT, tmp_path)
        assert out["source"] == "fallback" and "switched off" in out["reason"]
    assert sent == [1]                                                                                       # no second send
    cfg.write_text(json.dumps({"external_review": {"ac_suggest": True}}), encoding="utf-8")
    assert su._opted_out(tmp_path) is False
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gateway.example")
    assert su._opted_out(tmp_path) is True
    monkeypatch.delenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL")
    import lib.external_review_config as erc
    monkeypatch.setattr(erc, "load_review_config", lambda **k: (_ for _ in ()).throw(ValueError("corrupt config")))
    assert su._opted_out(tmp_path) is True                                                                   # any exception while reading the config: no send
    assert su.propose(_PROMISE, _CAT, tmp_path)["source"] == "fallback" and sent == [1]


@pytest.mark.covers("FR-01.11/AC49")
def test_the_suggester_has_one_time_budget_and_skips_what_is_not_a_new_ac_without_an_owner(monkeypatch):
    now = [0.0]
    item = {"kind": "add", "new_text": _PROMISE}
    s = su.make_suggester(_CAT, ".", budget=30, clock=lambda: now[0])
    assert s(0, {"kind": "change", "new_text": _PROMISE}) is None and s(0, {"kind": "add", "new_text": _PROMISE, "new_fr": {"id": "FR-01.30", "title": "x"}}) is None
    assert s(0, {"kind": "add", "new_text": ""}) is None and su.make_suggester({**_CAT, "titles": {}}, ".")(0, item) is None       # no titles: nothing to propose from
    assert su.make_suggester({**_CAT, "unparsed": True}, ".")(0, item) is None and su.make_suggester(_CAT, ".", enabled=False)(0, item) is None
    seen = []
    monkeypatch.setattr(su, "propose", lambda text, cat, root, **k: seen.append(k["timeout"]) or {"source": "fallback", "fr_id": None})
    assert s(0, item)["source"] == "fallback" and seen == [30]
    now[0] = 20.0
    s(1, item)
    assert seen[-1] == 10                                                                                    # what is left of the shared 30 s
    now[0] = 29.0
    out = s(2, item)
    assert "time budget" in out["reason"] and len(seen) == 2                                                 # used up: fall back, no call


@pytest.mark.covers("FR-01.11/AC49")
def test_the_model_call_needs_a_key_and_the_documented_switches_send_nothing(monkeypatch, tmp_path):
    sent = []
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    out = su.propose(_PROMISE, _CAT, tmp_path)                                                               # the real transport refuses without a key: nothing is sent
    assert out["source"] == "fallback" and "OPENROUTER_API_KEY" in out["reason"]
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(su, "default_transport", lambda: (lambda m, t: sent.append(m) or json.dumps({"fr_id": "FR-01.03"})))
    assert su.propose(_PROMISE, _CAT, tmp_path)["source"] == "model" and len(sent) == 1                      # key present, nothing switched off: sent once
    for value in ("0", "false", "off", "no"):                                                                # SHIPWRIGHT_AC_MODEL_SUGGEST=0
        monkeypatch.setenv(su.SWITCH_ENV, value)
        assert su.propose(_PROMISE, _CAT, tmp_path)["source"] == "fallback"
    monkeypatch.delenv(su.SWITCH_ENV)
    cfg = tmp_path / "shipwright_iterate_config.json"                                                         # ac_decision.model_suggest: false
    cfg.write_text(json.dumps({"ac_decision": {"model_suggest": False}}), encoding="utf-8")
    assert su.propose(_PROMISE, _CAT, tmp_path)["source"] == "fallback"
    cfg.write_text("{not json", encoding="utf-8")                                                              # an unreadable own config fails closed
    assert su.propose(_PROMISE, _CAT, tmp_path)["source"] == "fallback"
    cfg.write_text(json.dumps({"ac_decision": {"model_suggest": True}}), encoding="utf-8")
    assert su.propose(_PROMISE, _CAT, tmp_path)["source"] == "model" and len(sent) == 2                      # and on again: the second (and last) send
