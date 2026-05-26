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


# Accepts the 3-data-column Greenfield format
#   | FR-01.01 | login | Must |
# the 5-data-column /shipwright-adopt format
#   | FR-01.01 | /shipwright-run | Must | Orchestrate ... | enrichment.json |
# and 6+-column adopt specs that append further columns (e.g. an inference
# Confidence score) after Source:
#   | FR-01.01 | /shipwright-run | Must | Orchestrate ... | enrichment.json | 0.82 |
# Capture groups (always present): 1=ID, 2=col2 (Text or Name), 3=Priority.
# Optional groups (5-col+ only): 4=Description, 5=Source.
# Any columns beyond Source are matched and discarded.
# The semantic FR body is group(4) when present, else group(2). See ADR-031.
_FR_TABLE_RE = re.compile(
    r"^\|\s*(FR-[\d.]+)\s*\|\s*([^|]+?)\s*\|\s*(Must|Should|May)\s*\|"
    r"(?:\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|)?"  # optional Description (4) + Source (5)
    r"(?:\s*[^|]*?\s*\|)*\s*$"                # any number of further columns, ignored
)

# Rows inside a `## Removed Requirements` / `### Removed Requirements`
# section are FR rows a REMOVE-classified iterate retired. They must NOT
# count as live requirements — otherwise the RTM keeps reporting a deleted
# capability as uncovered/failing. The shared FR parser
# (shared/scripts/lib/drift_parsers.py:parse_fr_table) carries the SAME
# exclusion loop; keep the two in sync.
# Origin: iterate-2026-05-16-spec-impact-gate.
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*?)\s*$")


def collect_requirements(project_root: Path) -> list[RequirementInfo]:
    """Parse functional requirements from .shipwright/planning/*/spec.md files."""
    planning_dir = project_root / ".shipwright" / "planning"
    if not planning_dir.exists():
        return []

    requirements: list[RequirementInfo] = []

    for split_dir in sorted(planning_dir.iterdir()):
        if not split_dir.is_dir():
            continue
        spec_path = split_dir / "spec.md"
        if not spec_path.exists():
            continue

        split_name = split_dir.name
        rel_spec = f".shipwright/planning/{split_name}/spec.md"
        content = spec_path.read_text(encoding="utf-8")

        in_removed = False
        removed_level = 0
        for line in content.splitlines():
            heading = _MD_HEADING_RE.match(line)
            if heading:
                level = len(heading.group(1))
                if heading.group(2).strip().lower().startswith("removed requirements"):
                    in_removed, removed_level = True, level
                    continue
                if in_removed and level <= removed_level:
                    in_removed = False
            if in_removed:
                continue
            match = _FR_TABLE_RE.match(line)
            if match:
                # 5-col format puts the FR body in the Description column
                # (4); 3-col puts it in the Text column (2). See ADR-031.
                body = (match.group(4) or match.group(2)).strip()
                requirements.append(RequirementInfo(
                    id=match.group(1),
                    text=body,
                    priority=match.group(3),
                    split=split_name,
                    spec_path=rel_spec,
                ))

    return requirements


def collect_external_review_states(project_root: Path) -> list[ExternalReviewState]:
    """Scan .shipwright/planning/*/external_review_state.json for audit evidence.

    The marker file is written by shipwright-plan v0.3.0+ Step 5 (and by
    shipwright-iterate v0.4.0+ medium+ complexity runs). Splits without the
    marker are reported with status="missing" so compliance can flag them.
    """
    planning_dir = project_root / ".shipwright" / "planning"
    if not planning_dir.exists():
        return []

    states: list[ExternalReviewState] = []
    for split_dir in sorted(planning_dir.iterdir()):
        if not split_dir.is_dir():
            continue
        # Skip the iterate/ sub-dir — iterate runs produce run-scoped markers
        # that are audited separately via events, not per-split RTM rows.
        if split_dir.name == "iterate":
            continue

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
