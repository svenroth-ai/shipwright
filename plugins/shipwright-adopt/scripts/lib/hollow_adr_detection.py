"""Detect placeholder-valued ADR entries in decision_log.md (trg-6b59524b).

Split out of checks/validate_adoption.py to stay under its bloat guideline.
Kept independent of artifact_writer/adr_seeding (not imported from there) so
an OLDER already-adopted repo's decision_log.md — written before the
write-time fix existed and never regenerated since — is still
re-validatable against these same placeholder values.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

#: Placeholder title `_render_decision_log` used to emit for a retroactive
#: ADR missing `subject` before trg-6b59524b fixed it at write time.
HOLLOW_TITLE_PLACEHOLDER = "(no subject)"
#: Field-body placeholder for a present but empty context/decision value.
HOLLOW_FIELD_PLACEHOLDER = "—"  # em dash

#: A maintainer's own content lands verbatim under either of these headings
#: — harvested third-party ADRs (prior_art_harvester.py), or the merged-in
#: original decision_log.md (preserve_existing.merge_decision_log). Neither
#: is graded: a placeholder inside a MAINTAINER's own text isn't adopt's
#: defect to report.
_MAINTAINER_SECTION_RE = re.compile(
    r"^## (?:Imported decisions|Existing decision log)\b.*$", re.MULTILINE,
)

_ADR_ENTRY_HEADING_RE = re.compile(r"^#{2,3}\s+ADR-(\d+):\s*(.*)$", re.MULTILINE)
_ADR_COMMIT_LINE_RE = re.compile(r"^\s*-\s*\*\*Commit\*\*:\s*`([^`]*)`", re.MULTILINE)
_ADR_H4_SECTION_RE = re.compile(
    r"^#{4}\s+(.+?)\s*$\n(.*?)(?=^#{2,4}\s|\Z)", re.MULTILINE | re.DOTALL,
)


def count_adrs(decision_log: Path) -> int:
    """Count ADR headings (H2 or H3 — H3 is canonical, H2 kept for older
    logs). Does NOT exclude hollow entries; callers wanting a "substantive"
    count subtract ``len(find_hollow_adrs(...))`` themselves."""
    if not decision_log.is_file():
        return 0
    body = decision_log.read_text(encoding="utf-8", errors="ignore")
    return len(re.findall(r"^#{2,3}\s+ADR-\d+", body, re.MULTILINE))


def _adr_h4_sections(block: str) -> dict[str, str]:
    """Map lower-cased H4 heading name -> body text within one ADR block."""
    return {
        name.strip().lower(): body.strip()
        for name, body in _ADR_H4_SECTION_RE.findall(block)
    }


def find_hollow_adrs(decision_log: Path) -> list[str]:
    """Return one description per ADR entry that renders a placeholder in
    place of subject/commit/context/decision — content a bare heading-count
    would count toward a healthy log the same as any real entry.

    Deliberately narrow: only flags a field whose *marker is present but its
    value is the exact placeholder* (an empty ``**Commit**: `` `` `` pair, an
    em-dash section body, or the literal ``(no subject)`` title) — never a
    field whose marker is simply absent. Older/hand-written logs legitimately
    use a looser shape (no ``#### Context`` subsections at all, generic
    titles); that is a different, already-tolerated format, not this defect.
    """
    if not decision_log.is_file():
        return []
    body = decision_log.read_text(encoding="utf-8", errors="ignore")
    maintainer_section = _MAINTAINER_SECTION_RE.search(body)
    if maintainer_section is not None:
        body = body[:maintainer_section.start()]
    headings = list(_ADR_ENTRY_HEADING_RE.finditer(body))
    hollow: list[str] = []
    for i, m in enumerate(headings):
        num, title = m.group(1), m.group(2).strip()
        block = body[m.end():headings[i + 1].start() if i + 1 < len(headings) else len(body)]
        missing: list[str] = []
        if title == HOLLOW_TITLE_PLACEHOLDER:
            missing.append("subject")
        commit_m = _ADR_COMMIT_LINE_RE.search(block)
        if commit_m is not None and not commit_m.group(1).strip():
            missing.append("commit")
        sections = _adr_h4_sections(block)
        for field in ("context", "decision"):
            if field in sections and sections[field] in ("", HOLLOW_FIELD_PLACEHOLDER):
                missing.append(field)
        if missing:
            hollow.append(f"ADR-{num}: missing {', '.join(missing)}")
    return hollow


def read_snapshot_commits_total(project_root: Path) -> int | None:
    """Best-effort `git.commits_total` from `.shipwright/adopt/snapshot.json`."""
    snap = project_root / ".shipwright" / "adopt" / "snapshot.json"
    if not snap.is_file():
        return None
    try:
        data = json.loads(snap.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    val = (data.get("git") or {}).get("commits_total")
    return val if isinstance(val, int) else None


def soft_check_decision_log_density(project_root: Path) -> list[str]:
    """Warn on a thin decision_log, or a hollow entry (trg-6b59524b) — a
    hollow entry doesn't count toward "healthy" below."""
    warnings: list[str] = []
    decision_log = project_root / ".shipwright" / "agent_docs" / "decision_log.md"
    hollow = find_hollow_adrs(decision_log)
    warnings.extend(
        f".shipwright/agent_docs/decision_log.md has a hollow entry — {entry}. "
        "Layer-2 enrichment (or a hand edit) produced a placeholder instead of "
        "real content; fix it directly, or re-run enrichment and Step E."
        for entry in hollow
    )
    commits = read_snapshot_commits_total(project_root)
    if commits is None or commits <= 50:
        return warnings  # not enough signal to flag density
    total_adrs = count_adrs(decision_log)
    substantive_adrs = total_adrs - len(hollow)
    if substantive_adrs < 3:
        warnings.append(
            f".shipwright/agent_docs/decision_log.md has {substantive_adrs} "
            f"substantive ADR(s) (of {total_adrs} total; {len(hollow)} hollow) but "
            f"the repo has {commits} commits — historical data may be missing. "
            "Re-run Layer-2 enrichment or seed retroactive ADRs from "
            "git.major_refactor_commits[]."
        )
    return warnings


def soft_check_adr_seed_folder(project_root: Path) -> list[str]:
    """trg-50efc4c8: seeding is best-effort by design (a missing `shared/`
    tree must not abort an otherwise-successful adoption), so nothing else
    notices if it silently degraded (doubt-review, round 4)."""
    folder = project_root / ".shipwright" / "planning" / "adr"
    if not folder.is_dir() or not any(folder.glob("*.md")):
        return [
            ".shipwright/planning/adr/ has no seeded ADR files — Step E's "
            "ADR-folder seeding did not run or produced nothing; re-run "
            "Step E (generate_adoption_artifacts.py)."
        ]
    if not (folder / "INDEX.md").is_file():
        return [
            ".shipwright/planning/adr/INDEX.md is missing — the post-seed "
            "index refresh likely failed (see stderr from Step E); re-run "
            "shared/scripts/tools/rebuild_adr_index.py against this project."
        ]
    return []
