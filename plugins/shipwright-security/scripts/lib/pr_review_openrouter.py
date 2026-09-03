"""The OpenRouter HTTP boundary for the Tier-3 PR reviewer.

The second of the tool's two I/O boundaries — `pr_review_gh` owns the subprocess
one. Both are split out of `pr_review.py` so it holds orchestration only and
stays under the source-size guideline, and so each boundary (with its timeout,
its error mapping and, here, its Semgrep suppression) is reviewable on its own.

Stdlib urllib only: the script carries no third-party HTTP dependency and runs
under whatever environment `uv run` resolves on the CI runner.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

__all__ = [
    "DEEPSEEK_MODEL",
    "DEFAULT_MODEL",
    "DEFAULT_TIMEOUT",
    "GLM_MODEL",
    "LUNA_MODEL",
    "OPENROUTER_URL",
    "call_openrouter",
]

# One named constant — DEFAULT_MODEL, the ZDR-routing model match, and every
# test/workflow assertion all read this, so they cannot drift into three
# copies of the same literal. DeepSeek and GLM stay available as operator
# overrides (SHIPWRIGHT_PR_REVIEW_MODEL): DeepSeek after repeated confident
# false-positive BLOCK verdicts motivated the GLM 5.3 default switch
# (iterate-2026-09-01-pr-review-glm-model); GLM 5.3 itself was then found to
# silently hang mid-review (no exception, no timeout — a bare stall on the
# `novita` ZDR endpoint, ~90-170s then a bare process exit) on shipwright
# webui PR #416, reproducible 4x on the same diff while sibling PRs on the
# same model succeeded in the same window — an AVAILABILITY defect in the
# `allow_fallbacks: false` ZDR provider pool (only novita+together, no
# fallback), not a model-quality one. GPT-5.6 Luna needs no ZDR routing
# constraint at all (outside the deepseek/z-ai namespaces,
# `resolve_extra_body` short-circuits to `{}`), so it keeps OpenRouter's
# normal multi-host failover (OpenAI, Azure EU, Amazon Bedrock US — 3
# independent hosts, not 2 resellers with no fallback) instead of the ZDR
# pool's single point of failure. Chosen over a same-family Sonnet-5 rollback
# on cost: near-identical coding-review quality (SWE-bench Pro 62.7 vs 63.2,
# AA Intelligence Index 51 vs 53) at roughly 1/15th the OpenRouter price
# (iterate-2026-09-03-pr-review-sonnet-default — run-id kept for history, the
# swap landed on Luna, not Sonnet, after an empirical benchmark/price check
# mid-run).
DEEPSEEK_MODEL = "deepseek/deepseek-v4-pro"
GLM_MODEL = "z-ai/glm-5.3"
LUNA_MODEL = "openai/gpt-5.6-luna"
DEFAULT_MODEL = LUNA_MODEL
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# ONE default for the whole tool — the CLI flag and the direct call share it.
# 120s was sized for a 200k-char cap. The cap is now 1M chars (~250k input
# tokens) and the request is non-streaming, so a single blocking read must cover
# prompt processing AND generation. A socket timeout maps to EXIT_ERROR — still
# fail-closed, but it lands on exactly the large PRs the raise exists to
# unblock, and it returns before any comment is posted.
DEFAULT_TIMEOUT = 600


def _post_openrouter(api_key: str, model: str, messages: list[dict], timeout: int,
                      *, extra_body: dict | None = None) -> dict:
    """POST the chat-completion request and return the parsed JSON body.

    `extra_body` (e.g. a DeepSeek ZDR provider-routing constraint) is merged
    UNDER the transport's own keys — `{**extra_body, **payload}`, not the
    reverse — so a config-derived dict can never overwrite `model`,
    `messages`, or `response_format`, even if it later grows a colliding key.
    """
    payload = {**(extra_body or {}), "model": model, "messages": messages,
               "response_format": {"type": "json_object"}}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # OpenRouter attribution headers (optional, recommended).
            "HTTP-Referer": "https://github.com/svenroth-ai/shipwright",
            "X-Title": "Shipwright PR Review",
        },
        method="POST",
    )
    # OPENROUTER_URL is a fixed `https://` module constant; no user/dynamic input reaches
    # the request URL, so the dynamic-scheme (`file://`) / SSRF concern this Semgrep rule
    # guards against cannot occur here — confirmed false positive, suppressed on the match line.
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        body = resp.read().decode("utf-8")
    return json.loads(body)


def call_openrouter(api_key: str, model: str, messages: list[dict],
                    timeout: int = DEFAULT_TIMEOUT, *,
                    extra_body: dict | None = None) -> str:
    """Call OpenRouter and return the assistant message content string.

    Raises RuntimeError on transport failure (HTTP error, timeout) or an
    unexpected response shape — the caller maps that to exit 2.
    """
    try:
        data = _post_openrouter(api_key, model, messages, timeout, extra_body=extra_body)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 — best-effort body read
            pass
        raise RuntimeError(f"OpenRouter HTTP {e.code}: {detail}") from e
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        raise RuntimeError(f"OpenRouter request failed: {e}") from e
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"unexpected OpenRouter response shape: {e}") from e
