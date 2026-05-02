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
- decision_log.md with any existing `## ADR-` (or `### ADR-`) heading
  triggers a merge: the new adoption ADR is prepended; the existing
  body is preserved verbatim. The adoption ADR's id is the next free
  3-digit number — ADR-001 on a greenfield log, otherwise
  `max(existing) + 1` (see `parse_max_adr_id`). The ADRs the user
  wrote keep their original numbering and ordering.
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


# Used by count_adr_sections — lenient on heading level (H2 or H3) and
# on digit length, since the merge-vs-overwrite decision must err on the
# side of preserving any existing user ADRs even if their numbering pre-
# dates Shipwright's 3-digit canon.
_ADR_HEADING_RE = re.compile(r"^#{2,3}\s+ADR-\d+", re.MULTILINE)

# Used by parse_max_adr_id — strict 3+ digit match (Shipwright's output
# canon). Tolerant of:
#   * H2 vs H3 heading levels (## ADR-NNN: vs ### ADR-NNN:),
#   * the 045b/045a disambiguation-suffix convention,
#   * stylistic title duplication ("### ADR-053: ADR-053: Foo").
# A 1- or 2-digit historical id is intentionally NOT contributed to the
# max — the caller is fine starting at ADR-001 in that degenerate case.
_ADR_ID_PARSE_RE = re.compile(
    r"^#{2,3}\s+ADR-(\d{3,})[a-z]?:",
    re.MULTILINE,
)


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
    """Count `## ADR-NNNN` (or `### ADR-NNNN`) headings in the file.

    Returns 0 if the file is missing or unreadable. Lenient on heading
    level and digit length — see `_ADR_HEADING_RE` for the rationale.
    """
    if not decision_log.is_file():
        return 0
    try:
        body = decision_log.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0
    return len(_ADR_HEADING_RE.findall(body))


def parse_max_adr_id(content: str) -> int:
    """Return the highest 3+ digit numeric ADR id in ``content``, or 0.

    Used by /shipwright-adopt to pick the next-free ADR id when an
    existing decision_log.md is present. Robust against the four
    real-world variations seen in shipwright-webui's log: H2 vs H3
    headings, 045b-style disambiguation suffixes, and stylistic title
    duplication ("### ADR-053: ADR-053: Foo").

    1- or 2-digit historical ids do not contribute to the max — the
    caller falls back to ADR-001 in that degenerate case (the project
    isn't following Shipwright's 3-digit canon, so colliding numbering
    is the user's lookout, not adopt's).
    """
    matches = _ADR_ID_PARSE_RE.findall(content)
    if not matches:
        return 0
    return max(int(n) for n in matches)


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


def merge_decision_log(
    new_content: str,
    existing: Path,
    *,
    adoption_adr_id: int | None = None,
) -> tuple[str, dict[str, Any]]:
    """Merge new adoption decision_log content with an existing user file.

    Strategy: if the existing file has any ADR sections, prepend the new
    content's adoption ADR above the existing body (which keeps all
    historical ADRs intact, with their original numbering). If no ADRs
    are present, the existing file is treated as a placeholder and the
    new content replaces it.

    The merge preamble reports the actual range of pre-existing ADRs
    (e.g. "Pre-existing entries: up to ADR-058 (58 ADR section(s))")
    rather than hardcoding the previous-iterate's "ADR-052" snapshot.
    `adoption_adr_id`, when provided, is reflected in the preamble so a
    reader can see at a glance which entry adopt added.

    Returns (merged_content, info). `info` carries:
        - existing_adrs:        count of `^## ADR-` / `^### ADR-` blocks
        - max_existing_adr_id:  highest 3+ digit numeric id (or 0 if none)
        - action:               "merged" or "overwritten"
    """
    existing_adrs = count_adr_sections(existing)
    if existing_adrs == 0:
        return new_content, {
            "existing_adrs": 0,
            "max_existing_adr_id": 0,
            "action": "overwritten",
        }

    existing_body = existing.read_text(encoding="utf-8", errors="ignore")
    max_existing = parse_max_adr_id(existing_body)

    preamble_lines = [
        "<!-- Adoption merge marker — top of file is /shipwright-adopt scaffold,",
        "     followed by the existing decision log preserved verbatim.",
    ]
    if max_existing > 0:
        preamble_lines.append(
            f"     Pre-existing entries: up to ADR-{max_existing:03d} "
            f"({existing_adrs} ADR section(s) detected).",
        )
    else:
        preamble_lines.append(
            f"     Pre-existing entries: {existing_adrs} ADR section(s) detected "
            f"(no 3+ digit canonical ids found — kept verbatim).",
        )
    if adoption_adr_id is not None:
        preamble_lines.append(
            f"     Adoption ADR: ADR-{adoption_adr_id:03d}.",
        )
    preamble_lines.append(
        "     Original file backed up to .shipwright/adopt/backups/. -->",
    )
    preamble = "\n".join(preamble_lines) + "\n\n"

    merged = (
        preamble
        + new_content.rstrip()
        + "\n\n---\n\n"
        + "## Existing decision log (preserved during adoption)\n\n"
        + existing_body.lstrip()
    )
    return merged, {
        "existing_adrs": existing_adrs,
        "max_existing_adr_id": max_existing,
        "action": "merged",
    }


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
