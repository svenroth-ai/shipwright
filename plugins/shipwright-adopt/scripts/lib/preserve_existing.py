"""Preserve existing user artifacts before /shipwright-adopt overwrites them.

Trigger scenario this exists for: a real adoption run on a Windows +
multi-service repo silently overwrote a 16 KB load-bearing CLAUDE.md
and a 137 KB decision_log.md (58 ADRs spanning 6 weeks of history) with
thin scaffold content. The user kept those files manually and lost
everything else.

Policy:
- All four agent-doc-style files (CLAUDE.md, decision_log.md,
  architecture.md, conventions.md) get backed up to
  `<root>/.shipwright/adopt/backups/<rel>.preserved` before any write.
- CLAUDE.md ABOVE a byte threshold (1024 by default) is treated as
  load-bearing and NOT overwritten — adopt's suggested content goes to
  `.shipwright/adopt/CLAUDE.md.adopt-suggested` instead.
- decision_log.md with any existing `## ADR-` heading triggers a merge:
  the new adoption ADR-0001 is prepended; the existing body is preserved
  verbatim. The ADRs the user wrote keep their original numbering and
  ordering.
- architecture.md / conventions.md are backed up but overwritten — they
  are less load-bearing and easy to recover from `.preserved`.

A machine-readable summary of every action lands in
`.shipwright/adopt/preservation_log.json` so the handoff and
validate_adoption can surface what happened.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any


BACKUPS_REL = ".shipwright/adopt/backups"
PRESERVATION_LOG_REL = ".shipwright/adopt/preservation_log.json"
SUGGESTED_CLAUDE_REL = ".shipwright/adopt/CLAUDE.md.adopt-suggested"
LOADBEARING_CLAUDE_BYTE_THRESHOLD = 1024


_ADR_HEADING_RE = re.compile(r"^##\s+ADR-\d+", re.MULTILINE)


def preserve_if_exists(project_root: Path, rel_path: str) -> Path | None:
    """Copy `<project_root>/<rel_path>` into the backups dir.

    Returns the backup path if the source existed (overwriting any older
    backup at the same key), or None if the source was absent. Never
    moves — the source file is left in place so the caller can decide
    what to do next.
    """
    src = project_root / rel_path
    if not src.is_file():
        return None
    backup_root = project_root / BACKUPS_REL
    dst = backup_root / f"{rel_path}.preserved"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def count_adr_sections(decision_log: Path) -> int:
    """Count `## ADR-NNNN` headings in the file. 0 if missing or unreadable."""
    if not decision_log.is_file():
        return 0
    try:
        body = decision_log.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0
    return len(_ADR_HEADING_RE.findall(body))


def is_loadbearing_claude_md(
    claude_md: Path,
    byte_threshold: int = LOADBEARING_CLAUDE_BYTE_THRESHOLD,
) -> bool:
    """Heuristic: a CLAUDE.md significantly larger than the adopt scaffold
    (~600 bytes) is assumed to carry hand-written load-bearing rules."""
    if not claude_md.is_file():
        return False
    try:
        return claude_md.stat().st_size > byte_threshold
    except OSError:
        return False


def merge_decision_log(new_content: str, existing: Path) -> tuple[str, dict[str, Any]]:
    """Merge new adoption decision_log content with an existing user file.

    Strategy: if the existing file has any ADR sections, prepend the new
    content's adoption ADR-0001 above the existing body (which keeps all
    historical ADRs intact, with their original numbering). If no ADRs
    are present, the existing file is treated as a placeholder and the
    new content replaces it.

    Returns (merged_content, info). `info` carries `existing_adrs` and
    `action` for the preservation log.
    """
    existing_adrs = count_adr_sections(existing)
    if existing_adrs == 0:
        return new_content, {"existing_adrs": 0, "action": "overwritten"}

    existing_body = existing.read_text(encoding="utf-8", errors="ignore")

    merged = (
        "<!-- Adoption merge marker — top of file is /shipwright-adopt scaffold,\n"
        "     followed by the existing decision log preserved verbatim.\n"
        "     Original file backed up to .shipwright/adopt/backups/. -->\n\n"
        + new_content.rstrip()
        + "\n\n---\n\n"
        + "## Existing decision log (preserved during adoption)\n\n"
        + existing_body.lstrip()
    )
    return merged, {"existing_adrs": existing_adrs, "action": "merged"}


def record_preservation_action(
    project_root: Path,
    *,
    file: str,
    action: str,
    backup_path: Path | None = None,
    note: str | None = None,
) -> None:
    """Append a structured entry to `<root>/.shipwright/adopt/preservation_log.json`.

    Idempotent reader/writer: the log is read-modify-written atomically
    (no concurrent writers in adopt's flow). The file is created on
    first call. Entries are append-only — duplicates are allowed (a
    re-run of adopt overwriting the same file is itself a meaningful
    audit trail event).
    """
    log_path = project_root / PRESERVATION_LOG_REL
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        try:
            data = json.loads(log_path.read_text(encoding="utf-8"))
            entries = data.get("entries", [])
        except (json.JSONDecodeError, OSError):
            entries = []
    else:
        entries = []
    entry: dict[str, Any] = {"file": file, "action": action}
    if backup_path is not None:
        entry["backup"] = backup_path.relative_to(project_root).as_posix()
    if note:
        entry["note"] = note
    entries.append(entry)
    log_path.write_text(
        json.dumps({"version": 1, "entries": entries}, indent=2) + "\n",
        encoding="utf-8",
    )
