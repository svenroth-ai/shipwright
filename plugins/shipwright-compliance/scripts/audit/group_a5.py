"""Group A5 — CI security workflow integrity (post-Plan-v7 follow-up).

A5 audits a project's ``.github/workflows/security.yml`` against the
convention-lock constants in ``shared/scripts/lib/security_workflow.py``
laid down by ``/shipwright-adopt``'s security-scaffolding iterate.

Sub-checks:

- A5.0: setup-phase failure (shared-lib import / constants access).
  Emitted only when the convention-lock cannot be loaded — at that
  point no other A5 check can run reliably.
- A5.1: workflow file presence (``skip`` when absent).
- A5.2: YAML parseable.
- A5.3: ``permissions:`` block matches ``REQUIRED_PERMISSIONS``.
- A5.4: a step carries ``id: <CRITICAL_GATE_STEP_ID>``.
- A5.5: a step ``uses:`` an action under ``SARIF_UPLOAD_USES_PREFIX``
  AND declares ``category: <SARIF_CATEGORY>``.
- A5.6: dormant-trigger contract (``workflow_dispatch:`` active;
  ``pull_request:`` / ``schedule:`` either commented or absent).
- A5.7: SARIF upload step carries a fork-PR guard
  (``head.repo.full_name == github.repository`` substring).

Crash isolation: every sub-check is wrapped in try/except so a bug in
one check cannot mask the others. Setup-phase failures (shared-lib
import, constants access) are themselves treated as a single
``A5.0 fail`` Finding; sub-checks are skipped in that case.

Severity matrix (per the iterate spec):
- HIGH: missing critical-gate id (A5.4), wrong/missing required
  permissions (A5.3), missing ``workflow_dispatch:`` (A5.6 sub-case),
  setup failure (A5.0), parse error (A5.2)
- MEDIUM: SARIF category mismatch / no upload step (A5.5), missing
  fork guard (A5.7)
- LOW: active non-dormant ``pull_request:`` / ``schedule:`` (A5.6
  sub-case)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from scripts.audit import gate_behavior_probe
from scripts.audit.audit_adapters import (
    SOURCE_DETECTIVE_ONLY,
    Finding,
    load_shared_lib,
)


# ---------------------------------------------------------------------------
# Convention-lock loader
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Convention:
    """Snapshot of the convention-lock constants.

    Loaded once per ``run()`` call; sub-checks then read from this object
    so a missing/renamed constant fails fast at A5.0 instead of degrading
    every sub-check into a crash-finding.
    """

    workflow_path: str
    required_permissions: dict[str, str]
    critical_gate_step_id: str
    sarif_category: str
    sarif_upload_uses_prefix: str


def _load_convention() -> _Convention:
    """Load the convention-lock constants from
    ``shared/scripts/lib/security_workflow.py``.

    Raises if the module is missing, fails to import, or any required
    constant has been renamed/removed. The caller turns the raised
    exception into a single A5.0 setup-failure Finding.
    """
    mod = load_shared_lib("security_workflow")
    return _Convention(
        workflow_path=mod.WORKFLOW_PATH,
        required_permissions=dict(mod.REQUIRED_PERMISSIONS),
        critical_gate_step_id=mod.CRITICAL_GATE_STEP_ID,
        sarif_category=mod.SARIF_CATEGORY,
        sarif_upload_uses_prefix=mod.SARIF_UPLOAD_USES_PREFIX,
    )


def _apply_overrides(c: _Convention, cfg: dict[str, Any]) -> _Convention:
    """Apply user overrides from ``audit_config.json``.

    Bad-type overrides (e.g. ``a5_required_permissions`` supplied as a
    list) are silently ignored — the convention-lock default wins, keeping
    the audit safe rather than crashing on user-config drift.
    """
    workflow_path = cfg.get("a5_workflow_path")
    required = cfg.get("a5_required_permissions")
    gate_id = cfg.get("a5_critical_gate_step_id")
    category = cfg.get("a5_sarif_category")
    return _Convention(
        workflow_path=(workflow_path
                       if isinstance(workflow_path, str) and workflow_path
                       else c.workflow_path),
        required_permissions=(
            {str(k): str(v) for k, v in required.items()}
            if isinstance(required, dict) and required
            else c.required_permissions
        ),
        critical_gate_step_id=(gate_id
                               if isinstance(gate_id, str) and gate_id
                               else c.critical_gate_step_id),
        sarif_category=(category
                        if isinstance(category, str) and category
                        else c.sarif_category),
        sarif_upload_uses_prefix=c.sarif_upload_uses_prefix,
    )


# ---------------------------------------------------------------------------
# Suggested-iterate hint
# ---------------------------------------------------------------------------


def _suggest(check_id: str, label: str) -> str:
    return (
        f"/shipwright-iterate --type change "
        f"\"reconcile {check_id} ({label}) "
        f"— see .shipwright/compliance/audit-report.md\""
    )


def _truncate(detail: str, limit: int = 300) -> str:
    """Trim long parse-error / exception text so audit-report.md stays
    readable."""
    if len(detail) <= limit:
        return detail
    return detail[: limit - 3] + "..."


# ---------------------------------------------------------------------------
# YAML helpers — `on:` normalization, step iteration, fork-guard match
# ---------------------------------------------------------------------------


def _all_steps(workflow: dict) -> list[dict]:
    """Yield every step from every job. ``jobs:`` is a mapping in legal
    GitHub Actions YAML — never a list."""
    jobs = workflow.get("jobs") or {}
    if not isinstance(jobs, dict):
        return []
    out: list[dict] = []
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps") or []
        if isinstance(steps, list):
            out.extend(s for s in steps if isinstance(s, dict))
    return out


def _on_active_triggers(parsed_on: Any) -> set[str]:
    """Return the set of *active* trigger names in ``on:``.

    Handles all three legal forms:
    - scalar:   ``on: workflow_dispatch``        → {"workflow_dispatch"}
    - list:     ``on: [push, pull_request]``     → {"push", "pull_request"}
    - mapping:  ``on: {workflow_dispatch:, ...}`` → keys of the mapping

    PyYAML loads bare ``on:`` as the Python literal ``True`` because
    YAML 1.1's truthy strings include ``on``; this helper is robust
    against that quirk because the caller looks up the value under
    both keys (see ``_get_on_block``).
    """
    if isinstance(parsed_on, str):
        return {parsed_on}
    if isinstance(parsed_on, list):
        return {str(item) for item in parsed_on if isinstance(item, str)}
    if isinstance(parsed_on, dict):
        return {str(k) for k in parsed_on.keys()}
    return set()


def _get_on_block(workflow: dict) -> Any:
    """Return the ``on:`` value, accommodating PyYAML's YAML 1.1 quirk
    where bare ``on:`` parses as the Python literal ``True``."""
    if "on" in workflow:
        return workflow["on"]
    if True in workflow:
        return workflow[True]
    return None


def _normalize_expr(expr: str) -> str:
    """Strip whitespace + ``${{ ... }}`` wrapping for fork-guard substring
    matching. ``${{ x }}`` and ``x`` are the same expression for our
    purposes; the GitHub Actions runtime treats them equivalently."""
    s = str(expr).strip()
    if s.startswith("${{") and s.endswith("}}"):
        s = s[3:-2].strip()
    return re.sub(r"\s+", " ", s)


# Canonical fork-PR guard substrings. Both must be present in the
# upload-sarif step's ``if:`` for A5.7 to pass — checking for
# ``head.repo.full_name == github.repository`` alone is necessary but
# NOT sufficient (e.g. ``always() || (head.repo.full_name == ...)``
# tautologically uploads on every event including fork PRs, which
# legitimate templates never do). The legitimate canonical form is:
#
#   if: always() && (github.event_name != 'pull_request'
#                    || github.event.pull_request.head.repo.full_name == github.repository)
#
# i.e. "always upload UNLESS this is a PR from a different repo". Both
# substrings appear in every legitimate template; absence of either
# indicates the guard is broken.
_FORK_GUARD_REPO_EQ = "head.repo.full_name == github.repository"
_FORK_GUARD_PR_TYPECHECK = "event_name != 'pull_request'"


# ---------------------------------------------------------------------------
# Sub-checks
# ---------------------------------------------------------------------------


def _check_a5_3_permissions(
    workflow: dict, conv: _Convention,
) -> tuple[str, str, list[str]]:
    perms = workflow.get("permissions")
    if not isinstance(perms, dict) or not perms:
        return (
            "fail",
            f"`permissions:` block missing or empty — required keys: "
            f"{sorted(conv.required_permissions)}",
            [],
        )
    missing: list[str] = []
    wrong: list[str] = []
    for key, expected in conv.required_permissions.items():
        actual = perms.get(key)
        if actual is None:
            missing.append(f"{key} (expected {expected})")
        elif str(actual) != expected:
            wrong.append(f"{key}={actual!r} (expected {expected!r})")
    if not missing and not wrong:
        return "pass", "every required permission set to its documented value", []
    parts: list[str] = []
    if missing:
        parts.append("missing: " + ", ".join(missing))
    if wrong:
        parts.append("wrong value: " + ", ".join(wrong))
    return "fail", "; ".join(parts), [*missing, *wrong]


def _check_a5_4_critical_gate(
    workflow: dict, conv: _Convention,
) -> tuple[str, str, list[str]]:
    steps = _all_steps(workflow)
    ids = [s.get("id") for s in steps if isinstance(s.get("id"), str)]
    if conv.critical_gate_step_id in ids:
        return "pass", "critical-gate step carries the canonical id", []
    return (
        "fail",
        f"no step carries id={conv.critical_gate_step_id!r}; "
        f"found ids: {sorted(set(i for i in ids if i)) or '(none)'}",
        list(ids),
    )


def _find_sarif_upload_step(workflow: dict, conv: _Convention) -> dict | None:
    """First step whose ``uses:`` matches the canonical action.

    The match is action-name-exact + version-pin-tolerant: ``uses`` must
    equal ``<prefix>`` exactly OR start with ``<prefix>@`` (i.e.
    `github/codeql-action/upload-sarif` itself, or
    `github/codeql-action/upload-sarif@v3`, `@v4`, etc.). A bare
    ``startswith`` would also match unrelated actions like
    ``github/codeql-action/upload-sarif-fork@v1`` — verified false-positive
    risk surfaced during external code review.

    Multi-upload workflows (two upload-sarif steps with different
    categories) are out of scope: this function returns the FIRST match.
    """
    target = conv.sarif_upload_uses_prefix
    for step in _all_steps(workflow):
        uses = step.get("uses")
        if not isinstance(uses, str):
            continue
        if uses == target or uses.startswith(target + "@"):
            return step
    return None


def _check_a5_5_sarif_upload(
    workflow: dict, conv: _Convention,
) -> tuple[str, str, list[str]]:
    step = _find_sarif_upload_step(workflow, conv)
    if step is None:
        return (
            "fail",
            f"no step uses {conv.sarif_upload_uses_prefix!r} — SARIF upload absent",
            [],
        )
    # Reviewer-flagged: ``or {}`` short-circuit made the explicit "no with:
    # block" branch unreachable, then `{}.get("category")` returned None and
    # the mismatch branch said "got None, expected X" instead of pointing
    # at the missing block. Check shape FIRST, then access.
    with_block = step.get("with")
    if not isinstance(with_block, dict):
        return (
            "fail",
            "SARIF upload step missing `with:` block (or `with:` is not a "
            "mapping) — `category:` cannot be set",
            [],
        )
    category = with_block.get("category")
    if category != conv.sarif_category:
        return (
            "fail",
            f"SARIF category mismatch: got {category!r}, "
            f"expected {conv.sarif_category!r}",
            [str(category)],
        )
    return "pass", "SARIF upload step uses canonical action and category", []


def _check_a5_6_triggers(parsed: dict) -> tuple[str, str, list[str]]:
    """Dormant-trigger contract.

    The audit only enforces the spec-narrow contract:
    1. ``workflow_dispatch:`` must be present in active triggers (it gives
       the user a manual handle to fire the workflow).
    2. ``pull_request:`` and ``schedule:`` must NOT be active (they are the
       expensive auto-fire triggers; Phase B activation must be deliberate).

    Other triggers (``push:``, ``release:``, etc.) are NOT forbidden — a
    legitimate project may want tag-based releases or branch pushes to
    trigger scans. The spec narrows the dormant set to the two triggers
    that materially impact CI minutes / fork-PR security posture.

    Detection: PyYAML drops comments, so a commented-out
    ``# pull_request:`` simply doesn't appear in the parsed ``on:`` dict —
    making the parsed-structure check both simpler and more reliable than
    a line-walk regex (which previously also lived in this module before
    the parsed-dict approach proved sufficient).
    """
    on_block = _get_on_block(parsed)
    active_triggers = _on_active_triggers(on_block)

    # Special case: bare ``on:`` (no value) parses as None or as True
    # (YAML 1.1 truthiness). Either way no triggers are active — fail.
    if not active_triggers:
        return (
            "fail",
            "`on:` block declares no triggers; expected `workflow_dispatch:` active",
            [],
        )

    if "workflow_dispatch" not in active_triggers:
        return (
            "fail",
            f"`workflow_dispatch:` missing from `on:` "
            f"(found: {sorted(active_triggers)})",
            sorted(active_triggers),
        )

    # Active dormant-trigger violation: pull_request / schedule appear in
    # the parsed structure (i.e. NOT commented out).
    violations: list[str] = []
    for trigger in ("pull_request", "schedule"):
        if trigger in active_triggers:
            violations.append(trigger)
    if violations:
        return (
            "fail",
            f"non-dormant trigger active: {', '.join(violations)} "
            "— Phase B activation must be deliberate, not default",
            violations,
        )
    return (
        "pass",
        "`workflow_dispatch:` active; pull_request/schedule dormant",
        [],
    )


def _check_a5_7_fork_guard(
    workflow: dict, conv: _Convention,
) -> tuple[str, str, list[str]]:
    step = _find_sarif_upload_step(workflow, conv)
    if step is None:
        return "skip", "no SARIF upload step to inspect", []
    if_expr = step.get("if")
    if not isinstance(if_expr, str) or not if_expr.strip():
        return (
            "fail",
            "SARIF upload step lacks any `if:` condition — fork-PR guard absent",
            [],
        )
    normalized = _normalize_expr(if_expr)
    has_repo_eq = _FORK_GUARD_REPO_EQ in normalized
    has_pr_typecheck = _FORK_GUARD_PR_TYPECHECK in normalized
    if has_repo_eq and has_pr_typecheck:
        return "pass", "canonical fork-PR guard pair present in `if:`", []

    missing: list[str] = []
    if not has_repo_eq:
        missing.append(repr(_FORK_GUARD_REPO_EQ))
    if not has_pr_typecheck:
        missing.append(repr(_FORK_GUARD_PR_TYPECHECK))
    return (
        "fail",
        f"fork-PR guard incomplete — `if:` missing {', '.join(missing)} "
        f"(got {_truncate(if_expr, 120)!r}); both substrings must be "
        f"present so the upload only fires when not a fork PR",
        [if_expr],
    )


# ---------------------------------------------------------------------------
# Top-level run()
# ---------------------------------------------------------------------------


_NAMES: dict[str, str] = {
    "A5.0": "A5 setup",
    "A5.1": "Security workflow file presence",
    "A5.2": "Security workflow YAML parseable",
    "A5.3": "Workflow `permissions:` matches required",
    "A5.4": "Critical-gate step carries canonical id",
    "A5.5": "SARIF upload step + category present",
    "A5.6": "Dormant-trigger contract honored",
    "A5.7": "Fork-PR guard wired on SARIF upload",
}

_SEVERITY: dict[str, str] = {
    "A5.0": "HIGH",
    "A5.1": "HIGH",   # only used when status=fail; A5.1 normally skips
    "A5.2": "HIGH",
    "A5.3": "HIGH",
    "A5.4": "HIGH",
    "A5.5": "MEDIUM",
    "A5.6": "HIGH",   # may be downgraded to LOW for active-non-dormant case
    "A5.7": "MEDIUM",
}


def _make_finding(
    check_id: str,
    status: str,
    detail: str,
    *,
    severity: str | None = None,
    evidence: list[str] | None = None,
) -> Finding:
    sev = severity or _SEVERITY.get(check_id, "HIGH")
    return Finding(
        group="A",
        check_id=check_id,
        name=_NAMES.get(check_id, check_id),
        severity=sev,
        source=SOURCE_DETECTIVE_ONLY,
        status=status,
        detail=detail,
        evidence=list(evidence or []),
        suggested_iterate_cmd=(
            _suggest(check_id, _NAMES.get(check_id, check_id))
            if status == "fail" else None
        ),
    )


def _safe_run(
    check_id: str,
    fn: Callable[[], tuple[str, str, list[str]]],
    *,
    severity: str | None = None,
) -> Finding:
    """Run a sub-check; convert any exception into a single fail Finding."""
    try:
        status, detail, evidence = fn()
    except Exception as exc:  # noqa: BLE001 — crash isolation contract
        return _make_finding(
            check_id, "fail",
            f"check raised {type(exc).__name__}: {_truncate(str(exc))}",
            severity=severity,
        )
    return _make_finding(
        check_id, status, detail,
        severity=severity,
        evidence=evidence,
    )


def run(
    project_root: Path,
    config: dict[str, Any] | None,
    _data: Any,
) -> list[Finding]:
    """Run A5 against ``<project_root>/<WORKFLOW_PATH>``.

    Cascading control flow per the reviewer-flagged precondition contract:

    1. Setup — load the convention-lock constants. On failure: emit a
       single A5.0 fail Finding and return.
    2. A5.1 — file presence. On absent file: emit one skip Finding and
       return (skip-on-precondition pattern shared with B7 / G2 / G3).
    3. A5.2 — parse. On failure: emit one fail Finding and return.
    4. A5.3..A5.7 — structural checks, each wrapped in ``_safe_run`` for
       crash isolation.
    """
    cfg = config or {}

    # ------------------------------------------------------------------
    # Setup phase (A5.0): load the convention lock.
    # ------------------------------------------------------------------
    try:
        conv = _load_convention()
    except Exception as exc:  # noqa: BLE001 — turn into A5.0 finding
        return [_make_finding(
            "A5.0", "fail",
            f"convention lock unavailable "
            f"({type(exc).__name__}: {_truncate(str(exc))})",
        )]
    conv = _apply_overrides(conv, cfg)

    workflow_file = project_root / conv.workflow_path

    # ------------------------------------------------------------------
    # A5.1: file presence (skip-on-precondition).
    # ------------------------------------------------------------------
    if not workflow_file.is_file():
        return [_make_finding(
            "A5.1", "skip",
            f"no GitHub Actions workflow at {conv.workflow_path}",
        )]

    # ------------------------------------------------------------------
    # A5.2: YAML parse. Cascade-stop on parse failure — no point running
    # structural checks against unparseable text.
    # ------------------------------------------------------------------
    try:
        import yaml  # PyYAML — declared in compliance plugin's pyproject.toml
    except ImportError as exc:
        # A missing PyYAML is an ENV/invocation problem (the audit ran in an
        # interpreter without the compliance plugin's deps — e.g. a non-Python
        # adopt project where bare `uv run` resolves an env with no pyyaml),
        # NOT a compliance violation. Degrade to SKIP so it never lands in the
        # triage backlog as a phantom A5.0 FAIL. The invocation side (the
        # iterate/changelog Stop hooks) passes `uv run --with pyyaml` so A5
        # actually runs where a workflow exists. (C2,
        # 2026-06-02-compliance-detective-realign.)
        return [_make_finding(
            "A5.0", "skip",
            f"PyYAML unavailable — A5 workflow checks skipped "
            f"({type(exc).__name__}: {exc}); run the audit with its declared "
            f"deps (uv run --with pyyaml).",
        )]
    try:
        parsed = yaml.safe_load(
            workflow_file.read_text(encoding="utf-8", errors="replace"),
        )
    except Exception as exc:  # noqa: BLE001 — covers yaml.YAMLError + I/O
        return [_make_finding(
            "A5.2", "fail",
            f"YAML parse failed: {type(exc).__name__}: {_truncate(str(exc))}",
        )]
    if not isinstance(parsed, dict):
        return [_make_finding(
            "A5.2", "fail",
            f"workflow root is not a mapping (got {type(parsed).__name__}); "
            f"workflow YAML must be a top-level mapping",
        )]

    # ------------------------------------------------------------------
    # A5.2 pass marker, A5.3..A5.7 structural checks.
    # ------------------------------------------------------------------
    findings: list[Finding] = [_make_finding(
        "A5.2", "pass", "workflow YAML parses successfully",
    )]

    findings.append(_safe_run(
        "A5.3", lambda: _check_a5_3_permissions(parsed, conv),
    ))
    findings.append(_safe_run(
        "A5.4", lambda: _check_a5_4_critical_gate(parsed, conv),
    ))
    findings.append(_safe_run(
        "A5.5", lambda: _check_a5_5_sarif_upload(parsed, conv),
    ))

    # A5.6 — severity downgrades to LOW for the "active non-dormant
    # trigger" sub-case so reports rank cosmetic-but-deliberate-Phase-B
    # drift below structural breakage.
    a5_6 = _safe_run("A5.6", lambda: _check_a5_6_triggers(parsed))
    if a5_6.status == "fail" and "non-dormant trigger active" in a5_6.detail:
        a5_6 = _make_finding(
            "A5.6", "fail", a5_6.detail,
            severity="LOW", evidence=a5_6.evidence,
        )
    findings.append(a5_6)

    findings.append(_safe_run(
        "A5.7", lambda: _check_a5_7_fork_guard(parsed, conv),
    ))

    # A5.8 — behaviorally probe the deployed gate (executes its run: body
    # against fixture scan output). Own module to keep this file within its
    # ADR-095 bloat budget; tool-gated + kill-switch-safe (see gate_behavior_probe).
    findings.extend(gate_behavior_probe.run_if_enabled(parsed, conv))

    return findings
