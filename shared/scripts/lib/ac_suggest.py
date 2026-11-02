"""A model's plain gloss and area suggestions for a new promise - a DISPLAY aid, validated by code, never an authority.

When a new promise has no single owner the operator is asked "where does it belong?". The semantic part - which areas
fit by MEANING, and a plain one-sentence gloss - is done by a small model through the existing OpenRouter transport. The
question shows the agent's ORIGINAL promise word for word first, and the plain wording only as "In plain words: ..." under
it. Code does every check:

* every ``fr_id`` exists in the base catalog; at most 3 areas; no duplicates; no id invented (no area at all is allowed:
  the plain wording is then shown with the deterministic area list);
* the plain wording and each description read as outcomes (:mod:`lib.ac_wording`) and stay under a length cap;
* numbers (whole tokens, digits and number words), negations and limits, quantifiers and order words (not, never, unless,
  only, without, except, cannot, at most, at least, more/less/fewer than, all, every, any, each, before, after, within)
  agree in BOTH directions: nothing of the original dropped, nothing added.

Any failure (no key, opted out, timeout, bad JSON, rejected output) falls back to the deterministic wording and candidates
(``source: "fallback"`` with the ``reason``); this module never raises and never blocks Step 2a. The model is pinned here
(:data:`MODEL`) and a model in a namespace that needs a zero-data-retention rule is refused. A reply is cached by content,
one file per key, and re-validated on EVERY hit; environment failures (no key, a missing transport file, a timeout) are
never cached. Opt-outs, all fail-closed (an unreadable config means nothing is sent): ``SHIPWRIGHT_AC_SUGGEST=0``, the
config key ``external_review.ac_suggest: false``, ``external_review.feedback_iterations: 0``, or an operator gateway.
The promise text and catalog excerpts go to the external provider, as plan reviews do.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Callable

from lib.ac_catalog import words
from lib.ac_wording import wording_violations

__all__ = ["BUDGET", "CACHE_ENV", "MAX_AREAS", "MODEL", "OFF_ENV", "default_transport", "make_suggester", "prompt_text", "suggest", "validate"]

CACHE_ENV = "SHIPWRIGHT_AC_SUGGEST_CACHE"  # a DIRECTORY, one file per key
OFF_ENV = "SHIPWRIGHT_AC_SUGGEST"
MODEL = "anthropic/claude-haiku-5.5"  # pinned: a PR-review model change must not silently change what this sends
MAX_AREAS, MAX_PROMISE, MAX_DESC, TIMEOUT, BUDGET, SCHEMA = 3, 400, 160, 45, 30, 2
_ROOT = Path(__file__).resolve().parents[3]
PROMPT_PATH = _ROOT / "shared" / "prompts" / "ac_suggest.md"
_TRANSPORT_PATH = _ROOT / "plugins" / "shipwright-security" / "scripts" / "lib" / "pr_review_openrouter.py"
_TRANSPORT_NAME = "_ac_suggest_openrouter"
_ZDR_NAMESPACES = ("deepseek/", "z-ai/")  # models that need a zero-data-retention provider rule, which this call does not carry
_PAYLOAD_CAP = 24000
_PHRASES = ("at most", "at least", "more than", "less than", "fewer than")
_LIMIT_WORDS = frozenset("not never unless only no without except all every any each before after within more less fewer none nothing nobody neither nor".split())
_NUMBER_WORDS = {w: str(i) for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve".split())} | {
    "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50", "hundred": "100", "thousand": "1000", "million": "1000000", "half": "0.5",
    "twice": "2x", "double": "2x", "triple": "3x", "first": "1st", "second": "2nd", "third": "3rd", "once": "1x"}
del _NUMBER_WORDS["one"]  # "the earlier one" is a pronoun, not a count


def prompt_text() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _load_transport():
    """The existing OpenRouter call, loaded ONCE; registered in ``sys.modules`` BEFORE it executes (ADR-045)."""
    if _TRANSPORT_NAME in sys.modules:
        return sys.modules[_TRANSPORT_NAME]
    spec = importlib.util.spec_from_file_location(_TRANSPORT_NAME, _TRANSPORT_PATH)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(str(_TRANSPORT_PATH))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_TRANSPORT_NAME] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(_TRANSPORT_NAME, None)
        raise
    return mod


def default_transport() -> Callable[[list[dict], int], str]:
    """The existing OpenRouter call with the pinned :data:`MODEL`; raises when the transport file or the key is missing."""
    mod = _load_transport()
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise RuntimeError("no OPENROUTER_API_KEY")
    return lambda messages, timeout: mod.call_openrouter(key, MODEL, messages, timeout)


def _opted_out(project_root: str | Path) -> bool:
    """True when nothing may be sent. Fail-closed: an unreadable or unexpected config also means no send."""
    if os.environ.get(OFF_ENV, "").strip().lower() in ("0", "false", "off", "no") or os.environ.get("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL"):
        return True
    try:
        from lib.external_review_config import load_review_config
        ext = load_review_config(project_root=project_root).get("external_review") or {}
        return ext.get("feedback_iterations") == 0 or ext.get("ac_suggest") is False
    except Exception:  # noqa: BLE001 - fail closed: if the opt-out cannot be read, the promise is not sent
        return True


def _areas_payload(promise: str, cat: dict) -> list[dict]:
    want = words(promise)
    rows = []
    for fr, title in sorted(cat.get("titles", {}).items()):
        crit = [re.sub(r"\s+", " ", b)[:140] for ac, b in sorted(cat.get("acs", {}).items()) if ac.rsplit(".AC", 1)[0] == fr][:3]
        rows.append((-len(want & words(title + " " + " ".join(crit))), fr, {"fr_id": fr, "title": title, "criteria": crit}))
    rows.sort(key=lambda r: (r[0], r[1]))
    out, size = [], 0
    for _, _, row in rows:
        size += len(json.dumps(row, ensure_ascii=False))
        if size > _PAYLOAD_CAP:
            break
        out.append(row)
    return out


def _plain(text: str) -> str:
    text = text.lower().replace("’", "'")
    text = text.replace("cannot", "can not").replace("won't", "will not").replace("can't", "can not").replace("shan't", "shall not")
    return re.sub(r"(\w+)n't\b", r"\1 not", text)


def _limits(text: str) -> set[str]:
    """Negations, limits, quantifiers and order words of ``text``, as a set."""
    t, found = _plain(text), set()
    for phrase in _PHRASES:
        if phrase in t:
            found.add(phrase)
            t = t.replace(phrase, " ")
    return found | {w for w in re.findall(r"[a-z]+", t) if w in _LIMIT_WORDS}


def _numbers(text: str) -> set[str]:
    """Whole numeric tokens (digits, with unit suffix) and number words of ``text``, as a set: 5 never matches 15."""
    t = _plain(text)
    digits = {m.rstrip(".,") for m in re.findall(r"\d[\d.,]*[a-z%]*", t)}
    return digits | {_NUMBER_WORDS[w] for w in re.findall(r"[a-z]+", t) if w in _NUMBER_WORDS}


def validate(raw: object, promise: str, cat: dict, identifiers: set[str] | None = None) -> tuple[dict | None, str]:
    """``(clean {"plain_promise", "areas"}, "")`` for a usable model reply, else ``(None, why it was rejected)``. Never raises."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return None, "the reply is not a JSON object"
    plain, areas = data.get("plain_promise"), data.get("areas")
    if not isinstance(plain, str) or not plain.strip() or len(plain.strip()) > MAX_PROMISE or not isinstance(areas, list):
        return None, "plain_promise or areas missing or too long"
    plain = " ".join(plain.split())
    if wording_violations(plain, identifiers):
        return None, "the plain wording carries code-shaped wording"
    if _numbers(promise) != _numbers(plain):
        return None, f"numbers differ: original {sorted(_numbers(promise))}, plain {sorted(_numbers(plain))}"
    if _limits(promise) != _limits(plain):
        return None, f"negations or limits differ: original {sorted(_limits(promise))}, plain {sorted(_limits(plain))}"
    if len(areas) > MAX_AREAS:
        return None, "more than 3 areas"
    frs = cat.get("frs", ())
    clean, seen = [], set()
    for a in areas:
        fr, desc = (a.get("fr_id"), a.get("plain_description")) if isinstance(a, dict) else (None, None)
        if not isinstance(fr, str) or fr not in frs:
            return None, f"unknown area id {fr!r}"
        if fr in seen:
            return None, f"area {fr} suggested twice"
        if not isinstance(desc, str) or not desc.strip() or len(desc.strip()) > MAX_DESC or wording_violations(desc, identifiers):
            return None, f"the description of {fr} is empty, too long or code-shaped"
        seen.add(fr)
        clean.append({"fr_id": fr, "plain_description": " ".join(desc.split())})
    return {"plain_promise": plain, "areas": clean}, ""


def _from_raw(raw: object, model: str, sha: str, promise: str, cat: dict, identifiers: set[str] | None) -> dict:
    clean, why = validate(raw, promise, cat, identifiers)
    if clean is None:
        return {"source": "fallback", "reason": why}
    return {"source": "model", "reason": "", **clean, "model": model or "unknown", "prompt_sha": sha}


def _cache_dir() -> Path:
    return Path(os.environ[CACHE_ENV]) if os.environ.get(CACHE_ENV) else Path.home() / ".shipwright" / "ac_suggest"


def _cache_get(key: str, promise: str) -> dict | None:
    """A stored model reply for exactly this promise, or ``None`` (a missing, corrupt or foreign entry is a miss, never an error)."""
    try:
        hit = json.loads((_cache_dir() / f"{key}.json").read_text(encoding="utf-8"))
        ok = (isinstance(hit, dict) and hit.get("v") == SCHEMA and hit.get("original_promise") == promise and isinstance(hit.get("raw"), str)
              and isinstance(hit.get("model"), str) and isinstance(hit.get("prompt_sha"), str))
        return hit if ok else None
    except (OSError, ValueError, AttributeError, TypeError):
        return None


def _cache_put(key: str, value: dict) -> None:
    """Write one entry atomically (temp file + replace); a failure only costs a repeat call and never touches other entries."""
    directory = _cache_dir()
    tmp = directory / f"{key}.{os.getpid()}.tmp"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps({"v": SCHEMA, **value}, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, directory / f"{key}.json")
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass


def _compute(promise, cat, project_root, transport, identifiers, model, sha, prompt, payload, timeout) -> tuple[dict, str | None, str]:
    """``(result, raw reply or None, model used)``: ``raw`` is set only when the model answered (environment failures are never cached)."""
    try:
        if transport is None:
            if _opted_out(project_root):
                return {"source": "fallback", "reason": "switched off (SHIPWRIGHT_AC_SUGGEST, external_review.ac_suggest or feedback_iterations 0), an operator gateway, or an unreadable config"}, None, model
            transport, model = default_transport(), MODEL
        model = model or MODEL
        if model.lower().startswith(_ZDR_NAMESPACES):
            return {"source": "fallback", "reason": f"model {model!r} needs a zero-data-retention rule this call does not carry"}, None, model
        raw = transport([{"role": "system", "content": prompt}, {"role": "user", "content": payload}], timeout)
    except Exception as exc:  # noqa: BLE001 - no key, missing file, timeout, transport error: a display aid never blocks Step 2a
        return {"source": "fallback", "reason": f"{type(exc).__name__}: {str(exc)[:120]}"}, None, model
    return _from_raw(raw, model, sha, promise, cat, identifiers), raw if isinstance(raw, str) else None, model


def suggest(promise: str, cat: dict, project_root: str | Path = ".", transport: Callable[[list[dict], int], str] | None = None,
            identifiers: set[str] | None = None, use_cache: bool = True, model: str = "", timeout: int = TIMEOUT) -> dict:
    """``{"source": "model"|"fallback", "reason", "original_promise", ["plain_promise", "areas", "model", "prompt_sha"]}``; never raises."""
    base = {"original_promise": promise}
    try:
        prompt = prompt_text()
        sha = "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        payload = json.dumps({"promise": promise, "areas": _areas_payload(promise, cat)}, ensure_ascii=False)
        key = hashlib.sha256(f"{SCHEMA}\n{sha}\n{model or MODEL}\n{payload}".encode("utf-8")).hexdigest()
        if use_cache and (hit := _cache_get(key, promise)):
            return {**base, **_from_raw(hit["raw"], hit["model"], hit["prompt_sha"], promise, cat, identifiers)}  # re-validated on EVERY hit
        out, raw, used = _compute(promise, cat, project_root, transport, identifiers, model, sha, prompt, payload, timeout)
        if use_cache and raw is not None:
            _cache_put(key, {"original_promise": promise, "raw": raw, "model": used, "prompt_sha": sha})
        return {**base, **out}
    except Exception as exc:  # noqa: BLE001 - never raises
        return {**base, "source": "fallback", "reason": f"{type(exc).__name__}: {str(exc)[:120]}"}


def make_suggester(cat: dict, project_root: str | Path, identifiers: set[str] | None = None, use_cache: bool = True, enabled: bool = True,
                   budget: float = BUDGET, clock: Callable[[], float] = time.monotonic) -> Callable[[int, dict], dict | None]:
    """A callable ``(item index, item) -> suggestion | None`` for :func:`lib.ac_decision.decide`, asked only when a question is rendered.

    ``None`` when the item is not an add that asks "where does it belong?", the catalog has no area titles, or it is switched off.
    One shared time budget (:data:`BUDGET` seconds) covers all items of a decide call; once it is used up the rest fall back.
    """
    start = clock()

    def suggester(_n: int, item: dict) -> dict | None:
        text = " ".join(str(item.get("new_text") or "").split()) if isinstance(item, dict) else ""
        if not enabled or cat.get("unparsed") or not cat.get("titles") or not text or item.get("kind") != "add" or isinstance(item.get("new_fr"), dict):
            return None
        left = budget - (clock() - start)
        if left < 2:
            return {"source": "fallback", "reason": "the time budget for suggestions is used up", "original_promise": text}
        return suggest(text, cat, project_root, identifiers=identifiers, use_cache=use_cache, timeout=int(min(TIMEOUT, left)))
    return suggester
