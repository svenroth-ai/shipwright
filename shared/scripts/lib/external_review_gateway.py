"""Operator-owned OpenAI-compatible gateway route for external review (issue #547).

Split out of ``llm_review.py`` to mirror this package's existing separation
of concerns: ``external_review_routing.py`` holds the locked-down
GLM/OpenAI policy (model-identity lock + ZDR allowlist);  this module
holds the opposite. The gateway route carries NEITHER — the operator's
gateway/virtual key decides which model actually answers, by design. It
fits any OpenAI-compatible gateway (Portkey, Helicone, LiteLLM proxy, Azure
AI Foundry, ...); nothing here is Portkey-specific.

Fail-closed is the property that matters: once
``SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL`` is configured, the route is
exclusive. Callers must not fall back to openrouter/direct on a leg
failure — see ``review_gateway``'s docstring. A misconfigured slot (missing
model or key) is reported as ``error``, never ``skipped``: "skipped" would
read as "review not needed", which is the wrong signal once the operator
has opted into gateway-only egress.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse, urlunparse

# Same dual bare/package-qualified import shim as llm_review.py — this
# module is reached from both sys.path shapes (see llm_review.py's header
# comment for why neither can be dropped).
try:  # bare: this directory is on sys.path
    from external_review_degraded import MAX_OUTPUT_TOKENS, classify_reply, openai_finish_reason
except ModuleNotFoundError as exc:  # package-qualified: shared/scripts is on sys.path
    if exc.name != "external_review_degraded":
        raise
    from lib.external_review_degraded import (  # type: ignore[no-redef]
        MAX_OUTPUT_TOKENS,
        classify_reply,
        openai_finish_reason,
    )

GATEWAY_BASE_URL_ENV = "SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL"
_HEADER_ENV_PREFIX = "SHIPWRIGHT_REVIEW_GATEWAY_HEADER_"
_LOCAL_TEST_HOSTS = frozenset({"localhost", "127.0.0.1"})


def _is_secure_base_url(base_url: str) -> bool:
    """https only, with a narrow local-testing exception.

    Review prompts and the gateway key travel to this URL — plain http
    would send both across the network in plaintext. localhost/127.0.0.1
    are exempted so a local mock gateway can be tested without TLS.
    """
    parsed = urlparse(base_url)
    if parsed.scheme == "https" and parsed.hostname:
        return True
    return parsed.scheme == "http" and parsed.hostname in _LOCAL_TEST_HOSTS


def _sanitize_url_for_display(url: str) -> str:
    """Scheme + host + path only — no userinfo (``user:pass@``) or query
    string, either of which can carry credentials (basic-auth, a token query
    param). Safe to put in an error message.
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunparse((parsed.scheme, host, parsed.path, "", "", ""))


def _url_secret_parts(url: str) -> list[str]:
    """The literal substrings of ``url`` that can carry credentials: the
    ``user:pass`` userinfo before ``@``, and the raw query string.
    """
    parsed = urlparse(url)
    parts = []
    if "@" in parsed.netloc:
        parts.append(parsed.netloc.split("@", 1)[0])
    if parsed.query:
        parts.append(parsed.query)
    return parts


def gateway_configured() -> bool:
    """True iff the operator has pointed review traffic at a gateway.

    Exclusive once true — see this module's docstring.
    """
    return bool(os.environ.get(GATEWAY_BASE_URL_ENV, "").strip())


def gateway_headers() -> dict[str, str]:
    """Collect ``SHIPWRIGHT_REVIEW_GATEWAY_HEADER_<NAME>`` env vars.

    Arbitrarily many are supported (e.g. a WAF auth header). ``<NAME>``
    becomes the HTTP header name with underscores turned into hyphens; HTTP
    header names are case-insensitive so the all-caps env-var casing is
    functionally fine as sent.
    """
    headers: dict[str, str] = {}
    for key, value in os.environ.items():
        if key.startswith(_HEADER_ENV_PREFIX) and value.strip():
            header_name = key[len(_HEADER_ENV_PREFIX):].replace("_", "-")
            if header_name:  # bare SHIPWRIGHT_REVIEW_GATEWAY_HEADER_ (empty suffix) is ignored
                headers[header_name] = value
    return headers


_REDACTED = "***redacted***"


def _redact_secrets(text: str, *secrets: str) -> str:
    """Strip configured secret values out of an error message before it is
    returned — this route's error ``reason`` can be persisted to disk by a
    caller (``review_assistant_ui_plan.py`` writes ``reason`` for any
    non-success leg into its output markdown). A misbehaving gateway/proxy
    that echoes request details (headers, auth) back in an error body must
    not leak them into that artifact.

    Exact-substring match only — a gateway that echoes a secret back
    re-encoded (different casing, URL-encoded, partially masked) will not
    be caught. Accepted as a known limitation: a heuristic/regex redaction
    would itself be unreliable, and this still closes the direct-echo case,
    which is what a misconfigured proxy actually does in practice.
    """
    for secret in secrets:
        if secret:
            text = text.replace(secret, _REDACTED)
    return text


def redact_all_configured_secrets(text: str) -> str:
    """Defense-in-depth redaction using EVERY configured gateway secret
    (both slots' keys, all headers) — not scoped to one leg's config.

    ``review_gateway()``'s own try/except already redacts using that leg's
    specific secrets. This is for the caller-side fallback catch in
    ``llm_review.run_review()``'s executor loop, which has no access to a
    specific leg's secrets if ``review_gateway`` ever raises past its own
    handling (currently only possible via a future edit that adds
    secret-touching logic before that function's ``try:`` — not reachable
    today, but the redaction gap would be silent if it ever became so).
    """
    secrets = [
        os.environ.get("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1", "").strip(),
        os.environ.get("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_2", "").strip(),
        *gateway_headers().values(),
        *_url_secret_parts(os.environ.get(GATEWAY_BASE_URL_ENV, "").strip()),
    ]
    return _redact_secrets(text, *secrets)


def review_gateway(
    content: str, context: str, system_prompt: str, user_prompt: str,
    slot: str, timeout: int,
) -> dict:
    """Send content for review via an operator-owned OpenAI-compatible gateway.

    ``slot`` is ``"1"`` or ``"2"``, selecting
    ``SHIPWRIGHT_REVIEW_GATEWAY_MODEL_<slot>`` /
    ``SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_<slot>``. Any model name configured
    for a slot is passed straight through, unvalidated — no identity lock.

    The actually-answering model, when the API response reports one, is
    captured under ``answering_model`` — separate from the caller's
    "model-1"/"model-2" role label — so the record never implies an
    identity the gateway didn't use.
    """
    base_url = os.environ.get(GATEWAY_BASE_URL_ENV, "").strip()
    model = os.environ.get(f"SHIPWRIGHT_REVIEW_GATEWAY_MODEL_{slot}", "").strip()
    api_key = os.environ.get(f"SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_{slot}", "").strip()

    if not model:
        return {
            "status": "error",
            "reason": f"SHIPWRIGHT_REVIEW_GATEWAY_MODEL_{slot} not set",
        }
    if not api_key:
        return {
            "status": "error",
            "reason": f"SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_{slot} not set",
        }
    if not _is_secure_base_url(base_url):
        return {
            "status": "error",
            "reason": (
                f"{GATEWAY_BASE_URL_ENV} must be an https:// URL (or "
                "http://localhost / http://127.0.0.1 for local testing) — "
                # Sanitized, never the raw configured URL: it may itself
                # carry credentials (basic-auth userinfo, a token query
                # param) that must not land in a persisted error artifact.
                f"got {_sanitize_url_for_display(base_url)!r}. Review "
                "prompts and the gateway key would otherwise cross the "
                "network in plaintext."
            ),
        }

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            default_headers=gateway_headers() or None,
        )
        prompt = user_prompt.replace("{CONTENT}", content).replace("{CONTEXT}", context)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=MAX_OUTPUT_TOKENS,
        )
        result = classify_reply(
            response.choices[0].message.content,
            openai_finish_reason(response),
            via="gateway",
        )
        answering_model = getattr(response, "model", None)
        if answering_model:
            result["answering_model"] = answering_model
        return result

    except ImportError:
        return {"status": "error", "reason": "openai package not installed"}
    except Exception as e:
        reason = _redact_secrets(
            str(e), api_key, *gateway_headers().values(), *_url_secret_parts(base_url)
        )
        return {"status": "error", "reason": reason}
