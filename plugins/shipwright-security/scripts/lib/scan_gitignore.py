"""Best-effort `.gitignore` entry for the OSS scan's report folder.

The scan ignores ONLY the folder it writes to. `.shipwright/` also holds tracked
ADRs, specs and triage, so ignoring the whole directory would silently drop every
NEW file there from `git add -A` (GitHub issue #985).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Already covers the reports folder; the canonical whitelist form that Shipwright's
# own gitignore template uses (`/.shipwright/*` plus `!` re-includes).
COVERING_GITIGNORE_ENTRIES = {"/.shipwright/*"}
# Older versions of the scan wrote the broad form. It hides the reports, but also
# every new tracked file under `.shipwright/`: left in place (never auto-removed)
# and warned about.
BROAD_GITIGNORE_ENTRIES = {"/.shipwright/", ".shipwright/", "/.shipwright", ".shipwright"}
# Pre-iterate-3 location: accepted as "present" during migration.
LEGACY_GITIGNORE_ENTRIES = {"/securityreports/", "securityreports/"}


def reports_gitignore_entry(reports_dir: str) -> str:
    """The one line the scan may add: ``/<reports_dir>/``."""
    return f"/{reports_dir}/"


def ensure_gitignore_entry(project_root: Path, reports_dir: str) -> str:
    """Best-effort gitignore append.

    - If .gitignore is missing → skip silently (don't materialize one).
    - If a broad ``/.shipwright/`` entry (older versions wrote it) is present,
      even next to the canonical ``/.shipwright/*`` block → leave the file
      alone, warn on stderr, return 'present_broad'.
    - If .gitignore contains the reports entry, the covering wildcard or the
      legacy entry → no-op (idempotent).
    - Else → append, ensuring the existing file ends with a newline first.

    Returns: 'added' | 'present' | 'present_broad' | 'skipped'
    """
    entry = reports_gitignore_entry(reports_dir)
    gi = project_root / ".gitignore"
    if not gi.exists():
        return "skipped"

    existing = gi.read_text(encoding="utf-8")
    stripped = [line.strip() for line in existing.splitlines()]
    # Broad FIRST: projects adopted with the canonical `/.shipwright/*` block
    # got the broad line appended after it by older versions, so both are
    # present and the broad one is the one that hides new tracked files.
    if any(line in BROAD_GITIGNORE_ENTRIES for line in stripped):
        print(
            "WARNING: .gitignore ignores the whole .shipwright/ directory, so new "
            "ADRs, plans and specs under it are NOT staged by `git add -A`. The "
            f"security scan only needs {entry}; replace the broad entry "
            "with it (or with the canonical block in "
            "shared/templates/shipwright-gitignore.template).",
            file=sys.stderr,
        )
        return "present_broad"

    # Match exact entries on their own line. The reports-folder entry, the
    # covering whitelist wildcard AND the legacy `/securityreports/` (kept
    # idempotent for projects mid-migration) all count as already present.
    accepted = {entry} | COVERING_GITIGNORE_ENTRIES | LEGACY_GITIGNORE_ENTRIES
    if any(line in accepted for line in stripped):
        return "present"

    # Need to append. Ensure file ends with a newline before adding our entry,
    # otherwise we'd merge with the last existing line.
    suffix = "" if existing.endswith("\n") else "\n"
    gi.write_text(existing + f"{suffix}{entry}\n", encoding="utf-8")
    return "added"
