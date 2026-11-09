"""A small model proposes WHICH existing requirement a new acceptance criterion belongs to, and drafts a new one if none does.

When a new AC has no single owning requirement, the operator is asked about ONE best-fitting requirement. Which one fits by
MEANING is the job of the model (existing OpenRouter transport, one JSON reply): the id (or null = none fits), an optional
plain line of at most 12 words, and a drafted title and one sentence for a new requirement. Code does the rest: the id must
exist in the base catalog, every line is checked (:func:`_clean`: length, no quotes, brackets, code or ids) and dropped if not
plain, and the question shows the requirement's name from the spec. Any failure (no key, opted out, timeout, bad reply, unknown id) gives ``fr_id: None``; the question then
uses the deterministic best match by shared words (:func:`lib.ac_catalog.candidates`). This module never raises and never blocks
Step 2a. The model is pinned (:data:`MODEL`); a model in a namespace that needs a zero-data-retention rule is refused.
**What leaves the machine, and when.** Only the acceptance-criterion sentence the agent wrote and, for each requirement, its id and title
(:func:`_payload`), plus the fixed prompt ``shared/prompts/ac_suggest.md``: no code, no diff, no file paths, no requirement text.
It is sent to the OpenRouter provider only when an ``OPENROUTER_API_KEY`` is present, a new AC has no single owner, and nothing below
switched it off. Switch it off with ``ac_decision.model_suggest: false`` in ``shipwright_iterate_config.json`` or
``SHIPWRIGHT_AC_MODEL_SUGGEST=0``; then the deterministic best match by shared words is used and nothing goes over the network.
Older switches still work: ``SHIPWRIGHT_AC_SUGGEST=0``, ``external_review.ac_suggest: false``, ``external_review.feedback_iterations: 0``
and an operator gateway. All fail closed (an unreadable config means nothing is sent).
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
from lib.ac_wording import wording_violations

__all__ = ["BUDGET", "MODEL", "OFF_ENV", "SWITCH_ENV", "default_transport", "make_suggester", "prompt_text", "propose"]

OFF_ENV = "SHIPWRIGHT_AC_SUGGEST"
SWITCH_ENV = "SHIPWRIGHT_AC_MODEL_SUGGEST"
_OFF_WORDS = ("0", "false", "off", "no")
MODEL = "anthropic/claude-haiku-5.5"  # pinned: a PR-review model change must not silently change what this sends
TIMEOUT, BUDGET = 45, 30
_ROOT = Path(__file__).resolve().parents[3]
PROMPT_PATH = _ROOT / "shared" / "prompts" / "ac_suggest.md"
_TRANSPORT_PATH = _ROOT / "plugins" / "shipwright-security" / "scripts" / "lib" / "pr_review_openrouter.py"
_TRANSPORT_NAME = "_ac_suggest_openrouter"
_ZDR_NAMESPACES = ("deepseek/", "z-ai/")  # models that need a zero-data-retention provider rule, which this call does not carry
_PAYLOAD_CAP = 24000
LINE_WORDS, TITLE_WORDS, SENTENCE_WORDS = 12, 12, 30  # the longest a checked model line, a drafted requirement title and its one sentence may be


_ANNOUNCED: set[str] = set()  # one-time stderr notices already printed


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
    if any(os.environ.get(name, "").strip().lower() in _OFF_WORDS for name in (SWITCH_ENV, OFF_ENV)) or os.environ.get("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL"):
        return True
    try:
        own = json.loads((Path(project_root) / "shipwright_iterate_config.json").read_text(encoding="utf-8-sig"))
        block = own.get("ac_decision") if isinstance(own, dict) else None
        if isinstance(block, dict) and block.get("model_suggest") is False:
            return True
    except FileNotFoundError:
        pass
    except (OSError, ValueError):  # an unreadable own config: fail closed
        return True
    try:
        from lib.external_review_config import load_review_config
        ext = load_review_config(project_root=project_root).get("external_review") or {}
        return ext.get("feedback_iterations") == 0 or ext.get("ac_suggest") is False
    except Exception:  # noqa: BLE001 - fail closed: if the opt-out cannot be read, the text is not sent
        return True


def _payload(promise: str, cat: dict) -> str:
    """The ONLY data sent to the model: the AC sentence and each requirement's id and title (best word overlap first, capped in size).

    The overlap is ranked locally over the requirement's full text; that text itself never leaves the machine."""
    want = words(promise)
    rows = []
    for fr, title in sorted(cat.get("titles", {}).items()):
        crit = [b for ac, b in sorted(cat.get("acs", {}).items()) if ac.rsplit(".AC", 1)[0] == fr][:3]
        rows.append((-len(want & words(title + " " + fr_text(fr, cat) + " " + " ".join(crit))), fr, {"fr_id": fr, "title": title}))
    rows.sort(key=lambda r: (r[0], r[1]))
    out, size = [], 0
    for _, _, row in rows:
        size += len(json.dumps(row, ensure_ascii=False))
        if size > _PAYLOAD_CAP:
            break
        out.append(row)
    return json.dumps({"acceptance_criterion": promise, "requirements": out}, ensure_ascii=False)


def _clean(text: object, max_words: int) -> str:
    """A short model line, or ``""`` when it is not plain: empty, too long, quotes, brackets, code or an id. Code never shows a line it did not check."""
    line = " ".join(text.split()) if isinstance(text, str) else ""
    if not line or len(line.split()) > max_words or re.search(r"[\"`<>\[\]{}]", line) or wording_violations(line, None):
        return ""
    return line


def _reply(raw: object, cat: dict) -> tuple[dict | None, str]:
    """``(proposal fields, "")`` for a usable reply, else ``(None, why)``. ``fr_id: None`` with ``none: True`` is the model saying no requirement fits."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return None, "the reply is not a JSON object"
    if "fr_id" not in data:
        return None, "the reply has no fr_id"
    fr = data["fr_id"]
    if fr is not None and not (isinstance(fr, str) and fr in cat.get("frs", ())):
        return None, "unknown requirement id: the reply named an id that is not in the catalog"
    return {"fr_id": fr, "none": fr is None, "line": _clean(data.get("line"), LINE_WORDS) if fr else "",
            "title": _clean(data.get("title"), TITLE_WORDS), "sentence": _clean(data.get("sentence"), SENTENCE_WORDS)}, ""


def propose(promise: str, cat: dict, project_root: str | Path = ".", transport: Callable[[list[dict], int], str] | None = None,
            model: str = "", timeout: int = TIMEOUT) -> dict:
    """``{"source": "model"|"fallback", "fr_id": id or None, "none", "line", "title", "sentence", "reason", ["model", "prompt_sha"]}``; never raises.

    ``line`` (at most 12 words) and the drafted ``title`` / ``sentence`` of a new requirement are ``""`` unless code checked them."""
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
        fields, why = _reply(raw, cat)
        if fields is None:
            return {"source": "fallback", "fr_id": None, "reason": why}
        return {"source": "model", **fields, "reason": "", "model": model, "prompt_sha": "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest()}
    except Exception as exc:  # noqa: BLE001 - no key, missing file, timeout, transport error: a display aid never blocks Step 2a
        if isinstance(exc, FileNotFoundError) and "transport" not in _ANNOUNCED:  # a missing transport file is an install problem: say so once, not per item
            _ANNOUNCED.add("transport")
            print(f"ac_suggest: the model transport was not found ({str(exc)[:120]}); proposals fall back to the deterministic match", file=sys.stderr)
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
