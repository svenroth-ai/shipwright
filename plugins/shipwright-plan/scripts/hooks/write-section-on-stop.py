#!/usr/bin/env python3
"""Extract section content from section-writer subagent transcript.

Fires on SubagentStop for shipwright-plan:section-writer.
Reads the subagent's JSONL transcript and writes the section file.

CRITICAL: JSONL Race Condition Fix (from upstream v0.3.1)
Claude Code may not have flushed the transcript when this hook fires.
We retry with exponential backoff to handle this.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any


# ---------------------------------------------------------------------------
# Inline structured error helpers (hook runs from plugin cache, can't import
# shared/scripts/lib/errors.py).  Mirrors the contract defined there.
# ---------------------------------------------------------------------------

def _hook_error(
    what_failed: str,
    what_was_attempted: str,
    error_category: str,
    is_retryable: bool,
    partial_results: dict[str, Any] | None = None,
    alternatives: list[str] | None = None,
) -> dict[str, Any]:
    """Build hookSpecificOutput with structured error context."""
    error_detail = {
        "what_failed": what_failed,
        "what_was_attempted": what_was_attempted,
        "error_category": error_category,
        "is_retryable": is_retryable,
        "partial_results": partial_results or {},
        "alternatives": alternatives or [],
    }
    alt_text = ""
    if alternatives:
        alt_text = " Alternatives: " + "; ".join(alternatives)
    return {
        "hookSpecificOutput": {
            "hookEventName": "SubagentStop",
            "additionalContext": (
                f"ERROR [{error_category}]: {what_failed}. "
                f"Attempted: {what_was_attempted}.{alt_text}"
            ),
            "structuredError": error_detail,
        }
    }


def read_transcript_with_retry(transcript_path: str, max_retries: int = 4) -> list[dict]:
    """Read JSONL transcript with retry for flush race condition.

    Retries: 50ms, 100ms, 200ms, 400ms
    """
    delays = [0.05, 0.1, 0.2, 0.4]

    for attempt in range(max_retries):
        try:
            if not os.path.exists(transcript_path):
                if attempt < max_retries - 1:
                    time.sleep(delays[attempt])
                    continue
                return []

            with open(transcript_path, encoding="utf-8") as f:
                content = f.read().strip()

            if not content:
                if attempt < max_retries - 1:
                    time.sleep(delays[attempt])
                    continue
                return []

            entries = []
            for line in content.splitlines():
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

            if entries:
                return entries

            if attempt < max_retries - 1:
                time.sleep(delays[attempt])

        except OSError:
            if attempt < max_retries - 1:
                time.sleep(delays[attempt])

    return []


def extract_section_content(entries: list[dict]) -> str | None:
    """Extract the section markdown content from transcript entries."""
    # Look for assistant messages with markdown content
    for entry in reversed(entries):
        if entry.get("role") == "assistant":
            content = entry.get("content", "")
            if isinstance(content, list):
                # Handle content blocks
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                content = "\n".join(text_parts)

            if content and "# Section:" in content:
                return content

    return None


def extract_section_name(entries: list[dict]) -> str | None:
    """Extract the section name from transcript entries."""
    for entry in entries:
        content = entry.get("content", "")
        if isinstance(content, str):
            match = re.search(r"(\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*)", content)
            if match:
                return match.group(1)
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception) as exc:
        print(json.dumps(_hook_error(
            what_failed="Parse hook stdin payload",
            what_was_attempted="json.load(sys.stdin) for SubagentStop event",
            error_category="validation",
            is_retryable=False,
            partial_results={"exception": str(exc)},
            alternatives=["Re-run section-writer subagent"],
        )))
        return 0

    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        print(json.dumps(_hook_error(
            what_failed="Missing transcript_path in payload",
            what_was_attempted="Reading SubagentStop payload for transcript location",
            error_category="validation",
            is_retryable=False,
            partial_results={"payload_keys": list(payload.keys())},
            alternatives=["Check hooks.json matcher config"],
        )))
        return 0

    entries = read_transcript_with_retry(transcript_path)
    if not entries:
        print(json.dumps(_hook_error(
            what_failed="Read section-writer transcript",
            what_was_attempted=f"Reading JSONL transcript at {transcript_path} (4 retries with backoff)",
            error_category="transient",
            is_retryable=True,
            partial_results={
                "transcript_path": transcript_path,
                "file_exists": os.path.exists(transcript_path),
            },
            alternatives=["Re-run section-writer subagent", "Write section manually"],
        )))
        return 0

    section_content = extract_section_content(entries)
    section_name = extract_section_name(entries)

    if not section_content or not section_name:
        print(json.dumps(_hook_error(
            what_failed="Extract section content from transcript",
            what_was_attempted="Searching transcript entries for '# Section:' header and section name pattern",
            error_category="validation",
            is_retryable=False,
            partial_results={
                "section_name": section_name,
                "has_content": bool(section_content),
                "transcript_entries": len(entries),
            },
            alternatives=["Re-run section-writer with clearer instructions", "Write section manually"],
        )))
        return 0

    # Determine output path from environment or transcript context
    planning_dir = os.environ.get("SHIPWRIGHT_PLANNING_DIR", "")
    if not planning_dir:
        # Try to infer from transcript
        for entry in entries:
            content = str(entry.get("content", ""))
            match = re.search(r"planning[_-]dir[=:]\s*[\"']?([^\s\"']+)", content)
            if match:
                planning_dir = match.group(1)
                break

    if not planning_dir:
        print(json.dumps(_hook_error(
            what_failed="Determine planning directory",
            what_was_attempted="Checking SHIPWRIGHT_PLANNING_DIR env var and transcript for planning-dir reference",
            error_category="validation",
            is_retryable=False,
            partial_results={"section_name": section_name, "env_set": bool(os.environ.get("SHIPWRIGHT_PLANNING_DIR"))},
            alternatives=["Set SHIPWRIGHT_PLANNING_DIR environment variable", "Write section file manually"],
        )))
        return 0

    sections_dir = os.path.join(planning_dir, "sections")
    os.makedirs(sections_dir, exist_ok=True)

    output_path = os.path.join(sections_dir, f"{section_name}.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(section_content)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SubagentStop",
            "additionalContext": f"Section written: {output_path}",
        }
    }))

    return 0


if __name__ == "__main__":
    sys.exit(main())
