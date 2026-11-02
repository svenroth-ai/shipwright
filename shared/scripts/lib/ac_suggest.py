"""A model's plain wording and area suggestions for a new promise - a DISPLAY aid, validated by code, never an authority.

When a new promise has no single owner the operator is asked "where does it belong?". The semantic part - which areas
fit by MEANING, and a plain one-sentence wording - is done by a small model through the existing OpenRouter transport
(the cheap model the PR review already uses). Code does every check:

* every ``fr_id`` exists in the base catalog; at most 3 areas; no duplicates; no id invented;
* the plain promise and each description read as outcomes (:mod:`lib.ac_wording`) and stay under a length cap;
* every digit-bearing token and every negation/limit word of the original promise is still in the plain promise.

Any failure (no key, opted out, timeout, bad JSON, rejected output, empty) falls back to the deterministic wording and
candidates (``source: "fallback"``, with the ``reason``); this module never raises and never blocks Step 2a. The result is
cached by content so a re-run asks the SAME question (the operator's answer is bound to the question text). It never changes
what is frozen as the AC text: the original promise stays in the record next to the plain version, with the model id and
the prompt sha. Promise text and catalog excerpts go to the external provider, as plan reviews do.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
from typing import Callable

from lib.ac_catalog import _words
from lib.ac_wording import wording_violations

__all__ = ["CACHE_ENV", "MAX_AREAS", "default_transport", "model_id", "prompt_text", "suggest", "suggestions_for", "validate"]

CACHE_ENV = "SHIPWRIGHT_AC_SUGGEST_CACHE"
MAX_AREAS, MAX_PROMISE, MAX_DESC, TIMEOUT = 3, 400, 160, 45
_ROOT = Path(__file__).resolve().parents[3]
PROMPT_PATH = _ROOT / "shared" / "prompts" / "ac_suggest.md"
_TRANSPORT_PATH = _ROOT / "plugins" / "shipwright-security" / "scripts" / "lib" / "pr_review_openrouter.py"
_LIMIT_WORDS = ("not", "never", "unless", "only", "at most", "at least", "no")
_PAYLOAD_CAP = 24000


def prompt_text() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _load_transport():
    spec = importlib.util.spec_from_file_location("_ac_suggest_openrouter", _TRANSPORT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def model_id() -> str:
    """The cheap model the PR review defaults to (read from its transport module, so the two cannot drift)."""
    return _load_transport().DEFAULT_MODEL


def default_transport() -> Callable[[list[dict], int], str]:
    """The existing OpenRouter call; raises ``RuntimeError`` when no key is set."""
    mod = _load_transport()
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise RuntimeError("no OPENROUTER_API_KEY")
    return lambda messages, timeout: mod.call_openrouter(key, mod.DEFAULT_MODEL, messages, timeout)


def _opted_out(project_root: str | Path) -> bool:
    """True when external review is switched off for this project (feedback_iterations 0) or runs through an operator gateway."""
    if os.environ.get("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL"):
        return True
    try:
        from lib.external_review_config import load_review_config
        cfg = load_review_config(project_root=project_root)
        return (cfg.get("external_review") or {}).get("feedback_iterations") == 0
    except Exception:  # noqa: BLE001 - an unreadable config must not stop a display aid; the key check still applies
        return False


def _areas_payload(promise: str, cat: dict) -> list[dict]:
    want = _words(promise)
    rows = []
    for fr, title in sorted(cat.get("titles", {}).items()):
        crit = [re.sub(r"\s+", " ", b)[:140] for ac, b in sorted(cat.get("acs", {}).items()) if ac.rsplit(".AC", 1)[0] == fr][:3]
        score = len(want & _words(title + " " + " ".join(crit)))
        rows.append((-score, fr, {"fr_id": fr, "title": title, "criteria": crit}))
    rows.sort(key=lambda r: (r[0], r[1]))
    out, size = [], 0
    for _, _, row in rows:
        size += len(json.dumps(row, ensure_ascii=False))
        if size > _PAYLOAD_CAP:
            break
        out.append(row)
    return out


def _tokens(text: str) -> list[str]:
    return [t.strip(".,;:!?()[]\"'").lower() for t in text.split() if re.search(r"\d", t)]


def validate(raw: object, promise: str, cat: dict, identifiers: set[str] | None = None) -> tuple[dict | None, str]:
    """``(clean {"plain_promise", "areas"}, "")`` for a usable model reply, else ``(None, why it was rejected)``."""
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
        return None, "the plain promise carries code-shaped wording"
    low = plain.lower()
    orig = promise.lower()
    for tok in _tokens(promise):
        if tok not in low:
            return None, f"the number or limit {tok!r} of the promise is missing"
    for word in _LIMIT_WORDS:
        if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", orig) and not re.search(rf"(?<!\w){re.escape(word)}(?!\w)", low):
            return None, f"the word {word!r} of the promise is missing"
    if not areas or len(areas) > MAX_AREAS:
        return None, "no area suggested" if not areas else "more than 3 areas"
    clean, seen = [], set()
    for a in areas:
        fr, desc = (a.get("fr_id"), a.get("plain_description")) if isinstance(a, dict) else (None, None)
        if not isinstance(fr, str) or fr not in cat.get("frs", ()):
            return None, f"unknown area id {fr!r}"
        if fr in seen:
            return None, f"area {fr} suggested twice"
        if not isinstance(desc, str) or not desc.strip() or len(desc.strip()) > MAX_DESC or wording_violations(desc, identifiers):
            return None, f"the description of {fr} is empty, too long or code-shaped"
        seen.add(fr)
        clean.append({"fr_id": fr, "plain_description": " ".join(desc.split())})
    return {"plain_promise": plain, "areas": clean}, ""


def _cache_file() -> Path:
    return Path(os.environ[CACHE_ENV]) if os.environ.get(CACHE_ENV) else Path.home() / ".shipwright" / "ac_suggest_cache.json"


def _cache_get(key: str) -> dict | None:
    try:
        hit = json.loads(_cache_file().read_text(encoding="utf-8")).get(key)
        return hit if isinstance(hit, dict) else None
    except (OSError, ValueError, AttributeError):
        return None


def _cache_put(key: str, value: dict) -> None:
    path = _cache_file()
    try:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data = data if isinstance(data, dict) else {}
        data[key] = value
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # a cache that cannot be written only costs a repeat call


def _compute(promise, cat, project_root, transport, identifiers, model, sha, prompt, payload) -> dict:
    try:
        if transport is None:
            if _opted_out(project_root):
                return {"source": "fallback", "reason": "external review is switched off or runs through an operator gateway"}
            transport, model = default_transport(), model_id()
        raw = transport([{"role": "system", "content": prompt}, {"role": "user", "content": payload}], TIMEOUT)
    except Exception as exc:  # noqa: BLE001 - no key, timeout, transport error: a display aid never blocks Step 2a
        return {"source": "fallback", "reason": f"{type(exc).__name__}: {str(exc)[:120]}"}
    clean, why = validate(raw, promise, cat, identifiers)
    if clean is None:
        return {"source": "fallback", "reason": why}
    return {"source": "model", "reason": "", **clean, "model": model or "unknown", "prompt_sha": sha}


def suggest(promise: str, cat: dict, project_root: str | Path = ".", transport: Callable[[list[dict], int], str] | None = None,
            identifiers: set[str] | None = None, use_cache: bool = True, model: str = "") -> dict:
    """``{"source": "model"|"fallback", "reason", "original_promise", ["plain_promise", "areas", "model", "prompt_sha"]}``; never raises."""
    base = {"original_promise": promise}
    try:
        prompt = prompt_text()
        sha = "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        payload = json.dumps({"promise": promise, "areas": _areas_payload(promise, cat)}, ensure_ascii=False)
        key = hashlib.sha256(f"{sha}\n{payload}".encode("utf-8")).hexdigest()
        if use_cache and (hit := _cache_get(key)):
            return {**base, **hit}
        out = _compute(promise, cat, project_root, transport, identifiers, model, sha, prompt, payload)
        if use_cache:
            _cache_put(key, out)  # fallbacks too: a re-run must ask the SAME question the operator answered
        return {**base, **out}
    except Exception as exc:  # noqa: BLE001 - no key, timeout, transport error: a display aid never blocks Step 2a
        return {**base, "source": "fallback", "reason": f"{type(exc).__name__}: {str(exc)[:120]}"}


def suggestions_for(items: object, cat: dict, project_root: str | Path, identifiers: set[str] | None = None, use_cache: bool = True, enabled: bool = True) -> dict:
    """``{item index: suggestion}`` for every item that will be asked "where does it belong?" (an add with no owner in the catalog and no new area)."""
    out: dict = {}
    if not enabled or cat.get("unparsed") or not isinstance(items, list):
        return out
    for n, it in enumerate(items):
        text = " ".join(str(it.get("new_text") or "").split()) if isinstance(it, dict) else ""
        owner = it.get("owner_fr") if isinstance(it, dict) else None
        if text and it.get("kind") == "add" and not isinstance(it.get("new_fr"), dict) and not (isinstance(owner, str) and owner.strip() in cat.get("frs", ())) \
                and not wording_violations(text, identifiers):
            out[n] = suggest(text, cat, project_root, identifiers=identifiers, use_cache=use_cache)
    return out
