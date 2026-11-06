"""A small model proposes WHICH existing requirement a new acceptance criterion belongs to - nothing else.

When a new AC has no single owning requirement, the operator is asked about ONE best-fitting requirement. Which one fits by
MEANING is the only job of the model (existing OpenRouter transport, one id back). Code does the rest: the id must exist in
the base catalog, and the question shows that requirement's exact text from the spec - no model wording of any text ever
reaches the operator. Any failure (no key, opted out, timeout, bad reply, unknown id) gives ``fr_id: None``; the question then
uses the deterministic best match by shared words (:func:`lib.ac_catalog.candidates`). This module never raises and never blocks
Step 2a. The model is pinned (:data:`MODEL`); a model in a namespace that needs a zero-data-retention rule is refused.
Opt-outs, all fail-closed (an unreadable config means nothing is sent): ``SHIPWRIGHT_AC_SUGGEST=0``, the config key
``external_review.ac_suggest: false``, ``external_review.feedback_iterations: 0``, or an operator gateway. The AC text and
catalog excerpts go to the external provider, as plan reviews do.
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

from lib.ac_catalog import fr_text, words

__all__ = ["BUDGET", "MODEL", "OFF_ENV", "default_transport", "make_suggester", "prompt_text", "propose"]

OFF_ENV = "SHIPWRIGHT_AC_SUGGEST"
MODEL = "anthropic/claude-haiku-5.5"  # pinned: a PR-review model change must not silently change what this sends
TIMEOUT, BUDGET = 45, 30
_ROOT = Path(__file__).resolve().parents[3]
PROMPT_PATH = _ROOT / "shared" / "prompts" / "ac_suggest.md"
_TRANSPORT_PATH = _ROOT / "plugins" / "shipwright-security" / "scripts" / "lib" / "pr_review_openrouter.py"
_TRANSPORT_NAME = "_ac_suggest_openrouter"
_ZDR_NAMESPACES = ("deepseek/", "z-ai/")  # models that need a zero-data-retention provider rule, which this call does not carry
_PAYLOAD_CAP = 24000


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
    except Exception:  # noqa: BLE001 - fail closed: if the opt-out cannot be read, the text is not sent
        return True


def _payload(promise: str, cat: dict) -> str:
    """The AC text and the requirements (best word overlap first), capped in size."""
    want = words(promise)
    rows = []
    for fr, title in sorted(cat.get("titles", {}).items()):
        crit = [re.sub(r"\s+", " ", b)[:140] for ac, b in sorted(cat.get("acs", {}).items()) if ac.rsplit(".AC", 1)[0] == fr][:3]
        rows.append((-len(want & words(title + " " + fr_text(fr, cat) + " " + " ".join(crit))), fr, {"fr_id": fr, "title": title, "text": fr_text(fr, cat)[:240], "criteria": crit}))
    rows.sort(key=lambda r: (r[0], r[1]))
    out, size = [], 0
    for _, _, row in rows:
        size += len(json.dumps(row, ensure_ascii=False))
        if size > _PAYLOAD_CAP:
            break
        out.append(row)
    return json.dumps({"acceptance_criterion": promise, "requirements": out}, ensure_ascii=False)


def _fr_from(raw: object, cat: dict) -> tuple[str | None, str]:
    """``(id, "")`` for a reply that names one requirement of the catalog, else ``(None, why)``."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else None
    except ValueError:
        data = None
    fr = data.get("fr_id") if isinstance(data, dict) else None
    if not isinstance(data, dict):
        return None, "the reply is not a JSON object"
    return (fr, "") if isinstance(fr, str) and fr in cat.get("frs", ()) else (None, f"unknown requirement id {fr!r}")


def propose(promise: str, cat: dict, project_root: str | Path = ".", transport: Callable[[list[dict], int], str] | None = None,
            model: str = "", timeout: int = TIMEOUT) -> dict:
    """``{"source": "model"|"fallback", "fr_id": id or None, "reason", ["model", "prompt_sha"]}``; never raises."""
    try:
        if transport is None:
            if _opted_out(project_root):
                return {"source": "fallback", "fr_id": None, "reason": "switched off (SHIPWRIGHT_AC_SUGGEST, external_review.ac_suggest or feedback_iterations 0), an operator gateway, or an unreadable config"}
            transport, model = default_transport(), MODEL
        model = model or MODEL
        if model.lower().startswith(_ZDR_NAMESPACES):
            return {"source": "fallback", "fr_id": None, "reason": f"model {model!r} needs a zero-data-retention rule this call does not carry"}
        prompt = prompt_text()
        raw = transport([{"role": "system", "content": prompt}, {"role": "user", "content": _payload(promise, cat)}], timeout)
        fr, why = _fr_from(raw, cat)
        if fr is None:
            return {"source": "fallback", "fr_id": None, "reason": why}
        return {"source": "model", "fr_id": fr, "reason": "", "model": model, "prompt_sha": "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()}
    except Exception as exc:  # noqa: BLE001 - no key, missing file, timeout, transport error: a display aid never blocks Step 2a
        return {"source": "fallback", "fr_id": None, "reason": f"{type(exc).__name__}: {str(exc)[:120]}"}


def make_suggester(cat: dict, project_root: str | Path, enabled: bool = True, budget: float = BUDGET,
                   clock: Callable[[], float] = time.monotonic) -> Callable[[int, dict], dict | None]:
    """A callable ``(item index, item) -> proposal | None`` for :func:`lib.ac_decision.decide`, asked only when a question is rendered.

    ``None`` when the item is not a new AC without an owner, the catalog has no requirement titles, or it is switched off.
    One shared time budget (:data:`BUDGET` seconds) covers all items of a decide call; once it is used up the rest fall back.
    """
    start = clock()

    def suggester(_n: int, item: dict) -> dict | None:
        text = " ".join(str(item.get("new_text") or "").split()) if isinstance(item, dict) else ""
        if not enabled or cat.get("unparsed") or not cat.get("titles") or not text or item.get("kind") != "add" or isinstance(item.get("new_fr"), dict):
            return None
        left = budget - (clock() - start)
        if left < 2:
            return {"source": "fallback", "fr_id": None, "reason": "the time budget for suggestions is used up"}
        return propose(text, cat, project_root, timeout=int(min(TIMEOUT, left)))
    return suggester
