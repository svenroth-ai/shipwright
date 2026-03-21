#!/usr/bin/env python3
"""External LLM plan review — Gemini + OpenAI in parallel.

Supports three review providers:
1. OpenRouter (recommended): one OPENROUTER_API_KEY for both models
2. Direct keys: GEMINI_API_KEY + OPENAI_API_KEY separately
3. Skip: no keys → review skipped gracefully

Fallback chain: OpenRouter → direct keys → skip

Usage:
    uv run review.py --plan-file <path> --spec-file <path> --plugin-root <path>

Output (JSON):
    {
        "success": true/false,
        "provider": "openrouter" | "direct" | "none",
        "reviews": {
            "gemini": { "status": "success|error|skipped", "feedback": "..." },
            "openai": { "status": "success|error|skipped", "feedback": "..." }
        }
    }
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.config import load_global_config
from lib.prompts import load_review_prompts

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def review_with_openrouter(
    plan: str, spec: str, system_prompt: str, user_prompt: str,
    config: dict, model_key: str,
) -> dict:
    """Send plan for review via OpenRouter (OpenAI-compatible API)."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return {"status": "skipped", "reason": "No OPENROUTER_API_KEY set"}

    try:
        from openai import OpenAI

        models = config.get("models", {})
        if model_key == "gemini":
            model_name = models.get("openrouter_gemini", "google/gemini-2.5-pro-preview")
        else:
            model_name = models.get("openrouter_chatgpt", "openai/gpt-4.1")

        timeout = config.get("llm_client", {}).get("timeout_seconds", 120)

        client = OpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
            timeout=timeout,
        )

        prompt = user_prompt.replace("{PLAN}", plan).replace("{SPEC}", spec)

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


def review_with_gemini(
    plan: str, spec: str, system_prompt: str, user_prompt: str, config: dict
) -> dict:
    """Send plan for review to Gemini (direct API)."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {"status": "skipped", "reason": "No GEMINI_API_KEY set"}

    try:
        from google import genai

        model_name = config.get("models", {}).get("gemini", "gemini-3-pro-preview")
        client = genai.Client(api_key=api_key)

        prompt = user_prompt.replace("{PLAN}", plan).replace("{SPEC}", spec)

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


def review_with_openai(
    plan: str, spec: str, system_prompt: str, user_prompt: str, config: dict
) -> dict:
    """Send plan for review to OpenAI (direct API)."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"status": "skipped", "reason": "No OPENAI_API_KEY set"}

    try:
        from openai import OpenAI

        model_name = config.get("models", {}).get("chatgpt", "gpt-5.2")
        timeout = config.get("llm_client", {}).get("timeout_seconds", 120)

        client = OpenAI(api_key=api_key, timeout=timeout)

        prompt = user_prompt.replace("{PLAN}", plan).replace("{SPEC}", spec)

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4096,
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


def main() -> int:
    parser = argparse.ArgumentParser(description="External LLM plan review")
    parser.add_argument("--plan-file", required=True, help="Path to plan.md")
    parser.add_argument("--spec-file", required=True, help="Path to spec.md")
    parser.add_argument("--plugin-root", required=True, help="Path to plugin root")
    args = parser.parse_args()

    plan_path = Path(args.plan_file)
    spec_path = Path(args.spec_file)

    if not plan_path.exists():
        print(json.dumps({"success": False, "error": f"Plan not found: {plan_path}"}, indent=2))
        return 1

    if not spec_path.exists():
        print(json.dumps({"success": False, "error": f"Spec not found: {spec_path}"}, indent=2))
        return 1

    plan = plan_path.read_text(encoding="utf-8")
    spec = spec_path.read_text(encoding="utf-8")

    config = load_global_config(args.plugin_root)
    system_prompt, user_prompt = load_review_prompts(args.plugin_root)

    if not system_prompt:
        system_prompt = "You are a senior software architect reviewing an implementation plan."
    if not user_prompt:
        user_prompt = (
            "Review this implementation plan for a project.\n\n"
            "## Spec:\n{SPEC}\n\n## Plan:\n{PLAN}\n\n"
            "Identify: security issues, performance concerns, architecture problems, "
            "missing features, and edge cases not handled."
        )

    provider = detect_provider()
    reviews = {}

    if provider == "openrouter":
        # Both reviews via OpenRouter (one API key)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(review_with_openrouter, plan, spec, system_prompt, user_prompt, config, "gemini"): "gemini",
                executor.submit(review_with_openrouter, plan, spec, system_prompt, user_prompt, config, "openai"): "openai",
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    reviews[name] = future.result()
                except Exception as e:
                    reviews[name] = {"status": "error", "reason": str(e)}

    elif provider == "direct":
        # Direct API keys (original behavior)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(review_with_gemini, plan, spec, system_prompt, user_prompt, config): "gemini",
                executor.submit(review_with_openai, plan, spec, system_prompt, user_prompt, config): "openai",
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

    any_success = any(r.get("status") == "success" for r in reviews.values())

    print(json.dumps({
        "success": any_success,
        "provider": provider,
        "reviews": reviews,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
