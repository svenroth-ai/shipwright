#!/usr/bin/env python3
"""Best-effort FALLBACK: persist section-writer output if it wasn't written directly.

Fires on SubagentStop for shipwright-plan:section-writer. The section-writer now
OWNS persistence — it has a Write tool and writes
``{planning_dir}/sections/{NN-name}.md`` itself (SS4, Campaign 2026-07-07). This
hook is a DEFENSIVE FALLBACK only and **never blocks**:

  * if the section file already exists on disk (the direct write), it is a no-op
    success — it never blocks and never clobbers;
  * if the file is missing, it tries to salvage the content from the subagent
    JSONL transcript and write it;
  * if it cannot salvage, it logs to stderr and exits 0. It does NOT block the
    subagent. The real gate is /shipwright-plan Step 7 (``check-sections.py``),
    which verifies every declared section exists.

This supersedes the ADR-042 block-on-failure behavior: persistence moved into the
agent, so a fallback that blocked would false-block a successful direct write —
the exact failure SS4 fixes (the agent had no write tool and the hook did not
fire, so output was lost; and when the agent did write, a scrape-failure block
would have rejected a successful run).

CRITICAL: JSONL Race Condition (upstream v0.3.1) — the transcript may not be
flushed when the hook fires; the salvage path retries with backoff.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any, Optional


def _diag(message: str, **detail: Any) -> None:
    """Write an operator diagnostic to stderr — never to the protocol stdout.

    A SubagentStop success is signalled by empty stdout; keeping all detail on
    stderr means this fallback never emits a blocking payload.
    """
    sys.stderr.write(f"[shipwright:plan-section] {message}\n")
    if detail:
        sys.stderr.write(
            f"[shipwright:plan-section] detail={json.dumps(detail, ensure_ascii=False)}\n"
        )


def read_transcript_with_retry(transcript_path: str, max_retries: int = 4) -> list[dict]:
    """Read JSONL transcript with retry for the flush race (50ms -> 400ms)."""
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


def extract_section_content(entries: list[dict]) -> Optional[str]:
    """Extract the section markdown content from transcript entries."""
    for entry in reversed(entries):
        if entry.get("role") == "assistant":
            content = entry.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                content = "\n".join(text_parts)

            if content and "# Section:" in content:
                return content

    return None


def extract_section_name(entries: list[dict]) -> Optional[str]:
    """Extract the section name (NN-name) from transcript entries."""
    for entry in entries:
        content = entry.get("content", "")
        if isinstance(content, str):
            match = re.search(r"(\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*)", content)
            if match:
                return match.group(1)
    return None


def resolve_planning_dir(entries: list[dict]) -> str:
    """SHIPWRIGHT_PLANNING_DIR env, else inferred from the transcript."""
    planning_dir = os.environ.get("SHIPWRIGHT_PLANNING_DIR", "")
    if planning_dir:
        return planning_dir
    for entry in entries:
        content = str(entry.get("content", ""))
        match = re.search(r"planning[_-]dir[=:]\s*[\"']?([^\s\"']+)", content)
        if match:
            return match.group(1)
    return ""


def section_output_path(planning_dir: str, section_name: str) -> str:
    return os.path.join(planning_dir, "sections", f"{section_name}.md")


def existing_section_file(planning_dir: str, section_name: Optional[str]) -> Optional[str]:
    """The section file path if it already exists non-empty (direct write), else None."""
    if not planning_dir or not section_name:
        return None
    path = section_output_path(planning_dir, section_name)
    try:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
    except OSError:
        return None
    return None


def is_section_document(content: str) -> bool:
    """True iff the salvaged content's first non-blank line is a section header.

    The direct-write contract is that a section file opens with
    ``# Section: {NN-name}``. Requiring that before persisting salvaged content
    stops the fallback from writing arbitrary assistant prose that merely
    mentions ``# Section:`` somewhere in the body.
    """
    for line in content.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped.startswith("# Section:")
    return False


def _is_within(path: str, root: str) -> bool:
    """True iff ``path`` resolves to ``root`` or a descendant of it."""
    try:
        root_real = os.path.realpath(root)
        path_real = os.path.realpath(path)
    except OSError:
        return False
    return path_real == root_real or path_real.startswith(root_real + os.sep)


def salvage_write_dir(env_dir: str, inferred_dir: str, project_root: str) -> Optional[str]:
    """The directory to WRITE salvaged content into, or None if none is safe.

    Prefers the skill-provided ``SHIPWRIGHT_PLANNING_DIR`` (trusted). A dir
    inferred from untrusted transcript text is allowed ONLY when it resolves
    inside ``project_root`` — this keeps the salvage capability working when the
    env var is unset (its normal state today) without permitting a write outside
    the project tree. ``section_name`` is already regex-constrained, so it cannot
    add traversal on top of a safe base dir.
    """
    if env_dir:
        return env_dir
    if inferred_dir and _is_within(inferred_dir, project_root):
        return inferred_dir
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:  # noqa: BLE001 — a bad payload must not block
        _diag("could not parse SubagentStop stdin payload", exception=str(exc))
        return 0

    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        _diag("no transcript_path in payload", payload_keys=list(payload.keys()))
        return 0

    entries = read_transcript_with_retry(transcript_path)
    section_name = extract_section_name(entries) if entries else None
    planning_dir = resolve_planning_dir(entries)

    # FALLBACK success: the subagent already persisted the section itself.
    existing = existing_section_file(planning_dir, section_name)
    if existing:
        _diag(f"direct-write confirmed, hook is a no-op: {existing}")
        return 0

    # Salvage path — no file on disk; try to recover the content from the transcript.
    if not entries:
        _diag(
            "transcript empty and no section file on disk; Step-7 check-sections gates",
            transcript_path=transcript_path,
        )
        return 0

    section_content = extract_section_content(entries)
    if not section_content or not section_name:
        _diag(
            "no section file on disk and nothing salvageable from transcript",
            section_name=section_name,
            has_content=bool(section_content),
            transcript_entries=len(entries),
        )
        return 0

    # Persist only genuine section documents — not arbitrary assistant prose.
    if not is_section_document(section_content):
        _diag(
            "recovered content is not a section document (no leading '# Section:'); not writing",
            section_name=section_name,
        )
        return 0

    # Choose a SAFE write target: the skill-provided env dir when set, else the
    # transcript-inferred dir ONLY if it resolves inside the project tree
    # (write-outside-tree / path-traversal defense).
    write_dir = salvage_write_dir(
        os.environ.get("SHIPWRIGHT_PLANNING_DIR", ""), planning_dir, os.getcwd(),
    )
    if not write_dir:
        _diag(
            "no safe planning dir for salvage write (inferred dir is outside the project tree)",
            section_name=section_name,
        )
        return 0

    output_path = section_output_path(write_dir, section_name)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(section_content)
    _diag(f"salvaged section from transcript: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
