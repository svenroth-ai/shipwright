"""The two locked-down review legs: OpenRouter and direct OpenAI.

Split out of ``llm_review.py`` (keeping it under the 300-line guideline)
alongside the sibling ``external_review_gateway.py`` split. Both legs here
are identity-locked — ``resolve_reviewer_model``/``openrouter_extra_body``
enforce the fixed DeepSeek/OpenAI bindings and the DeepSeek ZDR allowlist —
in deliberate contrast to the gateway leg, which carries neither.
"""

from __future__ import annotations

import os

try:  # bare: this directory is on sys.path
    from external_review_degraded import MAX_OUTPUT_TOKENS, classify_reply, openai_finish_reason
    from external_review_routing import openrouter_extra_body, resolve_reviewer_model
except ModuleNotFoundError as exc:  # package-qualified: shared/scripts is on sys.path
    if exc.name != "external_review_degraded":
        raise
    from lib.external_review_degraded import (  # type: ignore[no-redef]
        MAX_OUTPUT_TOKENS,
        classify_reply,
        openai_finish_reason,
    )
    from lib.external_review_routing import (  # type: ignore[no-redef]
        openrouter_extra_body,
        resolve_reviewer_model,
    )

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def review_openrouter(
    content: str, context: str, system_prompt: str, user_prompt: str,
    config: dict, model_key: str, timeout: int,
) -> dict:
    """Send content for review via OpenRouter."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return {"status": "skipped", "reason": "No OPENROUTER_API_KEY set"}

    try:
        from openai import OpenAI

        model_name = resolve_reviewer_model(config, model_key, "openrouter")
        extra_body = openrouter_extra_body(model_key, config)

        client = OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL, timeout=timeout)
        prompt = user_prompt.replace("{CONTENT}", content).replace("{CONTEXT}", context)

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=MAX_OUTPUT_TOKENS,
            extra_body=extra_body,
        )
        return classify_reply(
            response.choices[0].message.content,
            openai_finish_reason(response),
            via="openrouter",
        )

    except ImportError:
        return {"status": "error", "reason": "openai package not installed"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}


def review_openai(
    content: str, context: str, system_prompt: str, user_prompt: str,
    config: dict, timeout: int,
) -> dict:
    """Send content for review to OpenAI (direct API)."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"status": "skipped", "reason": "No OPENAI_API_KEY set"}

    try:
        from openai import OpenAI

        model_name = resolve_reviewer_model(config, "openai", "direct")
        client = OpenAI(api_key=api_key, timeout=timeout)
        prompt = user_prompt.replace("{CONTENT}", content).replace("{CONTEXT}", context)

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            # gpt-5.x rejects `max_tokens` on the direct Chat Completions API;
            # `max_completion_tokens` is the supported replacement.
            max_completion_tokens=MAX_OUTPUT_TOKENS,
        )
        return classify_reply(
            response.choices[0].message.content,
            openai_finish_reason(response),
            via="direct",
        )

    except ImportError:
        return {"status": "error", "reason": "openai package not installed"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}
