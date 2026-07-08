#!/usr/bin/env python3
"""External LLM review CLI — Gemini + OpenAI in parallel (shared across plugins).

Supports three review providers:
1. OpenRouter (recommended): one OPENROUTER_API_KEY for both models
2. Direct keys: GEMINI_API_KEY + OPENAI_API_KEY separately
3. Skip: no keys → review skipped gracefully

Fallback chain: OpenRouter → direct keys → skip

Usage (plan / iterate modes):
    uv run shared/scripts/tools/external_review.py \\
        --mode plan|iterate \\
        --plan-file <path> \\
        --spec-file <path> \\
        --plugin-root <path>

Usage (code-review mode):
    uv run shared/scripts/tools/external_review.py \\
        --mode code \\
        --diff-file <path> \\
        --spec-file <path> \\
        --plugin-root <path>

The ``--plugin-root`` argument is used for plan-mode prompt loading
(plan_reviewer prompts stay plugin-local). Iterate-mode prompts come from
shared/prompts/iterate_reviewer/, code-mode prompts from
shared/prompts/code_reviewer/, regardless of plugin-root.

Mode → primary-input mapping:
- ``plan``    → ``--plan-file`` (full implementation plan vs project spec)
- ``iterate`` → ``--plan-file`` (mini-plan vs iterate spec)
- ``code``    → ``--diff-file`` (code diff vs section/iterate spec)

Output (JSON):
    {
        "success": true/false,
        "provider": "openrouter" | "direct" | "none",
        "skipped": "empty_diff",  // optional, code-mode only
        "reviews": {
            "gemini": { "status": "success|error|skipped", "feedback": "..." },
            "openai": { "status": "success|error|skipped", "feedback": "..." }
        }
    }

This is the consolidated successor of
``plugins/shipwright-plan/scripts/llm_clients/review.py`` — the logic is
copied verbatim except for the import paths, model resolution (now goes
through ``resolve_model`` for env-var override support), and prompt loading
(per-mode helpers from ``lib.external_review_prompts``).
"""

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Wire up shared/scripts/lib so we can import shared helpers + the env loader.
# parents[0]=tools, [1]=scripts, [2]=shared.
_SHARED_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_SHARED_LIB) not in sys.path:
    sys.path.insert(0, str(_SHARED_LIB))

from env import load_shipwright_env  # type: ignore[import-not-found]

load_shipwright_env()

from external_review_config import load_review_config, resolve_model  # noqa: E402
from external_review_degraded import finalize_review_output  # noqa: E402
from external_review_prompts import (  # noqa: E402
    load_code_review_prompts,
    load_iterate_review_prompts,
    load_plan_review_prompts,
)


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


_KNOWN_PLACEHOLDERS = ("{PLAN}", "{DIFF}", "{SPEC}")
_PLACEHOLDER_RE = re.compile(r"\{[A-Z][A-Z_]*\}")


def _render_user_prompt(user_prompt: str, primary: str, spec: str) -> str:
    """Substitute placeholders into the user prompt template.

    Both ``{PLAN}`` and ``{DIFF}`` are replaced with ``primary`` — whichever
    token the active mode's template uses wins, the other is a no-op.
    Plan/iterate templates use ``{PLAN}``; code-mode templates use ``{DIFF}``.

    Emits a stderr warning if the template contains an unknown placeholder
    (catches developer error when adding a new mode without updating this
    helper). The check inspects the template, NOT the rendered output, so
    diff/spec content that happens to contain literal ``{PLAN}/{DIFF}/{SPEC}``
    strings does not produce false positives.
    """
    for token in _PLACEHOLDER_RE.findall(user_prompt):
        if token not in _KNOWN_PLACEHOLDERS:
            print(
                f"warning: external_review prompt template contains unknown placeholder {token}",
                file=sys.stderr,
            )
    return (
        user_prompt
        .replace("{PLAN}", primary)
        .replace("{DIFF}", primary)
        .replace("{SPEC}", spec)
    )


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

        if model_key == "gemini":
            model_name = resolve_model(config, "openrouter_gemini")
        else:
            model_name = resolve_model(config, "openrouter_chatgpt")

        timeout = config.get("llm_client", {}).get("timeout_seconds", 120)

        client = OpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
            timeout=timeout,
        )

        prompt = _render_user_prompt(user_prompt, plan, spec)

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

        model_name = resolve_model(config, "gemini")
        client = genai.Client(api_key=api_key)

        prompt = _render_user_prompt(user_prompt, plan, spec)

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

        model_name = resolve_model(config, "chatgpt")
        timeout = config.get("llm_client", {}).get("timeout_seconds", 120)

        client = OpenAI(api_key=api_key, timeout=timeout)

        prompt = _render_user_prompt(user_prompt, plan, spec)

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            # gpt-5.x rejects `max_tokens`; `max_completion_tokens` is required.
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="External LLM plan / iterate / code review",
    )
    # Plan & iterate modes use --plan-file. Code mode uses --diff-file. Both
    # are non-required at parse time so a single CLI shape can serve all
    # three modes; mode-specific validation happens after parse.
    parser.add_argument(
        "--plan-file",
        required=False,
        help="Path to plan.md or mini-plan (required for --mode plan|iterate)",
    )
    parser.add_argument(
        "--diff-file",
        required=False,
        help="Path to a code diff (required for --mode code)",
    )
    parser.add_argument(
        "--spec-file",
        required=True,
        help="Path to spec.md, iterate spec, or section context",
    )
    parser.add_argument(
        "--plugin-root",
        required=True,
        help="Path to the calling plugin root (used for --mode plan prompt lookup)",
    )
    parser.add_argument(
        "--mode",
        choices=["plan", "iterate", "code"],
        default="plan",
        help=(
            "Review mode: 'plan' (full pipeline plan vs project spec), "
            "'iterate' (lightweight mini-plan vs iterate spec), "
            "or 'code' (code diff vs section/iterate spec)."
        ),
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help=(
            "Project directory used to load shipwright_iterate_config.json "
            "as a per-project override over shared/config/external_review.json. "
            "Defaults to cwd."
        ),
    )
    args = parser.parse_args()

    # Mode-specific argument validation.
    if args.mode == "code":
        if not args.diff_file:
            parser.error("--diff-file is required for --mode code")
        primary_path = Path(args.diff_file)
        primary_label = "Diff"
    else:
        if not args.plan_file:
            parser.error("--plan-file is required for --mode plan|iterate")
        primary_path = Path(args.plan_file)
        primary_label = "Plan"

    spec_path = Path(args.spec_file)

    if not primary_path.exists():
        print(
            json.dumps(
                {"success": False, "error": f"{primary_label} not found: {primary_path}"},
                indent=2,
            )
        )
        return 1

    if not spec_path.exists():
        print(json.dumps({"success": False, "error": f"Spec not found: {spec_path}"}, indent=2))
        return 1

    primary_text = primary_path.read_text(encoding="utf-8")
    spec = spec_path.read_text(encoding="utf-8")

    # Code-mode short-circuit: empty diff → no provider call. The LLM cannot
    # review what isn't there, and many providers reject empty inputs.
    if args.mode == "code" and not primary_text.strip():
        print(json.dumps({
            "success": True,
            "skipped": "empty_diff",
            "provider": "none",
            "degraded": False,
            "reviews": {
                "gemini": {"status": "skipped", "reason": "empty diff"},
                "openai": {"status": "skipped", "reason": "empty diff"},
            },
        }, indent=2))
        return 0

    config = load_review_config(project_root=Path(args.project_root).resolve())

    # Load mode-specific prompts.
    if args.mode == "iterate":
        system_prompt, user_prompt = load_iterate_review_prompts()
    elif args.mode == "code":
        system_prompt, user_prompt = load_code_review_prompts()
    else:
        system_prompt, user_prompt = load_plan_review_prompts(args.plugin_root)

    if not system_prompt:
        if args.mode == "iterate":
            system_prompt = (
                "You are a senior software architect reviewing an implementation approach "
                "for a single change to an existing application."
            )
        elif args.mode == "code":
            system_prompt = (
                "You are a senior software engineer auditing a code change against its "
                "specification. Focus on real defects (correctness, security, regressions, "
                "spec gaps, edge cases). Skip style and naming nits."
            )
        else:
            system_prompt = "You are a senior software architect reviewing an implementation plan."
    if not user_prompt:
        if args.mode == "iterate":
            user_prompt = (
                "Review this implementation approach for a change to an existing application.\n\n"
                "## Change Specification:\n{SPEC}\n\n## Implementation Approach:\n{PLAN}\n\n"
                "Focus on: approach soundness, risks to existing functionality, "
                "missing dependencies, edge cases, and security concerns."
            )
        elif args.mode == "code":
            user_prompt = (
                "Review this code change against its specification.\n\n"
                "## Specification:\n{SPEC}\n\n## Code Diff:\n```diff\n{DIFF}\n```\n\n"
                "Identify concrete defects: spec gaps, correctness bugs, security issues, "
                "test quality, regressions, and unhandled edge cases. "
                "Skip style and naming nits."
            )
        else:
            user_prompt = (
                "Review this implementation plan for a project.\n\n"
                "## Spec:\n{SPEC}\n\n## Plan:\n{PLAN}\n\n"
                "Identify: security issues, performance concerns, architecture problems, "
                "missing features, and edge cases not handled."
            )

    provider = detect_provider()
    reviews: dict[str, dict] = {}

    if provider == "openrouter":
        # Both reviews via OpenRouter (one API key)
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(review_with_openrouter, primary_text, spec, system_prompt, user_prompt, config, "gemini"): "gemini",
                executor.submit(review_with_openrouter, primary_text, spec, system_prompt, user_prompt, config, "openai"): "openai",
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
                executor.submit(review_with_gemini, primary_text, spec, system_prompt, user_prompt, config): "gemini",
                executor.submit(review_with_openai, primary_text, spec, system_prompt, user_prompt, config): "openai",
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    reviews[name] = future.result()
                except Exception as e:
                    reviews[name] = {"status": "error", "reason": str(e)}

    else:
        # No keys — both reviews skipped
        reviews = {
            "gemini": {"status": "skipped", "reason": "No GEMINI_API_KEY or OPENROUTER_API_KEY set"},
            "openai": {"status": "skipped", "reason": "No OPENAI_API_KEY or OPENROUTER_API_KEY set"},
        }

    # Degraded-gate: keys present but 0 reviews succeeded → fail loud (never a silent no-op).
    output, exit_code = finalize_review_output(provider, reviews)
    print(json.dumps(output, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
