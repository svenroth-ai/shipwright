"""Optional LLM adjudication leg for the backfill engine (traceability TT6).

Offline-deterministic by default: the engine only touches this module behind the
``--use-llm`` flag, and only for the residue the deterministic cascade could not
resolve. In CI the engine is handed P1's stubbed record/replay adapter (no live
call); this module holds the R4 payload guard (shared with that adapter's
contract) plus the *production* OpenRouter adjudicator.

R4 data controls (Spec §11-R4) enforced by :func:`validate_payload`:

* the request carries **only** ``test_path`` + ``test_title`` + ``candidate_frs``
  (canonical FR ids) — **never a test body**;
* fields are length-bounded and the FR list is count-bounded, so a body cannot be
  smuggled through an allowed field;
* the LLM verdict is **advisory**: ``auto_write`` is always ``False`` (only
  deterministic corroboration may auto-write — the engine enforces this too).

The production adjudicator sets the model **explicitly** (GPT + Gemini via
OpenRouter, per the external-review convention) — never the silent default, which
would fall back to a costly wrong model. It proposes an FR only on cross-model
**consensus**; disagreement returns ``proposed_fr = None``.
"""

from __future__ import annotations

import json
import re

_ALLOWED_PAYLOAD_KEYS = frozenset({"test_path", "test_title", "candidate_frs"})
_MAX_FIELD_LEN = 300
_MAX_CANDIDATE_FRS = 32
_CANONICAL_FR_RE = re.compile(r"^FR-\d{2}\.\d{2}$")

# §11-R4 "redact secrets": a TS/JS test title is a free-form string that can
# embed a token. Scrub the obvious credential shapes from path + title BEFORE
# anything leaves the process. Conservative + high-precision (avoids mangling
# ordinary identifiers); a residual is still bounded by the length cap.
_SECRET_PATTERNS = (
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}"),  # GitHub tokens
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),                                  # OpenAI-style
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                                     # AWS access key id
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),                           # Slack
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{12,}"),                       # Bearer <jwt/opaque>
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+"),  # JWT
    re.compile(r"\b[A-Fa-f0-9]{40,}\b"),                                     # long hex (hashes/keys)
)
_REDACTED = "[REDACTED]"


def redact_secrets(text: str) -> str:
    """Replace obvious credential/token shapes with ``[REDACTED]`` (§11-R4)."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text


def validate_payload(payload: dict) -> None:
    """Raise ``ValueError`` if ``payload`` breaks an R4 data control (no bodies)."""
    extra = set(payload) - _ALLOWED_PAYLOAD_KEYS
    if extra:
        raise ValueError(f"payload carries disallowed keys (no test bodies, R4): {sorted(extra)}")
    for field in ("test_path", "test_title"):
        value = payload.get(field, "")
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a string, not {type(value).__name__}")
        if len(value) > _MAX_FIELD_LEN:
            raise ValueError(f"{field} exceeds {_MAX_FIELD_LEN} chars; looks like a body, not an identifier")
    frs = payload.get("candidate_frs", [])
    if not isinstance(frs, list):
        raise ValueError("candidate_frs must be a list")
    if len(frs) > _MAX_CANDIDATE_FRS:
        raise ValueError(f"candidate_frs has {len(frs)} entries; a body cannot hide in a bounded FR list (R4)")
    for fr in frs:
        if not (isinstance(fr, str) and _CANONICAL_FR_RE.match(fr)):
            raise ValueError(f"candidate_frs entries must be canonical FR ids (FR-XX.YY), got {fr!r}")


class NullAdjudicator:
    """The default (offline) adjudicator — always abstains. No network, ever."""

    def adjudicate(self, payload: dict) -> dict:
        validate_payload(payload)
        return {"proposed_fr": None, "confidence": 0.0, "auto_write": False}


_SYSTEM_PROMPT = (
    "You map an existing automated test to the single functional requirement it "
    "most likely verifies, choosing ONLY from the candidate FR ids given. You see "
    "only the test's file path and title — never its body. Reply with STRICT JSON: "
    '{"proposed_fr": "FR-XX.YY" | null, "confidence": 0.0-1.0, "rationale": "..."}. '
    "Use null when no candidate clearly fits. Never invent an FR id."
)


class OpenRouterAdjudicator:
    """Production adjudicator — GPT + Gemini via OpenRouter, consensus-only.

    Constructed only when ``--use-llm`` is passed AND ``OPENROUTER_API_KEY`` is
    set. Never imported/instantiated in CI (the stub adapter is injected instead).
    """

    _BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: str, config: dict, resolve_model):
        self._api_key = api_key
        self._config = config
        self._resolve_model = resolve_model

    def _ask(self, model_key: str, payload: dict) -> str | None:
        from openai import OpenAI  # lazy: never a CI import

        model = self._resolve_model(self._config, model_key)  # EXPLICIT model (never silent default)
        timeout = self._config.get("llm_client", {}).get("timeout_seconds", 120)
        client = OpenAI(api_key=self._api_key, base_url=self._BASE_URL, timeout=timeout)
        user = (
            f"Test path: {payload['test_path']}\nTest title: {payload['test_title']}\n"
            f"Candidate FR ids: {', '.join(payload['candidate_frs']) or '(none)'}"
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": _SYSTEM_PROMPT},
                      {"role": "user", "content": user}],
            max_tokens=512,
        )
        return resp.choices[0].message.content

    @staticmethod
    def _parse(raw: str | None) -> tuple[str | None, float]:
        if not raw:
            return None, 0.0
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None, 0.0
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None, 0.0
        fr = data.get("proposed_fr")
        if not (isinstance(fr, str) and _CANONICAL_FR_RE.match(fr)):
            return None, 0.0
        try:
            conf = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        return fr, max(0.0, min(1.0, conf))

    def adjudicate(self, payload: dict) -> dict:
        """Return an advisory verdict; UNTRUSTED output is validated before use."""
        validate_payload(payload)
        allowed = set(payload["candidate_frs"])
        results = []
        for key in ("openrouter_gemini", "openrouter_chatgpt"):
            try:
                fr, conf = self._parse(self._ask(key, payload))
            except Exception:
                fr, conf = None, 0.0
            # Treat the model as untrusted: an FR outside the candidate set is dropped.
            if fr is not None and fr not in allowed:
                fr, conf = None, 0.0
            results.append((fr, conf))
        (fr_a, conf_a), (fr_b, conf_b) = results
        if fr_a is not None and fr_a == fr_b:      # consensus only
            return {"proposed_fr": fr_a, "confidence": min(conf_a, conf_b), "auto_write": False}
        return {"proposed_fr": None, "confidence": 0.0, "auto_write": False}


def build_adjudicator(use_llm: bool, config: dict, resolve_model):
    """Return the production adjudicator when enabled + keyed, else ``NullAdjudicator``."""
    import os
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if use_llm and api_key:
        return OpenRouterAdjudicator(api_key, config, resolve_model)
    return NullAdjudicator()


__all__ = [
    "validate_payload", "redact_secrets", "NullAdjudicator", "OpenRouterAdjudicator",
    "build_adjudicator",
]
