"""Detective-audit orchestrator (plan v7 Option Z, Step 3+).

Runs the seven check groups (A2-A4, B1-B7, C1-C4, D1-D5, E1-E5, F1-F3,
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
    # A4 paths reflect the real shipwright config schemas as written by
    # the plan plugin (see plugins/shipwright-plan/scripts/checks/
    # write-plan-config.py + setup-planning-session.py). The dotted-path
    # grammar:
    #   - ``[]`` iterates a list at that key
    #   - ``{}`` iterates the values of a dict at that key (used when the
    #     schema keys are dynamic, e.g. split names)
    # Real shapes seen in deployed projects:
    #   - aiportal: ``plan_config.splits.<name>.plan_file`` (multi-split)
    #   - shipwright-webui (adopted): ``plan_config.spec_file`` (single-split)
    # ``project_config`` carries no on-disk path fields today (splits[]
    # entries only have name+status), so it's intentionally absent.
    "a4_path_fields": [
        "plan_config.splits.{}.plan_file",
        "plan_config.spec_file",
    ],
    "g2_stoplist": [
        # G2 ignores these scopes — they're real conventional-commit scopes
        # used in the shipwright monorepo and other adopted projects but
        # too generic to map back to a specific plan-split or component.
        # The strings here are commit-scope identifiers (NOT directory
        # paths); the inline `artifact-path-canon: legacy` markers tell
        # the canon lint to skip these literals.
        "webui", "core", "api", "test", "tests", "ci", "deps",
        "build", "docs", "chore", "deploy", "iterate", "release",
        # Cross-cutting conventions that don't carry split semantics.
        "compliance", "security", "shipwright", "scripts", "shared",  # artifact-path-canon: legacy
        # Documentation / changelog scopes (Step 13 tuning — surfaced as
        # G2 false-positives during the shipwright monorepo smoke-run).
        "changelog",
    ],
    "g2_alias_map": {
        # Map split slugs / component names to the conventional-commit
        # scope variants that should be treated as equivalent. A scope
        # passes G2 when it appears in the alias-map values OR matches a
        # known split name from project_config.splits[].name. Adopted
        # projects with no plan-config splits skip the match check.
        # Variants are scope identifiers, NOT directory paths.
        "auth": ["auth", "authentication", "authn", "authz"],
        "payments": ["payments", "billing"],
        "db": ["db", "database", "persistence", "storage"],
        "adopt": ["adopt", "adopted"],
        "plan": ["plan", "planning"],  # artifact-path-canon: legacy
    },
    "b7_exclusions": {
        "exclude_merge_commits": True,
        "exclude_authors": ["dependabot[bot]", "github-actions[bot]"],
        # ``CHANGELOG-unreleased.d/`` is a Keep-a-Changelog drop directory
        # — entries land per iterate without a corresponding event, so
        # treating them as Spec/docs-class noise prevents B7 from
        # flagging every iterate's changelog drop as uncovered drift.
        "exclude_path_prefixes": [
            "Spec/", "docs/", "CHANGELOG-unreleased.d/",
        ],
        # Glob pattern passed to ``git describe --tags --match`` to find
        # the baseline tag B7 scans from. ``v*`` matches v0.1.0, v1.2.3, …
        "last_release_tag_pattern": "v*",
    },
    # Per-rule on/off switches for B7. Set any to false to disable that
    # rule without removing the substantive exclusion list (lets users
    # keep their author allowlist while disabling the merge-commit rule
    # for archaeology runs).
    "retention": {
        "rule_a": True,  # exclude merge commits
        "rule_b": True,  # exclude CI-bot authors
        "rule_c": True,  # exclude commits whose diff stays in path_prefixes
    },
    # Group A5 — CI security workflow integrity overrides. All four are
    # escape hatches for projects that legitimately diverge from the
    # convention-lock; ``None`` means "consume the constant from
    # ``shared/scripts/lib/security_workflow.py``" (the default and
    # strongly preferred path). Bad-type overrides are silently ignored
    # by group_a5 — the audit falls back to the convention-lock value
    # rather than crashing on user-config drift.
    "a5_workflow_path": None,           # str — override WORKFLOW_PATH
    "a5_required_permissions": None,    # dict[str,str] — override REQUIRED_PERMISSIONS
    "a5_critical_gate_step_id": None,   # str — override CRITICAL_GATE_STEP_ID
    "a5_sarif_category": None,          # str — override SARIF_CATEGORY
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
    fix: bool = False,
    emit_to_triage: bool = True,
    run_id: str | None = None,
    commit: str | None = None,
) -> AuditReport:
    """Run every registered group against ``project_root``.

    Args:
        project_root: Target project root.
        config: Optional override config (else ``load_audit_config``).
        only: Restrict to these group letters (A/B/C/...).
        data: Pre-collected ``ComplianceData``; auto-loaded when None.
        run_gate: If True, call ``verify_imports()`` first. Tests that
            only exercise detective-only groups can set this to False.
        fix: If True, enable Group E auto-regeneration of stale docs.
            Each rewritten doc is appended to ``report.fixes_applied``.
            Other groups ignore the flag.
        emit_to_triage: If True (default), mirror this run's findings
            into ``.shipwright/triage.jsonl`` and auto-dismiss compliance
            items whose check_id is no longer in this run. See
            :func:`mirror_findings_to_triage`. Disable for unit tests
            that only exercise detection.
        run_id: Optional run identifier recorded on emitted triage items.
        commit: Optional commit hash recorded on emitted triage items.
            Compliance dedup uses ``match_commit=False``, so this is
            informational only.
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

    # Thread the per-run --fix flag and a write-sink for fixes_applied
    # through the config dict. Group E reads ``fix`` and appends to
    # ``fixes_applied``; other groups ignore both keys.
    cfg = dict(cfg)
    cfg["fix"] = fix
    cfg["fixes_applied"] = report.fixes_applied

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

    if emit_to_triage:
        # Best-effort — never block the audit on triage failure, but
        # surface the error on stderr so silent breakage is visible
        # (MED-5 from external code review).
        try:
            mirror_findings_to_triage(
                project_root, report, run_id=run_id, commit=commit,
            )
        except Exception as exc:  # noqa: BLE001
            import sys
            sys.stderr.write(
                f"[audit_detector] triage emission failed: "
                f"{type(exc).__name__}: {exc}\n"
            )

    return report


# ---------------------------------------------------------------------------
# AC-5 of iterate-2026-05-11-triage-inbox-1a: triage emission
# ---------------------------------------------------------------------------

_SEVERITY_MAP: dict[str, str] = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
    "INFO": "info",
}


def _import_triage_api():
    """Lazy import of the triage helpers (avoids perturbing existing module
    import order — the audit_detector skeleton must keep importing cleanly
    in environments where ``shared/scripts/`` isn't on sys.path).

    Returns ``(append_idempotent, mark_status, read_all_items)`` on success
    or ``(None, None, None)`` on import failure.
    """
    import sys

    shared_scripts = Path(__file__).resolve().parents[4] / "shared" / "scripts"
    if str(shared_scripts) not in sys.path:
        sys.path.insert(0, str(shared_scripts))
    try:
        from triage import (  # noqa: PLC0415
            append_triage_item_idempotent,
            mark_status,
            read_all_items,
        )
        return append_triage_item_idempotent, mark_status, read_all_items
    except ImportError:
        return None, None, None


def mirror_findings_to_triage(
    project_root: Path,
    report: AuditReport,
    *,
    run_id: str | None = None,
    commit: str | None = None,
) -> dict[str, int]:
    """Mirror audit findings to ``.shipwright/triage.jsonl``.

    For each ``Finding`` with ``status == "fail"``: append a triage item
    via ``append_triage_item_idempotent`` with ``source="compliance"``,
    ``dedup_key=check_id``, ``match_commit=False``. Idempotent across
    sessions — the same finding code on the same project stays as a
    single triage item until the operator promotes or dismisses it.

    For currently-``triage`` items with ``source=="compliance"`` whose
    ``dedupKey`` is NOT in this run's failed findings: mark ``dismissed``
    with ``reason="auditResolved"`` (HIGH-2 from external review:
    auto-dismiss applies only to currently-``triage`` items; items
    previously promoted or dismissed stay terminal).

    Best-effort: per-item errors are swallowed. Returns
    ``{"appended": N, "dismissed": N}`` so callers can log telemetry.
    """
    append_idempotent, mark_status_fn, read_all_items = _import_triage_api()
    if append_idempotent is None:
        return {"appended": 0, "dismissed": 0}

    fail_findings = [f for f in report.findings if f.status == "fail"]
    current_codes = {f.check_id for f in fail_findings}

    appended = 0
    for f in fail_findings:
        sev = _SEVERITY_MAP.get(f.severity.upper(), "medium")
        title = f"{f.group}/{f.check_id}: {f.name}"[:160]
        detail_parts: list[str] = []
        if f.detail:
            detail_parts.append(f.detail)
        if f.evidence:
            detail_parts.append("evidence: " + "; ".join(str(e) for e in f.evidence))
        if f.suggested_iterate_cmd:
            detail_parts.append(f"hint: {f.suggested_iterate_cmd}")
        detail = " | ".join(detail_parts) or f.name

        try:
            new_id = append_idempotent(
                project_root,
                source="compliance",
                severity=sev,
                kind="compliance",
                title=title,
                detail=detail,
                dedup_key=f.check_id,
                run_id=run_id,
                commit=commit,
                match_commit=False,
                window_seconds=None,  # cross-session indefinite dedup
                                      # while item stays in `triage` state
                                      # (Gemini HIGH from code review)
            )
            if new_id is not None:
                appended += 1
        except Exception:  # noqa: BLE001
            continue

    dismissed = 0
    try:
        for item in read_all_items(project_root):
            if item.get("source") != "compliance":
                continue
            if item.get("status") != "triage":
                continue
            dk = item.get("dedupKey")
            if dk and dk not in current_codes:
                try:
                    mark_status_fn(
                        project_root,
                        item["id"],
                        new_status="dismissed",
                        by="auditDetector",
                        reason="auditResolved",
                    )
                    dismissed += 1
                except Exception:  # noqa: BLE001
                    continue
    except Exception:  # noqa: BLE001
        pass

    return {"appended": appended, "dismissed": dismissed}
