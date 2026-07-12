"""External LLM review client — Gemini + OpenAI via OpenRouter or direct keys.

Shared by plan and build plugins for external code/plan review.

Supports three providers:
1. OpenRouter (recommended): single OPENROUTER_API_KEY for both models
2. Direct keys: GEMINI_API_KEY + OPENAI_API_KEY separately
3. Skip: no keys → review skipped gracefully

Usage:
    from lib.llm_review import run_review

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


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Default models — can be overridden via config dict
DEFAULT_MODELS = {
    "openrouter_gemini": "google/gemini-3.1-pro-preview",
    "openrouter_chatgpt": "openai/gpt-5.6-terra-pro",
    "gemini": "gemini-3.1-pro-preview",
    "chatgpt": "gpt-5.6-terra-pro",
}


def _review_openrouter(
    content: str, context: str, system_prompt: str, user_prompt: str,
    models: dict, model_key: str, timeout: int,
) -> dict:
    """Send content for review via OpenRouter."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return {"status": "skipped", "reason": "No OPENROUTER_API_KEY set"}

    try:
        from openai import OpenAI

        if model_key == "gemini":
            model_name = models.get("openrouter_gemini", DEFAULT_MODELS["openrouter_gemini"])
        else:
            model_name = models.get("openrouter_chatgpt", DEFAULT_MODELS["openrouter_chatgpt"])

        client = OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL, timeout=timeout)
        prompt = user_prompt.replace("{CONTENT}", content).replace("{CONTEXT}", context)

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4096,
        )
        return {"status": "success", "feedback": response.choices[0].message.content, "via": "openrouter"}

    except ImportError:
        return {"status": "error", "reason": "openai package not installed"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}


def _review_gemini(
    content: str, context: str, system_prompt: str, user_prompt: str,
    models: dict, timeout: int,
) -> dict:
    """Send content for review to Gemini (direct API)."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {"status": "skipped", "reason": "No GEMINI_API_KEY set"}

    try:
        from google import genai

        model_name = models.get("gemini", DEFAULT_MODELS["gemini"])
        client = genai.Client(api_key=api_key)
        prompt = user_prompt.replace("{CONTENT}", content).replace("{CONTEXT}", context)

        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=4096,
            ),
        )
        return {"status": "success", "feedback": response.text, "via": "direct"}

    except ImportError:
        return {"status": "error", "reason": "google-genai package not installed"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}


def _review_openai(
    content: str, context: str, system_prompt: str, user_prompt: str,
    models: dict, timeout: int,
) -> dict:
    """Send content for review to OpenAI (direct API)."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"status": "skipped", "reason": "No OPENAI_API_KEY set"}

    try:
        from openai import OpenAI

        model_name = models.get("chatgpt", DEFAULT_MODELS["chatgpt"])
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
            max_completion_tokens=4096,
        )
        return {"status": "success", "feedback": response.choices[0].message.content, "via": "direct"}

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
    has_gemini = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    if has_gemini or has_openai:
        return "direct"
    return "none"


def run_review(
    content: str,
    context: str,
    system_prompt: str | None = None,
    user_prompt: str | None = None,
    models: dict | None = None,
    timeout: int = 120,
) -> dict:
    """Run external LLM review with Gemini + OpenAI in parallel.

    Args:
        content: The code diff, plan, or text to review.
        context: Supporting context (spec, section plan, etc.).
        system_prompt: System prompt for the reviewer.
        user_prompt: User prompt template with {CONTENT} and {CONTEXT} placeholders.
        models: Model name overrides (optional).
        timeout: API timeout in seconds.

    Returns:
        {"success": bool, "provider": str, "reviews": {"gemini": {...}, "openai": {...}}}
    """
    if not system_prompt:
        system_prompt = "You are a senior software engineer reviewing code for quality, security, and correctness."
    if not user_prompt:
        user_prompt = (
            "Review this code change.\n\n"
            "## Context:\n{CONTEXT}\n\n## Code:\n{CONTENT}\n\n"
            "Identify: security issues, bugs, performance concerns, and missed edge cases."
        )

    models = models or DEFAULT_MODELS
    provider = detect_provider()
    reviews: dict[str, dict] = {}

    if provider == "openrouter":
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(
                    _review_openrouter, content, context, system_prompt, user_prompt, models, "gemini", timeout
                ): "gemini",
                executor.submit(
                    _review_openrouter, content, context, system_prompt, user_prompt, models, "openai", timeout
                ): "openai",
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    reviews[name] = future.result()
                except Exception as e:
                    reviews[name] = {"status": "error", "reason": str(e)}

    elif provider == "direct":
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(
                    _review_gemini, content, context, system_prompt, user_prompt, models, timeout
                ): "gemini",
                executor.submit(
                    _review_openai, content, context, system_prompt, user_prompt, models, timeout
                ): "openai",
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    reviews[name] = future.result()
                except Exception as e:
                    reviews[name] = {"status": "error", "reason": str(e)}

    else:
        reviews = {
            "gemini": {"status": "skipped", "reason": "No API keys configured"},
            "openai": {"status": "skipped", "reason": "No API keys configured"},
        }

    return {
        "success": any(r.get("status") == "success" for r in reviews.values()),
        "provider": provider,
        "reviews": reviews,
    }
