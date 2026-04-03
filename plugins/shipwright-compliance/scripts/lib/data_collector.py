"""Central data aggregator for compliance reporting.

Reads all Shipwright config files, decision logs, git history, and dependency
manifests from a target project. Returns structured dataclasses consumed by
all report generators.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SplitInfo:
    name: str
    status: str  # "complete" | "in_progress" | "pending"
    spec_path: str | None = None


@dataclass
class SectionInfo:
    name: str
    split: str
    status: str
    commit: str | None = None
    tests_passed: int = 0
    tests_total: int = 0
    review_findings: int = 0
    review_findings_fixed: int = 0
    review_type: str = ""  # "self-review" | "full-review" | "" (unknown)
    estimated_tokens: int = 0
    estimated_api_calls: int = 0


@dataclass
class DecisionEntry:
    section: str
    timestamp: str
    commit: str = ""
    decisions: list[dict] = field(default_factory=list)
    # Each dict: {"decision": str, "context": str, "consequences": str, "rejected": str}


@dataclass
class CommitEntry:
    hash: str
    type: str
    scope: str | None
    description: str
    date: str
    author: str


@dataclass
class DependencyInfo:
    name: str
    version: str
    dep_type: str  # "runtime" | "dev"
    license: str = "unknown"


@dataclass
class TestResults:
    """Aggregated test results from test phase (shipwright_test_results.json)."""
    status: str = ""  # "pass" | "fail"
    timestamp: str = ""
    unit_passed: int = 0
    unit_total: int = 0
    unit_duration_s: float = 0
    smoke_status: str = ""  # "pass" | "fail" | "skip" | "skipped"
    smoke_url: str = ""
    smoke_response_ms: int = 0
    e2e_passed: int = 0
    e2e_total: int = 0
    e2e_failures: list[str] = field(default_factory=list)
    e2e_skipped: bool = False
    e2e_skip_reason: str = ""
    visual_passed: int = 0
    visual_total: int = 0
    visual_skipped: bool = False
    visual_skip_reason: str = ""


@dataclass
class RequirementInfo:
    """A functional requirement parsed from spec.md."""
    id: str           # "FR-02.01"
    text: str         # "The system SHALL..."
    priority: str     # "Must" | "Should" | "May"
    split: str        # "02-course-platform"
    spec_path: str = ""  # Relative path to spec.md
    sections: list[str] = field(default_factory=list)


@dataclass
class ComplianceData:
    project_root: Path
    configs: dict[str, dict] = field(default_factory=dict)
    splits: list[SplitInfo] = field(default_factory=list)
    sections: list[SectionInfo] = field(default_factory=list)
    decisions: list[DecisionEntry] = field(default_factory=list)
    commits: list[CommitEntry] = field(default_factory=list)
    dependencies: list[DependencyInfo] = field(default_factory=list)
    test_results: TestResults | None = None
    requirements: list[RequirementInfo] = field(default_factory=list)
    test_file_map: dict[str, list[str]] = field(default_factory=dict)  # section -> [test file paths]
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Config files
# ---------------------------------------------------------------------------

CONFIG_FILES = {
    "run": "shipwright_run_config.json",
    "project": "shipwright_project_config.json",
    "plan": "shipwright_plan_config.json",
    "build": "shipwright_build_config.json",
}


def collect_configs(project_root: Path) -> dict[str, dict]:
    """Read all shipwright config files. Returns empty dicts for missing files."""
    configs: dict[str, dict] = {}
    for key, filename in CONFIG_FILES.items():
        path = project_root / filename
        if path.exists():
            configs[key] = json.loads(path.read_text(encoding="utf-8"))
        else:
            configs[key] = {}
    return configs


# ---------------------------------------------------------------------------
# Splits
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Decision Log
# ---------------------------------------------------------------------------

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
    """Parse agent_docs/decision_log.md into structured entries.

    Supports both the old verbose format (## ADR-NNN | ...) and the
    compact format (### ADR-NNN: Title with bullet-point fields).
    """
    log_path = project_root / "agent_docs" / "decision_log.md"
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


# ---------------------------------------------------------------------------
# Git History
# ---------------------------------------------------------------------------

_CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|refactor|docs|test|chore|style|perf|ci|build)"
    r"(?:\(([^)]+)\))?"
    r":\s*(.+)$"
)


def collect_git_history(project_root: Path) -> list[CommitEntry]:
    """Parse git log for conventional commits."""
    try:
        result = subprocess.run(
            ["git", "log", "--format=%H|%s|%an|%aI", "--no-merges"],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            encoding="utf-8",
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    if result.returncode != 0:
        return []

    commits: list[CommitEntry] = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue

        hash_, subject, author, date = parts
        match = _CONVENTIONAL_RE.match(subject)
        if match:
            commits.append(CommitEntry(
                hash=hash_[:12],
                type=match.group(1),
                scope=match.group(2),
                description=match.group(3),
                date=date,
                author=author,
            ))
        else:
            # Non-conventional commits get type "other"
            commits.append(CommitEntry(
                hash=hash_[:12],
                type="other",
                scope=None,
                description=subject,
                date=date,
                author=author,
            ))

    return commits


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def collect_dependencies(project_root: Path) -> list[DependencyInfo]:
    """Read dependencies from package.json or pyproject.toml."""
    deps: list[DependencyInfo] = []

    # npm/Node.js
    pkg_path = project_root / "package.json"
    if pkg_path.exists():
        pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
        for name, version in pkg.get("dependencies", {}).items():
            license_ = _detect_npm_license(project_root, name)
            deps.append(DependencyInfo(name=name, version=version, dep_type="runtime", license=license_))
        for name, version in pkg.get("devDependencies", {}).items():
            license_ = _detect_npm_license(project_root, name)
            deps.append(DependencyInfo(name=name, version=version, dep_type="dev", license=license_))

    # Python (pyproject.toml)
    pyproject_path = project_root / "pyproject.toml"
    if pyproject_path.exists():
        deps.extend(_parse_pyproject_deps(pyproject_path))

    return deps


def _detect_npm_license(project_root: Path, package_name: str) -> str:
    """Try to read license from node_modules/{pkg}/package.json."""
    pkg_json = project_root / "node_modules" / package_name / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            return data.get("license", "unknown")
        except (json.JSONDecodeError, OSError):
            pass
    return "unknown"


def _parse_pyproject_deps(pyproject_path: Path) -> list[DependencyInfo]:
    """Parse dependencies from pyproject.toml (simple regex, no toml lib needed)."""
    deps: list[DependencyInfo] = []
    content = pyproject_path.read_text(encoding="utf-8")

    # Simple extraction of dependencies array
    in_deps = False
    in_dev = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "dependencies = [":
            in_deps = True
            in_dev = False
            continue
        if "dev" in stripped and "= [" in stripped:
            in_deps = True
            in_dev = True
            continue
        if in_deps and stripped == "]":
            in_deps = False
            continue
        if in_deps and stripped.startswith('"'):
            # Parse "package>=version" or "package"
            dep_str = stripped.strip('",')
            match = re.match(r"^([a-zA-Z0-9_-]+)(?:[><=!~]+(.+))?$", dep_str)
            if match:
                deps.append(DependencyInfo(
                    name=match.group(1),
                    version=match.group(2) or "any",
                    dep_type="dev" if in_dev else "runtime",
                ))

    return deps


# ---------------------------------------------------------------------------
# Test Results
# ---------------------------------------------------------------------------

def _parse_test_results_file(path: Path) -> TestResults | None:
    """Parse a single test results JSON file into a TestResults object."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    unit = data.get("unit", {})
    smoke = data.get("smoke", {})
    e2e = data.get("e2e", {})
    visual = data.get("visual", {})

    return TestResults(
        status=data.get("status", ""),
        timestamp=data.get("timestamp", ""),
        unit_passed=unit.get("passed", 0),
        unit_total=unit.get("total", 0),
        unit_duration_s=unit.get("duration_s", 0),
        smoke_status=smoke.get("status", ""),
        smoke_url=smoke.get("url", ""),
        smoke_response_ms=smoke.get("response_ms", 0),
        e2e_passed=e2e.get("passed", 0),
        e2e_total=e2e.get("total", 0),
        e2e_failures=e2e.get("failures", []),
        e2e_skipped=e2e.get("skipped", False),
        e2e_skip_reason=e2e.get("reason", ""),
        visual_passed=visual.get("passed", 0),
        visual_total=visual.get("total", 0),
        visual_skipped=visual.get("skipped", False),
        visual_skip_reason=visual.get("skip_reason", ""),
    )


def collect_test_results(project_root: Path) -> TestResults | None:
    """Read and aggregate test results from current + archived split results.

    Reads split_*_test_results.json (archived) and shipwright_test_results.json
    (current), aggregating unit/e2e counts across all splits.
    """
    all_results: list[TestResults] = []

    # Archived split results
    for f in sorted(project_root.glob("split_*_test_results.json")):
        tr = _parse_test_results_file(f)
        if tr:
            all_results.append(tr)

    # Current results
    current = project_root / "shipwright_test_results.json"
    if current.exists():
        tr = _parse_test_results_file(current)
        if tr:
            all_results.append(tr)

    if not all_results:
        return None

    if len(all_results) == 1:
        return all_results[0]

    # Aggregate across splits
    return TestResults(
        status="pass" if all(r.status == "pass" for r in all_results) else "fail",
        timestamp=all_results[-1].timestamp,  # Most recent
        unit_passed=sum(r.unit_passed for r in all_results),
        unit_total=sum(r.unit_total for r in all_results),
        unit_duration_s=sum(r.unit_duration_s for r in all_results),
        smoke_status=all_results[-1].smoke_status,  # Latest split's smoke
        smoke_url=all_results[-1].smoke_url,
        smoke_response_ms=all_results[-1].smoke_response_ms,
        e2e_passed=sum(r.e2e_passed for r in all_results),
        e2e_total=sum(r.e2e_total for r in all_results),
        e2e_failures=[f for r in all_results for f in r.e2e_failures],
        e2e_skipped=all_results[-1].e2e_skipped,
        e2e_skip_reason=all_results[-1].e2e_skip_reason,
        visual_passed=sum(r.visual_passed for r in all_results),
        visual_total=sum(r.visual_total for r in all_results),
        visual_skipped=all_results[-1].visual_skipped,
        visual_skip_reason=all_results[-1].visual_skip_reason,
    )


# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------

_FR_TABLE_RE = re.compile(
    r"^\| (FR-[\d.]+)\s*\|\s*(.+?)\s*\|\s*(Must|Should|May)\s*\|$"
)


def collect_requirements(project_root: Path) -> list[RequirementInfo]:
    """Parse functional requirements from planning/*/spec.md files."""
    planning_dir = project_root / "planning"
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
        rel_spec = f"planning/{split_name}/spec.md"
        content = spec_path.read_text(encoding="utf-8")

        for line in content.splitlines():
            match = _FR_TABLE_RE.match(line)
            if match:
                requirements.append(RequirementInfo(
                    id=match.group(1),
                    text=match.group(2).strip(),
                    priority=match.group(3),
                    split=split_name,
                    spec_path=rel_spec,
                ))

    return requirements


def _map_requirements_to_sections(
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


# ---------------------------------------------------------------------------
# Test file mapping
# ---------------------------------------------------------------------------

def collect_test_files(project_root: Path) -> dict[str, list[str]]:
    """Scan tests/ directory and map test files to sections by path convention.

    Returns dict: section_name -> [relative test file paths].
    """
    test_dir = project_root / "tests"
    if not test_dir.exists():
        return {}

    file_map: dict[str, list[str]] = {}
    for test_file in test_dir.rglob("*.test.*"):
        rel_path = str(test_file.relative_to(project_root)).replace("\\", "/")
        # Use the file path as-is; grouping by section done at report level
        file_map.setdefault("_all", []).append(rel_path)

    return file_map


# ---------------------------------------------------------------------------
# Main collector
# ---------------------------------------------------------------------------

def collect_all(project_root: Path) -> ComplianceData:
    """Collect all compliance-relevant data from a project."""
    project_root = Path(project_root).resolve()

    sections = collect_sections(project_root)
    requirements = collect_requirements(project_root)
    _map_requirements_to_sections(requirements, sections)

    return ComplianceData(
        project_root=project_root,
        configs=collect_configs(project_root),
        splits=collect_splits(project_root),
        sections=sections,
        decisions=collect_decision_log(project_root),
        commits=collect_git_history(project_root),
        dependencies=collect_dependencies(project_root),
        test_results=collect_test_results(project_root),
        requirements=requirements,
        test_file_map=collect_test_files(project_root),
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
