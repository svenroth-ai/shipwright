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
    estimated_tokens: int = 0
    estimated_api_calls: int = 0


@dataclass
class DecisionEntry:
    section: str
    timestamp: str
    decisions: list[dict] = field(default_factory=list)


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
class ComplianceData:
    project_root: Path
    configs: dict[str, dict] = field(default_factory=dict)
    splits: list[SplitInfo] = field(default_factory=list)
    sections: list[SectionInfo] = field(default_factory=list)
    decisions: list[DecisionEntry] = field(default_factory=list)
    commits: list[CommitEntry] = field(default_factory=list)
    dependencies: list[DependencyInfo] = field(default_factory=list)
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

def _map_sections_to_splits(
    splits: list[SplitInfo], sections_data: list[dict[str, Any]]
) -> list[SectionInfo]:
    """Map build config sections to their parent splits.

    Heuristic: section names often start with a number prefix.
    If we can't determine the parent split, use the first split name.
    """
    sections: list[SectionInfo] = []
    default_split = splits[0].name if splits else "unknown"

    for s in sections_data:
        name = s.get("name", "unknown")
        findings = s.get("code_review_findings", [])
        fixed = sum(1 for f in findings if f.get("status") == "fixed")

        sections.append(SectionInfo(
            name=name,
            split=default_split,  # simplified — all sections belong to first split
            status=s.get("status", "pending"),
            commit=s.get("commit"),
            tests_passed=s.get("tests_passed", 0),
            tests_total=s.get("tests_total", 0),
            review_findings=len(findings),
            review_findings_fixed=fixed,
            estimated_tokens=s.get("estimated_tokens_used", 0),
            estimated_api_calls=s.get("estimated_api_calls", 0),
        ))

    return sections


def collect_sections(project_root: Path) -> list[SectionInfo]:
    """Read sections from build config, mapping to splits."""
    build_path = project_root / CONFIG_FILES["build"]
    if not build_path.exists():
        return []

    build_config = json.loads(build_path.read_text(encoding="utf-8"))
    sections_data = build_config.get("sections", [])

    if not sections_data:
        return []

    splits = collect_splits(project_root)
    return _map_sections_to_splits(splits, sections_data)


# ---------------------------------------------------------------------------
# Decision Log
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^## (.+?) \((.+?)\)\s*$")
_DECISION_RE = re.compile(r"^- \*\*(.+?)\*\* \[(.+?)\]\s*$")
_REASON_RE = re.compile(r"^\s+- Reason: (.+)$")


def collect_decision_log(project_root: Path) -> list[DecisionEntry]:
    """Parse agent_docs/decision_log.md into structured entries."""
    log_path = project_root / "agent_docs" / "decision_log.md"
    if not log_path.exists():
        return []

    content = log_path.read_text(encoding="utf-8")
    entries: list[DecisionEntry] = []
    current_entry: DecisionEntry | None = None
    current_decision: dict | None = None

    for line in content.splitlines():
        section_match = _SECTION_RE.match(line)
        if section_match:
            if current_entry and current_entry.decisions:
                entries.append(current_entry)
            current_entry = DecisionEntry(
                section=section_match.group(1),
                timestamp=section_match.group(2),
            )
            current_decision = None
            continue

        if current_entry is None:
            continue

        decision_match = _DECISION_RE.match(line)
        if decision_match:
            current_decision = {
                "decision": decision_match.group(1),
                "category": decision_match.group(2),
                "reason": "",
            }
            current_entry.decisions.append(current_decision)
            continue

        if current_decision is not None:
            reason_match = _REASON_RE.match(line)
            if reason_match:
                current_decision["reason"] = reason_match.group(1)

    # Don't forget the last entry
    if current_entry and current_entry.decisions:
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
# Main collector
# ---------------------------------------------------------------------------

def collect_all(project_root: Path) -> ComplianceData:
    """Collect all compliance-relevant data from a project."""
    project_root = Path(project_root).resolve()

    return ComplianceData(
        project_root=project_root,
        configs=collect_configs(project_root),
        splits=collect_splits(project_root),
        sections=collect_sections(project_root),
        decisions=collect_decision_log(project_root),
        commits=collect_git_history(project_root),
        dependencies=collect_dependencies(project_root),
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
