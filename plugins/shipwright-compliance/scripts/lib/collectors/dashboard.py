"""Dashboard-facing collectors: splits + sections + req↔section mapping.

Reads ``shipwright_project_config.json`` (splits) and
``shipwright_build_config.json`` (sections, including archived
``split_NN_sections``). The req↔section heuristic is here too — it
links FRs to sections when the event log has no ``affected_frs``
coverage (the legacy fallback used by RTM generation).

Iterate Campaign B (B2): split out of ``data_collector.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._common import CONFIG_FILES
from ._types import RequirementInfo, SectionInfo, SplitInfo


def collect_splits(project_root: Path) -> list[SplitInfo]:
    """Read splits from project config."""
    config_path = project_root / CONFIG_FILES["project"]
    if not config_path.exists():
        return []

    config = json.loads(config_path.read_text(encoding="utf-8"))
    splits_data = config.get("splits", [])

    return [
        SplitInfo(
            name=s.get("name", "unknown"),
            status=s.get("status", "pending"),
            spec_path=s.get("spec_path"),
        )
        for s in splits_data
    ]


def _sections_from_data(
    sections_data: list[dict[str, Any]], split_name: str
) -> list[SectionInfo]:
    """Convert raw section dicts into SectionInfo objects for a given split."""
    sections: list[SectionInfo] = []
    for s in sections_data:
        findings = s.get("code_review_findings", [])
        fixed = sum(1 for f in findings if f.get("status") == "fixed")

        sections.append(SectionInfo(
            name=s.get("name", "unknown"),
            split=split_name,
            status=s.get("status", "pending"),
            commit=s.get("commit"),
            tests_passed=s.get("tests_passed", 0),
            tests_total=s.get("tests_total", 0),
            review_findings=len(findings),
            review_findings_fixed=fixed,
            review_type=s.get("review_type", ""),
            estimated_tokens=s.get("estimated_tokens_used", 0),
            estimated_api_calls=s.get("estimated_api_calls", 0),
        ))

    return sections


def collect_sections(project_root: Path) -> list[SectionInfo]:
    """Read sections from build config, including archived splits.

    The build config stores current-split sections under ``sections`` and
    archived splits under ``split_NN_sections`` keys.  This function reads
    all of them and maps each group to its parent split.
    """
    build_path = project_root / CONFIG_FILES["build"]
    if not build_path.exists():
        return []

    build_config = json.loads(build_path.read_text(encoding="utf-8"))
    splits = collect_splits(project_root)

    # Build a lookup: split number prefix -> split name
    split_by_prefix: dict[str, str] = {}
    for sp in splits:
        # Extract leading digits: "01-foundation" -> "01"
        prefix = sp.name.split("-", 1)[0]
        split_by_prefix[prefix] = sp.name

    all_sections: list[SectionInfo] = []

    # 1. Archived splits: split_NN_sections keys
    for key, value in build_config.items():
        if key.startswith("split_") and key.endswith("_sections") and isinstance(value, list):
            # "split_01_sections" -> "01"
            prefix = key.removeprefix("split_").removesuffix("_sections")
            split_name = split_by_prefix.get(prefix, f"{prefix}-unknown")
            all_sections.extend(_sections_from_data(value, split_name))

    # 2. Current split sections
    current_split = build_config.get("current_split", "")
    sections_data = build_config.get("sections", [])
    if sections_data:
        # Use current_split if available, otherwise fall back to first split
        split_name = current_split or (splits[0].name if splits else "unknown")
        all_sections.extend(_sections_from_data(sections_data, split_name))

    return all_sections


def map_requirements_to_sections(
    requirements: list[RequirementInfo],
    sections: list[SectionInfo],
) -> None:
    """Infer requirement→section mapping by matching FR split prefix to section split."""
    # Group sections by split
    sections_by_split: dict[str, list[SectionInfo]] = {}
    for sec in sections:
        sections_by_split.setdefault(sec.split, []).append(sec)

    for req in requirements:
        # Find sections in the same split
        split_sections = sections_by_split.get(req.split, [])
        # Simple heuristic: match section names against requirement text keywords
        req_lower = req.text.lower()
        for sec in split_sections:
            sec_keywords = sec.name.replace("-", " ").split()
            # If any meaningful section keyword appears in requirement text
            matches = sum(1 for kw in sec_keywords if len(kw) > 2 and kw in req_lower)
            if matches >= 1:
                req.sections.append(sec.name)
