"""RTM-facing collectors: decision log + requirements + ER states.

Three sources feed the Requirements Traceability Matrix:

* ``.shipwright/agent_docs/decision_log.md`` — ADR-style decision entries
  in either the old verbose format or the compact format.
* ``.shipwright/planning/*/spec.md`` — functional requirement tables
  (3-, 5-, and 6-column variants — see ADR-031). ``## Removed
  Requirements`` sections are excluded so retired FRs don't accrue
  false uncovered-row counts.
* ``.shipwright/planning/*/external_review_state.json`` — audit
  evidence that the external-review quality gate was considered.

Iterate Campaign B (B2): split out of ``data_collector.py``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ._lib_loader import load_shared_lib
from ._types import (
    DecisionEntry,
    ExternalReviewState,
    RequirementInfo,
    WorkEvent,
)


# Old format: ## ADR-001 | date | section | Commit hash
_ADR_OLD_HEADER_RE = re.compile(r"^## ADR-\d+ \| (.+?) \| (.+?) \| Commit (.+)$")
_ADR_OLD_FIELD_RE = re.compile(r"^### (Status|Context|Decision|Consequences):?\s*(.*)$")
_ADR_OLD_REJECTED_RE = re.compile(r"^- Alternatives rejected: (.+)$")

# Compact format: ### ADR-001: Title  (bullet-point fields)
_ADR_COMPACT_HEADER_RE = re.compile(r"^### ADR-\d+:\s*(.+)$")
_ADR_COMPACT_FIELD_RE = re.compile(
    r"^- \*\*(Date|Section|Context|Decision|Commit|Rationale|Consequences|Rejected):\*\*\s*(.+)$"
)


def collect_decision_log(project_root: Path) -> list[DecisionEntry]:
    """Parse .shipwright/agent_docs/decision_log.md into structured entries.

    Supports both the old verbose format (## ADR-NNN | ...) and the
    compact format (### ADR-NNN: Title with bullet-point fields).
    """
    log_path = project_root / ".shipwright" / "agent_docs" / "decision_log.md"
    if not log_path.exists():
        return []

    content = log_path.read_text(encoding="utf-8")
    entries: list[DecisionEntry] = []
    current_entry: DecisionEntry | None = None
    current_field: str | None = None
    current_decision: dict | None = None

    for line in content.splitlines():
        # --- Compact format header ---
        compact_match = _ADR_COMPACT_HEADER_RE.match(line)
        if compact_match:
            if current_entry and current_decision:
                current_entry.decisions.append(current_decision)
                entries.append(current_entry)
            # Fields filled in by subsequent bullet lines
            current_entry = DecisionEntry(section="", timestamp="", commit="")
            current_decision = {"decision": "", "context": "", "consequences": "", "rejected": ""}
            current_field = None
            continue

        # --- Compact format field ---
        if current_entry is not None and current_decision is not None:
            compact_field = _ADR_COMPACT_FIELD_RE.match(line)
            if compact_field:
                field_name = compact_field.group(1)
                value = compact_field.group(2).strip()
                if field_name == "Section":
                    current_entry.section = value
                elif field_name == "Date":
                    current_entry.timestamp = value
                elif field_name == "Commit":
                    current_entry.commit = value
                elif field_name == "Decision":
                    current_decision["decision"] = value
                elif field_name == "Context":
                    current_decision["context"] = value
                elif field_name in ("Consequences", "Rationale"):
                    current_decision["consequences"] = value
                elif field_name == "Rejected":
                    current_decision["rejected"] = value
                current_field = None
                continue

        # --- Old verbose format header ---
        header_match = _ADR_OLD_HEADER_RE.match(line)
        if header_match:
            if current_entry and current_decision:
                current_entry.decisions.append(current_decision)
                entries.append(current_entry)
            current_entry = DecisionEntry(
                section=header_match.group(2),
                timestamp=header_match.group(1),
                commit=header_match.group(3),
            )
            current_decision = {"decision": "", "context": "", "consequences": "", "rejected": ""}
            current_field = None
            continue

        if current_entry is None or current_decision is None:
            continue

        # --- Old verbose format fields ---
        field_match = _ADR_OLD_FIELD_RE.match(line)
        if field_match:
            field_name = field_match.group(1).lower()
            inline_value = field_match.group(2).strip()
            current_field = field_name
            if inline_value:
                current_decision[field_name] = inline_value
            continue

        rejected_match = _ADR_OLD_REJECTED_RE.match(line)
        if rejected_match:
            current_decision["rejected"] = rejected_match.group(1)
            continue

        # Accumulate multi-line content for the current field
        stripped = line.strip()
        if current_field and stripped and not line.startswith("---"):
            if stripped.startswith("- "):
                stripped = stripped[2:]
            existing = current_decision.get(current_field, "")
            current_decision[current_field] = (existing + " " + stripped).strip() if existing else stripped

    # Finalize last entry
    if current_entry and current_decision:
        current_entry.decisions.append(current_decision)
        entries.append(current_entry)

    return entries


def collect_requirements(project_root: Path) -> list[RequirementInfo]:
    """Parse functional requirements from .shipwright/planning/*/spec.md files.

    Rows are read by ``lib.fr_table_reader`` — the one header-driven reader
    (campaign S4). This function used to carry a copy of the positional regex
    that was byte-identical to ``drift_parsers``', plus a removed-section loop
    that was a semantic clone of the same file's; nothing enforced the second
    half, and the pair produced FV-3 (a row wider than its header shifted the
    body column, so the RTM rendered the wrong requirement text).
    """
    planning_dir = project_root / ".shipwright" / "planning"

    requirements: list[RequirementInfo] = []
    read_active_fr_rows = load_shared_lib("fr_table_reader").read_active_fr_rows

    # guard="exists" preserves this walk raising NotADirectoryError on a
    # planning FILE. Its claimed mirror, drift_parsers, swallows the read_text
    # OSError that follows; this one has no try/except at all. Both divergences
    # are frozen here, not reconciled (campaign S2b owns that).
    iter_spec_files = load_shared_lib("planning_discovery").iter_spec_files
    for spec_path in iter_spec_files(planning_dir, guard="exists"):
        split_name = spec_path.parent.name
        rel_spec = f".shipwright/planning/{split_name}/spec.md"
        content = spec_path.read_text(encoding="utf-8")

        requirements.extend(
            RequirementInfo(
                id=row.id,
                text=row.text,
                priority=row.priority,
                split=split_name,
                spec_path=rel_spec,
            )
            for row in read_active_fr_rows(content)
        )

    return requirements


def collect_external_review_states(project_root: Path) -> list[ExternalReviewState]:
    """Scan .shipwright/planning/*/external_review_state.json for audit evidence.

    The marker file is written by shipwright-plan v0.3.0+ Step 5 (and by
    shipwright-iterate v0.4.0+ medium+ complexity runs). Splits without the
    marker are reported with status="missing" so compliance can flag them.
    """
    planning_dir = project_root / ".shipwright" / "planning"

    states: list[ExternalReviewState] = []
    # Split DIRS, not spec files: this is the only call site that emits a row
    # for a split that LACKS its target file, so it cannot enumerate the files.
    # include_iterate=False — iterate runs produce run-scoped markers that are
    # audited separately via events, not per-split RTM rows.
    iter_split_dirs = load_shared_lib("planning_discovery").iter_split_dirs
    for split_dir in iter_split_dirs(planning_dir, guard="exists", include_iterate=False):
        marker_path = split_dir / "external_review_state.json"
        if not marker_path.exists():
            states.append(ExternalReviewState(split=split_dir.name, status="missing"))
            continue

        try:
            data = json.loads(marker_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            states.append(ExternalReviewState(split=split_dir.name, status="missing"))
            continue

        states.append(ExternalReviewState(
            split=split_dir.name,
            status=str(data.get("status", "missing")),
            provider=data.get("provider"),
            findings_count=int(data.get("findings_count", 0) or 0),
            self_review_fallback_ran=bool(data.get("self_review_fallback_ran", False)),
            reason=data.get("reason"),
            timestamp=str(data.get("timestamp", "")),
        ))

    return states


def map_requirements_to_events(
    requirements: list[RequirementInfo],
    work_events: list[WorkEvent],
) -> None:
    """Map requirements to work events via affected_frs field."""
    fr_to_events: dict[str, list[str]] = {}
    for we in work_events:
        for fr_id in we.affected_frs:
            fr_to_events.setdefault(fr_id, []).append(
                we.section if we.source == "build" else we.id
            )

    for req in requirements:
        event_refs = fr_to_events.get(req.id, [])
        if event_refs:
            req.sections = event_refs
