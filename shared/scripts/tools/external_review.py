#!/usr/bin/env python3
"""External LLM review CLI — DeepSeek + OpenAI in parallel.

Provider chain (:func:`detect_provider`): OpenRouter (one OPENROUTER_API_KEY for
both models) → direct OpenAI (GPT only; DeepSeek has no direct route) → skip.
DeepSeek never falls back to Gemini or a direct provider.

Usage — every mode takes ``--spec-file``, ``--plugin-root``, exactly ONE input
flag below, and uv's own ``--project <plan plugin root>`` (else ``openai``
silently fails to import outside a project whose own pyproject.toml declares it)::

    uv run --project <shipwright-plan plugin root> \\
        shared/scripts/tools/external_review.py --mode <mode> \\
        <input-flag> <path> --spec-file <path> --plugin-root <path>

Mode → primary-input mapping (the table itself is
:data:`lib.external_review_modes.MODE_INPUT`, which also enforces it — a flag
belonging to another mode is a usage error, never a silent fall-through):

- ``plan``         → ``--plan-file`` (full implementation plan vs project spec)
- ``iterate``      → ``--plan-file`` (mini-plan vs iterate spec)
- ``code``         → ``--diff-file`` (code diff vs section/iterate spec)
- ``architecture`` → ``--brief-file`` (architecture brief vs the spec)

``--plugin-root`` is used for plan-mode prompt loading only (plan_reviewer
prompts stay plugin-local); iterate / code / architecture prompts come from
``shared/prompts/<mode>_reviewer/`` regardless of it.

Output (JSON):
    {
        "review_schema": 2,  // v1 was implicit and used gemini/openai
        "success": true/false,
        "provider": "openrouter" | "direct" | "none",
        "skipped": "empty_diff",  // optional, code-mode only
        "reviews": {
            "deepseek": { "status": "success|error|skipped", "feedback": "..." },
            "openai": { "status": "success|error|skipped", "feedback": "..." }
        },
        // Both reviewers' verdicts, read from the SHIPWRIGHT_VERDICT sentinel,
        // plus the deterministic comparison. Present on every exit path.
        "verdicts":  { "deepseek": "approve", "openai": "reject" },
        "statuses":  { "deepseek": "success", "openai": "success" },
        "contradiction": {
            "detected": true, "comparable": true,
            "requires_resolution": true, "reason": "..."
        }
    }

Prompt loading uses per-mode helpers from ``lib.external_review_prompts``;
reviewer/model identities are validated against fixed bindings before client construction.
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from pathlib import Path

# Wire up shared/scripts/lib so we can import shared helpers + the env loader.
# parents[0]=tools, [1]=scripts, [2]=shared.
_SHARED_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_SHARED_LIB) not in sys.path:
    sys.path.insert(0, str(_SHARED_LIB))

from env import load_shipwright_env  # type: ignore[import-not-found]

load_shipwright_env()

from external_review_config import load_review_config  # noqa: E402
from external_review_degraded import (  # noqa: E402
    MAX_OUTPUT_TOKENS,
    REVIEW_ENVELOPE_SCHEMA,
    file_partial_degradation_triage,
    finalize_review_output,
    llm_client_settings,
    retrying_completion,
)
from external_review_modes import (  # noqa: E402
    MODE_INPUT,
    ModeInputError,
    is_blank,
    render_user_prompt,
    select_mode_input,
)
from external_review_prompts import (  # noqa: E402
    default_review_prompts,
    load_architecture_review_prompts,
    load_code_review_prompts,
    load_iterate_review_prompts,
    load_plan_review_prompts,
)
from external_review_routing import (  # noqa: E402
    openrouter_extra_body,
    resolve_reviewer_model,
)
from iterate_timings import span as _timing_span  # noqa: E402
from review_verdict import summarize_reviews  # noqa: E402

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


#: Kept as a module-level name: two call sites below and the tests bind to it.
_render_user_prompt = render_user_prompt


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

        model_name = resolve_reviewer_model(config, model_key, "openrouter")
        extra_body = openrouter_extra_body(model_key, config)
        timeout, max_retries = llm_client_settings(config)

        client = OpenAI(
            api_key=api_key, base_url=OPENROUTER_BASE_URL,
            timeout=timeout, max_retries=max_retries,
        )
        prompt = _render_user_prompt(user_prompt, plan, spec)

        return retrying_completion(
            client, via="openrouter", max_retries=max_retries,
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=MAX_OUTPUT_TOKENS,
            extra_body=extra_body,
        )

    except ImportError:
        return {"status": "error", "reason": "openai package not installed"}
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

        model_name = resolve_reviewer_model(config, "openai", "direct")
        timeout, max_retries = llm_client_settings(config)

        client = OpenAI(api_key=api_key, timeout=timeout, max_retries=max_retries)
        prompt = _render_user_prompt(user_prompt, plan, spec)

        return retrying_completion(
            client, via="direct", max_retries=max_retries,
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            # gpt-5.x rejects `max_tokens`; `max_completion_tokens` is required.
            max_completion_tokens=MAX_OUTPUT_TOKENS,
        )

    except ImportError:
        return {"status": "error", "reason": "openai package not installed"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}


def detect_provider() -> str:
    """Detect which review provider to use.

    Fallback chain: OpenRouter → direct OpenAI → none.
    """
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"

    if os.environ.get("OPENAI_API_KEY"):
        return "direct"

    return "none"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="External LLM plan / iterate / code / architecture review",
    )
    # One input flag per mode (see lib/external_review_modes.MODE_INPUT). All are non-required at parse
    # time so a single CLI shape can serve every mode; mode-specific validation
    # happens after parse, and rejects a flag belonging to a DIFFERENT mode
    # rather than ignoring it.
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
        "--brief-file",
        required=False,
        help="Architecture brief (--mode architecture). A brief, NOT the plan "
             "— see shared/templates/architecture_brief.md",
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
        choices=list(MODE_INPUT),
        default="plan",
        help="Review mode: 'plan' (pipeline plan vs project spec), 'iterate' "
             "(mini-plan vs iterate spec), 'code' (diff vs spec), or "
             "'architecture' (brief vs spec — should this exist at all).",
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
    parser.add_argument(
        "--run-id", default=None,
        help="Iterate run_id — records this call as an 'external_review' timing span; omit to skip.",
    )
    args = parser.parse_args()

    # Mode-specific validation lives in lib/external_review_modes (a foreign
    # flag first, then a missing one — see there for why the order matters).
    try:
        value, primary_label = select_mode_input(args.mode, args)
    except ModeInputError as exc:
        # `parser.error` exits 2 and never returns — a fact about argparse, not
        # one visible here, so without the raise this reads as falling through
        # to an unbound `value` (CodeQL py/uninitialized-local-variable, #582).
        parser.error(str(exc))
        raise SystemExit(2) from exc
    primary_path = Path(value)

    spec_path = Path(args.spec_file)

    if not primary_path.exists():
        print(
            json.dumps(
                {
                    "review_schema": REVIEW_ENVELOPE_SCHEMA,
                    "success": False,
                    "error": f"{primary_label} not found: {primary_path}",
                },
                indent=2,
            )
        )
        return 1

    if not spec_path.exists():
        print(json.dumps({
            "review_schema": REVIEW_ENVELOPE_SCHEMA,
            "success": False,
            "error": f"Spec not found: {spec_path}",
        }, indent=2))
        return 1

    primary_text = primary_path.read_text(encoding="utf-8")
    spec = spec_path.read_text(encoding="utf-8")

    # `.strip()` alone is not enough: a BOM is not whitespace to Python
    # (`'﻿'.isspace()` is False), and PowerShell 5.1's `Set-Content -Encoding
    # UTF8 ""` writes exactly BOM+CRLF — which would have read as a non-empty
    # brief and been sent to both providers (Stage-3 doubt review, low).
    #
    # An empty brief is an ERROR, not a skip — the opposite of code mode below.
    # An empty diff genuinely has nothing to review; an empty brief means this
    # pass's only input was never written, and the providers would still answer:
    # a plausible `approve` over nothing, recorded as a completed review.
    # `is_blank` (not `.strip()`) because a BOM is not whitespace.
    if args.mode == "architecture" and is_blank(primary_text):
        print(json.dumps({
            "review_schema": REVIEW_ENVELOPE_SCHEMA,
            "success": False,
            "error": (
                f"Brief is empty: {primary_path} — the architecture review has "
                "nothing to reason over, and reviewing nothing is not a pass. "
                "Write it from shared/templates/architecture_brief.md; when the "
                "change adds nothing permanent that is three lines."
            ),
        }, indent=2))
        return 1

    # Code-mode short-circuit: empty diff → no provider call. The LLM cannot
    # review what isn't there, and many providers reject empty inputs.
    if args.mode == "code" and not primary_text.strip():
        empty_reviews = {
            "deepseek": {"status": "skipped", "reason": "empty diff"},
            "openai": {"status": "skipped", "reason": "empty diff"},
        }
        print(json.dumps({
            "review_schema": REVIEW_ENVELOPE_SCHEMA,
            "success": True,
            "skipped": "empty_diff",
            "provider": "none",
            "degraded": False,
            "reviews": empty_reviews,
            # Same shape on every exit path so a consumer never has to guard
            # for the block's absence.
            **summarize_reviews(empty_reviews),
        }, indent=2))
        return 0

    config = load_review_config(project_root=Path(args.project_root).resolve())

    # Load mode-specific prompts.
    if args.mode == "iterate":
        system_prompt, user_prompt = load_iterate_review_prompts()
    elif args.mode == "code":
        system_prompt, user_prompt = load_code_review_prompts()
    elif args.mode == "architecture":
        system_prompt, user_prompt = load_architecture_review_prompts()
    else:
        system_prompt, user_prompt = load_plan_review_prompts(args.plugin_root)

    default_system, default_user = default_review_prompts(args.mode)
    system_prompt = system_prompt or default_system
    user_prompt = user_prompt or default_user

    provider = detect_provider()
    reviews: dict[str, dict] = {}

    # external_review is a real producer boundary (this whole block IS the
    # network-call span); code mode is the Step-8 cascade's pass, others —
    # plan, iterate and architecture alike — run pre-Build, which is why
    # architecture shares `planning` rather than earning a parent of its own.
    # Bare string below is a span-parent name, not a path.
    timing_cm = nullcontext(None)
    if args.run_id:
        timing_parent = "review" if args.mode == "code" else "planning"  # artifact-path-canon: legacy
        timing_cm = _timing_span(Path(args.project_root).resolve(), args.run_id,
                                 name="external_review", parent=timing_parent)
    with timing_cm as timing_extra:
        if provider == "openrouter":
            # Both reviews via OpenRouter (one API key)
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {
                    executor.submit(review_with_openrouter, primary_text, spec, system_prompt, user_prompt, config, "deepseek"): "deepseek",
                    executor.submit(review_with_openrouter, primary_text, spec, system_prompt, user_prompt, config, "openai"): "openai",
                }
                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        reviews[name] = future.result()
                    except Exception as e:
                        reviews[name] = {"status": "error", "reason": str(e)}

        elif provider == "direct":
            # DeepSeek has no direct route. Preserve GPT's existing direct path.
            reviews = {
                "deepseek": {
                    "status": "skipped",
                    "reason": "DeepSeek requires an approved OpenRouter ZDR endpoint",
                },
                "openai": review_with_openai(
                    primary_text, spec, system_prompt, user_prompt, config
                ),
            }

        else:
            # No keys — both reviews skipped
            reviews = {
                "deepseek": {"status": "skipped", "reason": "No OPENROUTER_API_KEY set"},
                "openai": {"status": "skipped", "reason": "No OPENAI_API_KEY or OPENROUTER_API_KEY set"},
            }
        if timing_extra is not None:
            timing_extra["provider"] = provider

    # Degraded-gate: keys present but 0 reviews succeeded → fail loud (never a silent no-op).
    output, exit_code = finalize_review_output(provider, reviews)
    # Two reviewers exist so disagreement gets noticed; carry both verdicts and
    # the derived contradiction alongside the full texts rather than letting a
    # downstream finding count average them away.
    output.update(summarize_reviews(reviews))
    if output.get("partially_degraded"):
        file_partial_degradation_triage(
            Path(args.project_root).resolve(), args.run_id, args.mode, provider,
            output["partially_degraded_legs"],
        )
    print(json.dumps(output, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
