"""External LLM review client — DeepSeek + OpenAI.

Shared by plan and build plugins for external code/plan review.

Supports three routes:
1. OpenRouter (recommended): single OPENROUTER_API_KEY for both models
2. Direct OpenAI: DeepSeek is unavailable; GPT keeps its direct route
3. Skip: no keys → review skipped gracefully

Usage — BOTH import names are live and supported (see the import block below):

    from lib.llm_review import run_review   # shared/scripts on sys.path
    from llm_review import run_review       # this directory on sys.path

    result = run_review(
        content="<code diff or plan>",
        context="<spec or section spec>",
        system_prompt="You are a reviewer...",
        user_prompt="Review this:\n{CONTENT}\n\nContext:\n{CONTEXT}",
    )
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# This module is imported under TWO names and both are live:
#   * bare ``import llm_review``      — shipwright-adopt's Layer-3 review_runner,
#                                       after putting this directory on sys.path
#   * ``from lib.llm_review import …`` — shared/scripts/tools/review_assistant_ui_plan.py
# A bare sibling import works only in the first case (ModuleNotFoundError in the
# second); a ``lib.``-qualified one works only in the second. Try both rather
# than mutating sys.path, which is a process-global side effect that would
# change module resolution for every later import in the host process.
#
# TWO things this does NOT close, stated rather than implied:
#   * The ``try`` branch trusts sys.path ORDER. In a process where another tree
#     carrying a same-named module sits ahead of this directory, it binds that
#     one silently and the ``except`` never fires. Accepted here because no
#     such duplicate exists in this repo and the alternative — a sentinel
#     spec_from_file_location loader, as in adopt's ``review_runner._discovery``
#     — would break the ``_import_genai`` monkeypatch seam the tests rely on.
#   * ``ModuleNotFoundError`` is used rather than ``ImportError`` on purpose: a
#     PARTIAL or stale sibling (present, but missing a name) must fail loudly
#     with its real message instead of silently retrying under the other name
#     and possibly binding a second copy of the module this file exists to keep
#     in lockstep. The plugin cache is documented to go stale that way.
try:  # bare: this directory is on sys.path
    from external_review_degraded import (
        DEFAULT_TIMEOUT_SECONDS,
        MAX_OUTPUT_TOKENS,
        classify_reply,
        openai_finish_reason,
    )
    from external_review_config import load_review_config
    from external_review_routing import openrouter_extra_body, resolve_reviewer_model
except ModuleNotFoundError as exc:  # package-qualified: shared/scripts is on sys.path
    if exc.name != "external_review_degraded":
        raise
    from lib.external_review_degraded import (  # type: ignore[no-redef]
        DEFAULT_TIMEOUT_SECONDS,
        MAX_OUTPUT_TOKENS,
        classify_reply,
        openai_finish_reason,
    )
    from lib.external_review_config import load_review_config  # type: ignore[no-redef]
    from lib.external_review_routing import (  # type: ignore[no-redef]
        openrouter_extra_body,
        resolve_reviewer_model,
    )


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Identity-locked model bindings. The shipping config must match exactly.
DEFAULT_MODELS = {
    "openrouter_deepseek": "deepseek/deepseek-v4-pro",
    "openrouter_chatgpt": "openai/gpt-5.6-terra",
    "chatgpt": "gpt-5.6-terra",
}


def _review_openrouter(
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

def _review_openai(
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


def detect_provider() -> str:
    """Detect which review provider to use.

    Fallback chain: openrouter → direct → none
    """
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.environ.get("OPENAI_API_KEY"):
        return "direct"
    return "none"


def run_review(
    content: str,
    context: str,
    system_prompt: str | None = None,
    user_prompt: str | None = None,
    models: dict | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """Run external LLM review with DeepSeek + OpenAI in parallel.

    Args:
        content: The code diff, plan, or text to review.
        context: Supporting context (spec, section plan, etc.).
        system_prompt: System prompt for the reviewer.
        user_prompt: User prompt template with {CONTENT} and {CONTEXT} placeholders.
        models: Optional model declarations. Values must exactly match the
            identity-locked bindings; differing values fail before client
            construction.
        timeout: API timeout in seconds.

    Returns usable ``success`` plus ``partial`` / ``warnings``: one complete
    leg remains usable without representing a degraded peer as a clean pass.
    """
    if not system_prompt:
        system_prompt = "You are a senior software engineer reviewing code for quality, security, and correctness."
    if not user_prompt:
        user_prompt = (
            "Review this code change.\n\n"
            "## Context:\n{CONTEXT}\n\n## Code:\n{CONTENT}\n\n"
            "Identify: security issues, bugs, performance concerns, and missed edge cases."
        )

    config = load_review_config()
    if models is not None:
        config = {
            **config,
            "models": {**config.get("models", {}), **models},
        }
    provider = detect_provider()
    reviews: dict[str, dict] = {}

    if provider == "openrouter":
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(
                    _review_openrouter, content, context, system_prompt, user_prompt, config, "deepseek", timeout
                ): "deepseek",
                executor.submit(
                    _review_openrouter, content, context, system_prompt, user_prompt, config, "openai", timeout
                ): "openai",
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    reviews[name] = future.result()
                except Exception as e:
                    reviews[name] = {"status": "error", "reason": str(e)}

    elif provider == "direct":
        reviews = {
            "deepseek": {
                "status": "skipped",
                "reason": "DeepSeek requires an approved OpenRouter ZDR endpoint",
            },
            "openai": _review_openai(
                content, context, system_prompt, user_prompt,
                config, timeout,
            ),
        }

    else:
        reviews = {
            "deepseek": {"status": "skipped", "reason": "No OPENROUTER_API_KEY set"},
            "openai": {"status": "skipped", "reason": "No API keys configured"},
        }

    success = any(r.get("status") == "success" for r in reviews.values())
    warnings = [
        f"{name}: {r['reasoning_cap_dropped']}"
        for name, r in reviews.items() if r.get("reasoning_cap_dropped")
    ]
    non_success = [
        (name, str(review.get("status") or "unknown"))
        for name, review in reviews.items()
        if review.get("status") != "success"
    ]
    if success:
        warnings.extend(
            f"{name}: reviewer arm {status}" for name, status in non_success
        )
    partial = success and bool(warnings)
    return {
        "success": success,
        "partial": partial,
        "warnings": warnings,
        "provider": provider,
        "reviews": reviews,
    }
