"""The model's plain gloss and area suggestions: strict validation in both directions, the pin, the cache (stubbed transport, never the live provider)."""

from __future__ import annotations

import json
import sys

import pytest

from lib import ac_decision as ad
from lib import ac_suggest as su

_PROMISE = "A draft that is older than 30 days is deleted unless the owner keeps it"
_CAT = {"acs": {"FR-01.03.AC01": "Given a draft, when saved, then it is kept.", "FR-01.04.AC01": "Given a link, when opened, then the draft shows."},
        "frs": {"FR-01.03", "FR-01.04"}, "titles": {"FR-01.03": "Saving drafts", "FR-01.04": "Sharing drafts"}, "unparsed": False}
_GOOD = {"plain_promise": "A draft that is 30 days old or older is removed, unless the owner keeps it.",
         "areas": [{"fr_id": "FR-01.03", "plain_description": "How drafts are saved and kept."}]}
_NEG = "A draft cannot be deleted without the owner's consent, and every copy is kept"


def _run(reply, promise=_PROMISE, **kw):
    calls = []

    def transport(messages, timeout):
        calls.append(messages)
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply)
    out = su.suggest(promise, _CAT, ".", transport=transport, model=kw.pop("model", "stub/model"), **kw)
    return out, calls


@pytest.mark.covers("FR-01.11/AC49")
def test_a_good_reply_is_a_gloss_under_the_original_and_the_record_keeps_both_the_model_and_the_prompt_sha():
    out, calls = _run(_GOOD)
    assert out["source"] == "model" and out["model"] == "stub/model" and out["prompt_sha"].startswith("sha256:")
    assert out["original_promise"] == _PROMISE and out["plain_promise"].startswith("A draft that is 30 days old")
    assert json.loads(calls[0][1]["content"])["promise"] == _PROMISE
    q = ad.render_question({"kind": "add", "new_text": _PROMISE}, _CAT, out)
    lines = q.splitlines()
    assert lines[0] == f"This change adds a new promise: {_PROMISE}." and lines[1].startswith("In plain words: A draft that is 30 days old")  # display = frozen text first
    assert lines[2] == "Which requirement would this promise belong to?" and "FR-01" not in q and "A Saving drafts: How drafts are saved and kept." in q
    assert ad.question_options({"kind": "add", "new_text": _PROMISE}, _CAT, out)["A"] == {"choice": "yes", "text": "FR-01.03"}
    meta = ad.suggestion_meta(out)
    assert meta["suggestion_source"] == "model" and meta["suggestion_original_promise"] == _PROMISE and meta["suggestion_model"] == "stub/model" and "suggestion_prompt_sha" in meta


@pytest.mark.covers("FR-01.11/AC49")
@pytest.mark.parametrize("promise, plain, why", [
    (_PROMISE, "A draft that is old is deleted, unless the owner keeps it.", "numbers differ"),                        # dropped number
    (_PROMISE, "A draft that is 300 days old is deleted, unless the owner keeps it.", "numbers differ"),               # 30 must not match 300
    ("A draft is kept for 5 days unless the owner keeps it", "A draft is kept for 15 days, unless the owner keeps it.", "numbers differ"),   # 5 must not match 15
    (_PROMISE, "A draft that is 30 days old, or two weeks, is removed, unless the owner keeps it.", "numbers differ"),  # added number word
    (_PROMISE, "A draft that is 30 days old is deleted whenever the owner agrees.", "negations or limits differ"),      # dropped unless
    (_PROMISE, "A draft that is 30 days old is deleted unless the owner keeps it, and never otherwise.", "negations or limits differ"),   # added never
    (_PROMISE, "Every draft that is 30 days old is deleted unless the owner keeps it.", "negations or limits differ"),  # added quantifier
    (_NEG, "A draft can be removed without the owner's consent, and every copy is kept.", "negations or limits differ"),   # cannot dropped
    (_NEG, "A draft cannot be removed, and every copy is kept.", "negations or limits differ"),                         # without dropped
    (_NEG, "A draft cannot be removed without the owner's consent, and no copy is lost.", "negations or limits differ"),  # every -> no
    (_PROMISE, "A draft that is 30 days old is deleted unless the owner keeps it; see plan_review.py.", "code-shaped"),
    (_PROMISE, "x" * 500, "too long"),
])
def test_a_reply_that_drops_changes_or_adds_a_number_negation_or_limit_falls_back(promise, plain, why):
    out, _ = _run({"plain_promise": plain, "areas": _GOOD["areas"]}, promise=promise)
    assert out["source"] == "fallback" and why in out["reason"]
    q = ad.render_question({"kind": "add", "new_text": promise}, _CAT, out)
    assert q.startswith(f"This change adds a new promise: {promise}") and "In plain words" not in q   # today's deterministic wording


@pytest.mark.covers("FR-01.11/AC49")
@pytest.mark.parametrize("promise, plain", [
    (_PROMISE, "A draft that is thirty days old or older is removed, unless the owner keeps it."),                    # number words equal digits
    (_NEG, "A draft can't be removed without the owner's consent, and every copy is kept."),                          # can't == cannot
    (_NEG, "A draft cannot be removed without the owner’s consent, and every copy is kept."),                        # typographic apostrophe
])
def test_equivalent_spellings_of_the_same_numbers_and_negations_are_accepted(promise, plain):
    out, _ = _run({"plain_promise": plain, "areas": _GOOD["areas"]}, promise=promise)
    assert out["source"] == "model", out["reason"]


@pytest.mark.covers("FR-01.11/AC49")
@pytest.mark.parametrize("areas, why", [
    ([{"fr_id": "FR-99.99", "plain_description": "Invented."}], "unknown area id"),
    ([{"fr_id": "FR-01.03", "plain_description": "One."}, {"fr_id": "FR-01.03", "plain_description": "Two."}], "twice"),
    ([{"fr_id": f"FR-01.0{i}", "plain_description": "y"} for i in (3, 4, 5, 6)], "more than 3"),
    ([{"fr_id": "FR-01.03", "plain_description": "Uses plan_review.py"}], "code-shaped"),
    ([{"fr_id": "FR-01.03", "plain_description": ""}], "empty"),
    ("not a list", "missing"),
])
def test_bad_areas_fall_back_with_their_reason(areas, why):
    out, _ = _run({"plain_promise": _GOOD["plain_promise"], "areas": areas})
    assert out["source"] == "fallback" and why in out["reason"]


@pytest.mark.covers("FR-01.11/AC49")
@pytest.mark.parametrize("reply", ["this is not json", "[1, 2]", "", None])
def test_a_non_json_reply_falls_back(reply):
    out, _ = _run(reply if reply is not None else "null")
    assert out["source"] == "fallback" and "not a JSON object" in out["reason"]


@pytest.mark.covers("FR-01.11/AC49")
def test_an_empty_area_list_keeps_the_plain_wording_with_the_deterministic_area_list():
    out, _ = _run({"plain_promise": _GOOD["plain_promise"], "areas": []})
    assert out["source"] == "model" and out["areas"] == []
    q = ad.render_question({"kind": "add", "new_text": "Drafts are saved and shared"}, _CAT, {**out, "original_promise": "Drafts are saved and shared"})
    assert "In plain words:" in q and "A Saving drafts" in q                 # candidates by shared words, not from the model


@pytest.mark.covers("FR-01.11/AC49")
def test_the_model_is_pinned_and_a_model_that_needs_a_zero_retention_rule_is_refused(monkeypatch):
    assert su.MODEL == "anthropic/claude-haiku-5.5"
    for model in ("deepseek/deepseek-v4-pro", "z-ai/glm-5.3", "Z-AI/GLM-5.3"):
        out, calls = _run(_GOOD, model=model)
        assert out["source"] == "fallback" and "zero-data-retention" in out["reason"] and calls == []
    seen = []
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    mod = su._load_transport()
    monkeypatch.setattr(mod, "call_openrouter", lambda key, model, messages, timeout: seen.append(model) or json.dumps(_GOOD))
    monkeypatch.setattr(su, "_opted_out", lambda root: False)
    assert su.suggest(_PROMISE, _CAT, ".")["source"] == "model" and seen == [su.MODEL]       # not the PR review's default
    monkeypatch.setattr(su, "MODEL", "z-ai/glm-5.3")
    assert "zero-data-retention" in su.suggest(_PROMISE, _CAT, ".", use_cache=False)["reason"] and seen == ["anthropic/claude-haiku-5.5"]


@pytest.mark.covers("FR-01.11/AC49")
def test_the_transport_module_is_loaded_once_registered_before_it_runs_and_a_missing_file_is_a_fallback_never_cached(monkeypatch, tmp_path):
    first = su._load_transport()
    assert su._load_transport() is first and sys.modules[su._TRANSPORT_NAME] is first
    monkeypatch.delitem(sys.modules, su._TRANSPORT_NAME)
    monkeypatch.setattr(su, "_TRANSPORT_PATH", tmp_path / "gone.py")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(su, "_opted_out", lambda root: False)
    out = su.suggest(_PROMISE, _CAT, ".")
    assert out["source"] == "fallback" and "FileNotFoundError" in out["reason"] and su._TRANSPORT_NAME not in sys.modules
    (tmp_path / "boom.py").write_text("raise RuntimeError('import failed')\n", encoding="utf-8")
    monkeypatch.setattr(su, "_TRANSPORT_PATH", tmp_path / "boom.py")
    assert "import failed" in su.suggest(_PROMISE, _CAT, ".")["reason"] and su._TRANSPORT_NAME not in sys.modules      # a failed import leaves nothing registered
    assert not list(su._cache_dir().glob("*.json"))                                                                    # environment failures are never cached


@pytest.mark.covers("FR-01.11/AC49")
def test_the_cache_is_one_file_per_key_revalidated_on_every_hit_and_a_bad_entry_is_a_miss():
    first, calls1 = _run(_GOOD)
    files = list(su._cache_dir().glob("*.json"))
    assert len(files) == 1 and not list(su._cache_dir().glob("*.tmp"))
    again, calls2 = _run({"plain_promise": "Something else.", "areas": []})
    assert calls1 and not calls2 and again["plain_promise"] == first["plain_promise"]                  # reused, no second call
    entry = json.loads(files[0].read_text(encoding="utf-8"))
    entry["raw"] = json.dumps({**_GOOD, "areas": [{"fr_id": "FR-99.99", "plain_description": "Gone."}]})   # the cached reply no longer validates
    files[0].write_text(json.dumps(entry), encoding="utf-8")
    stale, calls3 = _run({"plain_promise": "Something else.", "areas": []})
    assert stale["source"] == "fallback" and "unknown area id" in stale["reason"] and not calls3
    for bad in ("{not json", "[]", json.dumps({**entry, "v": 1}), json.dumps({**entry, "original_promise": "another promise"}), json.dumps({**entry, "raw": 7}), ""):
        files[0].write_text(bad, encoding="utf-8")                                                  # corrupt, foreign or malformed: a miss, never a traceback
        out, calls = _run(_GOOD)
        assert out["source"] == "model" and calls
    other, _ = _run(_GOOD, promise=_PROMISE + " today")                                              # another key is another file; nothing else is overwritten
    assert len(list(su._cache_dir().glob("*.json"))) == 2 and other["original_promise"].endswith("today")
    assert su.suggest(_PROMISE, _CAT, ".", transport=lambda m, t: json.dumps(_GOOD), model="stub/model", use_cache=False)["source"] == "model"


@pytest.mark.covers("FR-01.11/AC49")
def test_a_timeout_and_a_missing_key_fall_back_and_are_never_cached(monkeypatch):
    out, _ = _run(TimeoutError("read timed out"))
    assert out["source"] == "fallback" and "TimeoutError" in out["reason"]
    monkeypatch.setattr(su, "_opted_out", lambda root: False)
    no_key = su.suggest(_PROMISE, _CAT, ".")
    assert no_key["source"] == "fallback" and "OPENROUTER_API_KEY" in no_key["reason"]
    assert not list(su._cache_dir().glob("*.json"))
