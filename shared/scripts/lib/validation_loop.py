"""Reusable extract-validate-retry loop.

Claude Architect Best Practice (Domain 4.4):
  "Retry with specific errors. Stop when the data isn't in the source."

Distinguishes between:
  - Retriable errors: format issues, partial data, transient failures
  - Terminal errors: source data missing, business rule violation

Usage:
    from shared.scripts.lib.validation_loop import validate_with_retry

    result = validate_with_retry(
        extract_fn=lambda: parse_section(path),
        validate_fn=lambda data: validate_section_structure(data),
        max_retries=3,
        stop_condition=lambda data, errors: "source file missing" in str(errors),
    )

    if result["success"]:
        process(result["data"])
    else:
        handle_errors(result["final_errors"])
"""

from __future__ import annotations

from typing import Any, Callable


def validate_with_retry(
    extract_fn: Callable[[], Any],
    validate_fn: Callable[[Any], tuple[bool, list[str]]],
    max_retries: int = 3,
    stop_condition: Callable[[Any, list[str]], bool] | None = None,
) -> dict[str, Any]:
    """Extract data, validate it, retry with specific error feedback.

    Args:
        extract_fn: Callable that extracts/produces data. Called once per attempt.
        validate_fn: Callable that returns (is_valid, error_messages).
            Error messages must be SPECIFIC: not "try again" but
            "field X has value Y, expected Z based on source line N".
        max_retries: Maximum number of attempts (including the first).
        stop_condition: Optional callable that returns True if retrying is pointless
            (e.g., source data is fundamentally missing). Receives (data, errors).

    Returns:
        Dict with:
          - success: bool
          - data: extracted data (last attempt)
          - attempts: number of attempts made
          - final_errors: list of error strings from last failed validation
          - stopped_early: bool — True if stop_condition triggered
    """
    last_data = None
    last_errors: list[str] = []

    for attempt in range(1, max_retries + 1):
        # Extract
        try:
            data = extract_fn()
        except Exception as exc:
            last_errors = [f"Extraction failed on attempt {attempt}: {exc}"]
            last_data = None

            # Check stop condition on extraction failure
            if stop_condition and stop_condition(None, last_errors):
                return {
                    "success": False,
                    "data": None,
                    "attempts": attempt,
                    "final_errors": last_errors,
                    "stopped_early": True,
                }
            continue

        last_data = data

        # Validate
        is_valid, errors = validate_fn(data)
        if is_valid:
            return {
                "success": True,
                "data": data,
                "attempts": attempt,
                "final_errors": [],
                "stopped_early": False,
            }

        last_errors = errors

        # Check stop condition
        if stop_condition and stop_condition(data, errors):
            return {
                "success": False,
                "data": data,
                "attempts": attempt,
                "final_errors": errors,
                "stopped_early": True,
            }

    # Exhausted retries
    return {
        "success": False,
        "data": last_data,
        "attempts": max_retries,
        "final_errors": last_errors,
        "stopped_early": False,
    }
