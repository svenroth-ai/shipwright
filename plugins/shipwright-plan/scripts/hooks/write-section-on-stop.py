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
    except (json.JSONDecodeError, Exception):
        return 0

    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        return 0

    entries = read_transcript_with_retry(transcript_path)
    if not entries:
        # Couldn't read transcript — log but don't fail
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SubagentStop",
                "additionalContext": "Warning: Could not read section-writer transcript. Section may need manual writing.",
            }
        }))
        return 0

    section_content = extract_section_content(entries)
    section_name = extract_section_name(entries)

    if not section_content or not section_name:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SubagentStop",
                "additionalContext": f"Warning: Could not extract section content from transcript. section_name={section_name}, has_content={bool(section_content)}",
            }
        }))
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
