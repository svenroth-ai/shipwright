"""External LLM review client — DeepSeek + OpenAI, plus an operator-owned gateway.

Shared by plan and build plugins for external code/plan review.

Supports four routes:
1. Gateway (operator-owned, exclusive when configured — see
   external_review_gateway.py): any OpenAI-compatible gateway via
   SHIPWRIGHT_REVIEW_GATEWAY_* env vars. No identity lock, no ZDR check.
2. OpenRouter / 3. Direct OpenAI (identity-locked — see
   external_review_default_legs.py): single OPENROUTER_API_KEY covers both
   models; OPENAI_API_KEY alone runs the GPT arm only (DeepSeek always
   requires the approved OpenRouter ZDR route).
4. Skip: no keys → review skipped gracefully

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
    from external_review_degraded import DEFAULT_TIMEOUT_SECONDS
    from external_review_config import load_review_config
    from external_review_default_legs import (
        review_openai as _review_openai,
        review_openrouter as _review_openrouter,
    )
    from external_review_gateway import (
        gateway_configured,
        redact_all_configured_secrets,
        review_gateway as _review_gateway,
    )
except ModuleNotFoundError as exc:  # package-qualified: shared/scripts is on sys.path
    if exc.name != "external_review_degraded":
        raise
    from lib.external_review_degraded import DEFAULT_TIMEOUT_SECONDS  # type: ignore[no-redef]
    from lib.external_review_config import load_review_config  # type: ignore[no-redef]
    from lib.external_review_default_legs import (  # type: ignore[no-redef]
        review_openai as _review_openai,
        review_openrouter as _review_openrouter,
    )
    from lib.external_review_gateway import (  # type: ignore[no-redef]
        gateway_configured,
        redact_all_configured_secrets,
        review_gateway as _review_gateway,
    )


# Identity-locked model bindings. The shipping config must match exactly.
DEFAULT_MODELS = {
    "openrouter_deepseek": "deepseek/deepseek-v4-pro",
    "openrouter_chatgpt": "openai/gpt-5.6-terra",
    "chatgpt": "gpt-5.6-terra",
}


def detect_provider() -> str:
    """Detect which review provider to use.

    Fallback chain: gateway → openrouter → direct → none. Gateway is
    exclusive once configured — see module docstring and ``run_review``.
    """
    if gateway_configured():
        return "gateway"
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

    if provider == "gateway":
        # Exclusive — no fallback to openrouter/direct below (module docstring).
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(
                    _review_gateway, content, context, system_prompt, user_prompt, "1", timeout
                ): "model-1",
                executor.submit(
                    _review_gateway, content, context, system_prompt, user_prompt, "2", timeout
                ): "model-2",
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    reviews[name] = future.result()
                except Exception as e:
                    # review_gateway() redacts internally; this is defense in depth only.
                    reviews[name] = {"status": "error", "reason": redact_all_configured_secrets(str(e))}

    elif provider == "openrouter":
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
