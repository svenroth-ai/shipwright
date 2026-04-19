"""Detective-audit orchestrator (plan v7 Option Z, Step 3+).

Runs the seven check groups (A2-A4, B1-B7, C1-C4, D1-D4, E1-E5, F1-F3,
G2-G3) and returns a structured ``AuditReport``. Group check functions
live in this module; iterate-12 / PR-4 imports go through
``audit_adapters.py`` so there's one choke point for import drift.

Step 3 sets up the skeleton and public surface. Individual group check
functions are wired incrementally by Steps 4-8.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from scripts.audit.audit_adapters import (
    Finding,
    ImportGateError,
    verify_imports,
)

# Every group callable takes ``(project_root, config, data)`` and returns
# a list of Findings. Missing groups raise ``NotImplementedError`` for now
# so the detector skeleton can be imported + unit-tested independently of
# the check implementations.
GroupFn = Callable[[Path, dict, Any], list[Finding]]


@dataclass
class AuditReport:
    """Aggregate output of a detective audit pass."""

    findings: list[Finding] = field(default_factory=list)
    fixes_applied: list[str] = field(default_factory=list)  # relative paths written
    groups_run: list[str] = field(default_factory=list)
    groups_skipped: list[tuple[str, str]] = field(default_factory=list)  # (group, reason)
    import_gate_error: str | None = None

    @property
    def any_fail(self) -> bool:
        return any(f.status == "fail" for f in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "any_fail": self.any_fail,
            "findings": [f.to_dict() for f in self.findings],
            "fixes_applied": list(self.fixes_applied),
            "groups_run": list(self.groups_run),
            "groups_skipped": [
                {"group": g, "reason": r} for g, r in self.groups_skipped
            ],
            "import_gate_error": self.import_gate_error,
        }


# ---------------------------------------------------------------------------
# Group registry. Values get populated by Steps 4-8 via ``register_group``.
# A missing group in the registry produces a "skipped: not-implemented"
# entry instead of a crash — lets the skeleton ship + be integration-
# tested early.
# ---------------------------------------------------------------------------

_GROUPS: dict[str, GroupFn] = {}


def register_group(letter: str, fn: GroupFn) -> None:
    """Register a group check function. Called by Steps 4-8."""
    letter = letter.upper()
    if letter not in {"A", "B", "C", "D", "E", "F", "G"}:
        raise ValueError(f"unknown audit group letter: {letter!r}")
    _GROUPS[letter] = fn


def registered_groups() -> dict[str, GroupFn]:
    """Expose the current registry (used by tests + run_all)."""
    return dict(_GROUPS)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG: dict[str, Any] = {
    "a4_path_fields": [
        "project_config.splits[].spec_path",
        "plan_config.sections[].section_file",
    ],
    "g2_stoplist": [
        "webui", "core", "api", "test", "tests", "ci", "deps",
        "build", "docs", "chore",
    ],
    "g2_alias_map": {
        "auth": ["auth", "authentication", "authn", "authz"],
        "payments": ["payments", "billing"],
        "db": ["db", "database", "persistence", "storage"],
    },
    "b7_exclusions": {
        "exclude_merge_commits": True,
        "exclude_authors": ["dependabot[bot]", "github-actions[bot]"],
        "exclude_path_prefixes": ["Spec/", "docs/"],
    },
}


def load_audit_config(project_root: Path) -> dict[str, Any]:
    """Load ``audit_config.json`` next to the compliance plugin.

    Falls back to built-in defaults when the file doesn't exist (fresh
    projects). User-tunable via ``--fix`` flows in a later step.
    """
    # The default config lives next to the compliance plugin; users can
    # override via a project-local ``audit_config.json`` at project root.
    override = project_root / "audit_config.json"
    if override.exists():
        try:
            user_cfg = json.loads(override.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            user_cfg = {}
        merged = dict(_DEFAULT_CONFIG)
        merged.update(user_cfg)
        return merged
    return dict(_DEFAULT_CONFIG)


# ---------------------------------------------------------------------------
# Top-level runner
# ---------------------------------------------------------------------------

def _load_compliance_data(project_root: Path) -> Any:
    """Lazy, optional data collection.

    Some test scenarios don't want to pay the full ``collect_all`` cost
    (or can't — synthetic fixtures may lack fields). Return ``None`` and
    let individual group checks decide whether they need data.
    """
    try:
        from scripts.lib.data_collector import collect_all
    except ImportError:
        return None
    try:
        return collect_all(project_root)
    except Exception:  # noqa: BLE001 — never crash the whole audit here
        return None


def run_all(
    project_root: Path,
    *,
    config: dict[str, Any] | None = None,
    only: list[str] | None = None,
    data: Any = None,
    run_gate: bool = True,
) -> AuditReport:
    """Run every registered group against ``project_root``.

    Args:
        project_root: Target project root.
        config: Optional override config (else ``load_audit_config``).
        only: Restrict to these group letters (A/B/C/...).
        data: Pre-collected ``ComplianceData``; auto-loaded when None.
        run_gate: If True, call ``verify_imports()`` first. Tests that
            only exercise detective-only groups can set this to False.
    """
    report = AuditReport()

    if run_gate:
        try:
            verify_imports()
        except ImportGateError as exc:
            report.import_gate_error = str(exc)
            return report

    cfg = config if config is not None else load_audit_config(project_root)
    payload = data if data is not None else _load_compliance_data(project_root)

    wanted = {g.upper() for g in only} if only else {"A", "B", "C", "D", "E", "F", "G"}

    for letter in sorted(wanted):
        fn = _GROUPS.get(letter)
        if fn is None:
            report.groups_skipped.append((letter, "not-implemented"))
            continue
        try:
            findings = fn(project_root, cfg, payload)
        except Exception as exc:  # noqa: BLE001 — surface, don't crash
            report.groups_skipped.append(
                (letter, f"crashed: {type(exc).__name__}: {exc}"),
            )
            continue
        report.findings.extend(findings)
        report.groups_run.append(letter)

    return report
