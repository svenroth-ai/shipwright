"""The gateway roster for ``tools/external_review.py``, plus the output tail and
timing span both of its routes share (#547).

Lives here rather than in the CLI because that file is a grandfathered
bloat-baseline entry (ratchet: it may not grow) and because the two routes must
not each carry their own copy of the envelope tail - a drift between them is the
bug class this module exists to prevent.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from pathlib import Path

from external_review_degraded import (
    file_partial_degradation_triage,
    finalize_review_output,
    llm_client_settings,
)
from external_review_gateway import redact_all_configured_secrets, review_gateway_prompt
from iterate_timings import span as _timing_span
from review_verdict import GATEWAY_REVIEWERS, summarize_reviews

__all__ = ["emit_envelope", "review_timing", "run_gateway"]


def review_timing(args):
    """The ``external_review`` timing span, or a no-op without ``--run-id``.

    Code mode is the Step-8 cascade's pass; every other mode runs pre-Build,
    which is why architecture shares ``planning`` rather than earning a parent
    of its own. The bare string is a span-parent name, not a path.
    """
    if not args.run_id:
        return nullcontext(None)
    parent = "review" if args.mode == "code" else "planning"  # artifact-path-canon: legacy
    return _timing_span(Path(args.project_root).resolve(), args.run_id,
                        name="external_review", parent=parent)


def emit_envelope(args, provider: str, reviews: dict, driver_record: dict) -> int:
    """Print the review envelope and return the exit code.

    Two reviewers exist so disagreement gets noticed; carry both verdicts and the
    derived contradiction alongside the full texts rather than letting a
    downstream finding count average them away.
    """
    output, exit_code = finalize_review_output(provider, reviews)
    output.update(driver_record)
    output.update(summarize_reviews(reviews))
    if output.get("partially_degraded"):
        file_partial_degradation_triage(
            Path(args.project_root).resolve(), args.run_id, args.mode, provider,
            output["partially_degraded_legs"],
        )
    print(json.dumps(output, indent=2))
    return exit_code


def run_gateway(args, driver_record: dict, primary_text: str, spec: str,
                system_prompt: str, user_prompt: str, config: dict, render) -> int:
    """The operator-owned gateway roster: two legs, ``model-1`` / ``model-2``.

    Exclusive and fail-closed - a failed leg is reported, never re-routed to
    OpenRouter/direct, whatever other keys happen to be set. ``--driver`` does
    not pick the roster here (the operator's virtual keys decide which models
    answer), but the record still carries it. ``render`` is the CLI's own
    placeholder renderer, so the prompt is built exactly as on the key route.
    """
    timeout, max_retries = llm_client_settings(config)
    prompt = render(user_prompt, primary_text, spec)
    reviews: dict[str, dict] = {}
    with review_timing(args) as timing_extra:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(
                    review_gateway_prompt, prompt, system_prompt, slot, timeout, max_retries,
                ): name
                for slot, name in zip(("1", "2"), GATEWAY_REVIEWERS)
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    reviews[name] = future.result()
                except Exception as e:  # review_gateway_prompt redacts itself; defense in depth
                    reviews[name] = {"status": "error", "reason": redact_all_configured_secrets(str(e))}
        if timing_extra is not None:
            timing_extra["provider"] = "gateway"
    return emit_envelope(args, "gateway", reviews, driver_record)
