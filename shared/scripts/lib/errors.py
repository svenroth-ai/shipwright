"""Structured error responses for Shipwright scripts.

Every script that outputs JSON must include a "success" boolean.
On failure, include the structured "error" object with actionable context.

Error categories (from Claude Architect Certification, Domain 2.2):
  - transient: timeouts, race conditions, temporary unavailability (retryable)
  - validation: bad input, malformed data, schema mismatch (not retryable)
  - business: policy violation, threshold breach, missing prerequisite (not retryable)
  - permission: access denied, auth failure (not retryable)

Usage:
    from shared.scripts.lib.errors import structured_error, structured_success

    # On failure:
    print(json.dumps(structured_error(
        what_failed="Read section-writer transcript",
        what_was_attempted="Parsing JSONL transcript at /tmp/transcript.jsonl",
        error_category="transient",
        is_retryable=True,
        partial_results={"transcript_path": path, "file_existed": True},
        alternatives=["Re-run section-writer subagent", "Write section manually"],
    )))

    # On success:
    print(json.dumps(structured_success(data={"section": "01-auth", "path": "..."})))
"""

from __future__ import annotations

from typing import Any

# Valid error categories per Claude Architect Cert Domain 2.2
ERROR_CATEGORIES = {"transient", "validation", "business", "permission"}


def structured_error(
    what_failed: str,
    what_was_attempted: str,
    error_category: str,
    is_retryable: bool,
    partial_results: dict[str, Any] | None = None,
    alternatives: list[str] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a structured error response.

    Args:
        what_failed: Short description of what went wrong.
        what_was_attempted: What operation was being performed.
        error_category: One of "transient", "validation", "business", "permission".
        is_retryable: Whether the operation could succeed on retry.
        partial_results: Any partial data recovered before failure.
        alternatives: Suggested alternative actions.
        context: Additional key-value context for debugging.

    Returns:
        Dict with success=False and structured error details.
    """
    if error_category not in ERROR_CATEGORIES:
        raise ValueError(
            f"Invalid error_category '{error_category}'. "
            f"Must be one of: {sorted(ERROR_CATEGORIES)}"
        )

    return {
        "success": False,
        "error": {
            "what_failed": what_failed,
            "what_was_attempted": what_was_attempted,
            "error_category": error_category,
            "is_retryable": is_retryable,
            "partial_results": partial_results or {},
            "alternatives": alternatives or [],
            "context": context or {},
        },
    }


def structured_success(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a structured success response.

    Args:
        data: The result payload.

    Returns:
        Dict with success=True and result data.
    """
    result: dict[str, Any] = {"success": True}
    if data:
        result.update(data)
    return result


def hook_error(
    hook_event: str,
    what_failed: str,
    what_was_attempted: str,
    error_category: str,
    is_retryable: bool,
    partial_results: dict[str, Any] | None = None,
    alternatives: list[str] | None = None,
) -> dict[str, Any]:
    """Build a structured error formatted as Claude Code hook output.

    Hooks communicate via hookSpecificOutput JSON. This wraps the structured
    error in the hook output format so Claude sees actionable context.

    Args:
        hook_event: The hook event name (e.g. "SubagentStop", "PreToolUse").
        what_failed: Short description of what went wrong.
        what_was_attempted: What operation was being performed.
        error_category: One of "transient", "validation", "business", "permission".
        is_retryable: Whether the operation could succeed on retry.
        partial_results: Any partial data recovered before failure.
        alternatives: Suggested alternative actions.

    Returns:
        Dict with hookSpecificOutput containing structured error.
    """
    if error_category not in ERROR_CATEGORIES:
        raise ValueError(
            f"Invalid error_category '{error_category}'. "
            f"Must be one of: {sorted(ERROR_CATEGORIES)}"
        )

    error_detail = {
        "what_failed": what_failed,
        "what_was_attempted": what_was_attempted,
        "error_category": error_category,
        "is_retryable": is_retryable,
        "partial_results": partial_results or {},
        "alternatives": alternatives or [],
    }

    # Build human-readable context string for Claude
    alt_text = ""
    if alternatives:
        alt_text = " Alternatives: " + "; ".join(alternatives)

    return {
        "hookSpecificOutput": {
            "hookEventName": hook_event,
            "additionalContext": (
                f"ERROR [{error_category}]: {what_failed}. "
                f"Attempted: {what_was_attempted}.{alt_text}"
            ),
            "structuredError": error_detail,
        }
    }


def hook_block(
    hook_event: str,
    reason: str,
    details: dict[str, Any],
    override_instruction: str,
    resume_note: str,
) -> dict[str, Any]:
    """Build a soft-block hook output (exit code 2) with override support.

    Used by compliance enforcement hooks. The user can say "Continue anyway"
    and the override gets logged to .shipwright/agent_docs/compliance_overrides.log.

    Args:
        hook_event: The hook event name (e.g. "PreToolUse").
        reason: Human-readable reason for blocking.
        details: Structured details (thresholds, findings, etc.).
        override_instruction: Text telling Claude how to handle user override.
        resume_note: Text explaining when/how the check will be re-applied.

    Returns:
        Dict with hookSpecificOutput for soft-block display.
    """
    return {
        "hookSpecificOutput": {
            "hookEventName": hook_event,
            "additionalContext": (
                f"BLOCKED: {reason}\n\n"
                f"The user may say 'Continue anyway' to override this check. "
                f"If they do: {override_instruction}\n\n"
                f"Note: {resume_note}"
            ),
            "blocked": True,
            "reason": reason,
            "details": details,
            "override_instruction": override_instruction,
            "resume_note": resume_note,
        }
    }
