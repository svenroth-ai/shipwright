#!/usr/bin/env python3
"""GitHub findings -> triage inbox importer.

**Action-unit model** (iterate-2026-05-20-triage-launch-surface, supersedes
the per-finding mapping shipped in iterate-2026-05-19): GitHub findings
collapse into a tiny number of operator-actionable items rather than one
triage item per upstream finding. GitHub itself is the per-finding store —
this importer's job is to emit "there is work here, here is how to start
it", not to mirror that database.

  - code-scanning + Dependabot  -> ``gh-security:{owner}/{repo}`` (one unit
    per repo; ``launchPayload`` starts with ``/shipwright-security``).
  - secret-scanning             -> ``gh-secrets:{owner}/{repo}`` (one unit
    per repo; ``launchPayload`` is a whitelist-only rotation checklist —
    no slash command, no alert content, secret rotation is manual).
  - failed default-branch CI    -> ``gh-ci:{workflow_id}`` (one unit per
    failing workflow; dedup key drops the ``head_sha`` so the payload is
    stable across reruns and links to the workflow PAGE URL, not a single
    run).

Dedup keys remain stable and namespaced; ``match_commit=False`` +
``window_seconds=None`` so a finding stays exactly one open inbox item
until it clears.

Auto-resolve mirrors ADR-052: a stale open item whose key left the current
finding set is dismissed with ``reason="githubResolved"`` — scoped strictly
to the three owned key prefixes, and ONLY for sources whose fetch actually
succeeded.

**Legacy migration** (one-shot): if a project's ``triage.jsonl`` predates
this iterate it carries per-finding items with prefixes
``github:code-scanning:`` / ``github:dependabot:`` /
``github:secret-scanning:`` / ``github-ci:{wf}:{sha}``. The first
successful per-source fetch dismisses the corresponding open legacy items
with ``reason="schemaMigration"`` — gated PER ORIGINAL SOURCE, never
inferred from another source's success (preserves the ADR-052 fail-soft
invariant; review finding #3).

See sibling ``github_api`` for the `gh` client and the throttled
SessionStart entry point ``hooks/import_github_findings.py``.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import github_api
from triage import (
    SEVERITY_RANK,
    append_triage_item_idempotent,
    mark_status,
    read_all_items,
)

SOURCE = "github"
STATE_FILENAME = "github_import_state.json"
DEFAULT_THROTTLE_HOURS = 6.0
_ENV_THROTTLE = "SHIPWRIGHT_GITHUB_IMPORT_THROTTLE_HOURS"

# GitHub severity vocab -> canonical triage severity. `error/warning/note`
# are code-scanning `rule.severity` levels; the rest are the GHAS
# `security_severity_level` / advisory `severity` vocab.
_GH_SEVERITY_TO_TRIAGE = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "error": "high",
    "warning": "medium",
    "note": "low",
}

# Workflow-run conclusions that count as a failure worth triaging.
_FAILED_CONCLUSIONS = frozenset({"failure", "startup_failure", "timed_out"})

# Action-unit dedup-key prefixes this producer owns. The auto-resolve pass
# is scoped strictly to these (ADR-052).
PREFIX_SECURITY = "gh-security:"
PREFIX_SECRETS = "gh-secrets:"
PREFIX_CI = "gh-ci:"
_OWNED_PREFIXES = (PREFIX_SECURITY, PREFIX_SECRETS, PREFIX_CI)

# Legacy per-finding prefixes from iterate-2026-05-19. Migrated on the
# first successful fetch of the corresponding source; never resolved from
# a failed fetch (review finding #3).
_LEGACY_CODE_SCANNING = "github:code-scanning:"
_LEGACY_DEPENDABOT = "github:dependabot:"
_LEGACY_SECRET_SCANNING = "github:secret-scanning:"
_LEGACY_CI = "github-ci:"

# Map: which legacy prefix gets migrated when which producer source succeeds.
_LEGACY_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("code_scanning", _LEGACY_CODE_SCANNING),
    ("dependabot", _LEGACY_DEPENDABOT),
    ("secret_scanning", _LEGACY_SECRET_SCANNING),
    ("runs", _LEGACY_CI),
)


# ---------------------------------------------------------------------------
# Severity helpers
# ---------------------------------------------------------------------------

def triage_severity(gh_value: str | None) -> str:
    """Map a GitHub severity token to a canonical triage severity.

    Unknown / missing values fall back to ``medium`` — a finding is never
    dropped for an unrecognised severity.
    """
    return _GH_SEVERITY_TO_TRIAGE.get((gh_value or "").lower(), "medium")


def _kind_for(severity: str) -> str:
    """critical/high findings are bugs; lower severities are improvements."""
    return "bug" if severity in ("critical", "high") else "improvement"


def _max_severity(severities: list[str]) -> str:
    """Pick the most severe of a list (lowest SEVERITY_RANK wins).

    Returns ``"medium"`` for an empty list — a defensive default so an
    accidentally-empty caller never gets a crash.
    """
    if not severities:
        return "medium"
    return min(severities, key=lambda s: SEVERITY_RANK.get(s, 99))


def _security_url(owner_repo: str) -> str:
    return f"https://github.com/{owner_repo}/security"


def _secret_scanning_url(owner_repo: str) -> str:
    return f"https://github.com/{owner_repo}/security/secret-scanning"


def _workflow_page_url(owner_repo: str, workflow_id) -> str:
    return f"https://github.com/{owner_repo}/actions/workflows/{workflow_id}"


# ---------------------------------------------------------------------------
# Action-unit mappers
# ---------------------------------------------------------------------------

def _severity_breakdown(alerts: list[dict], extract_severity) -> dict[str, int]:
    """Count alerts per canonical triage severity.

    ``extract_severity`` is per-feed (code-scanning reads
    ``rule.security_severity_level``; dependabot reads
    ``security_advisory.severity``).
    """
    counts: dict[str, int] = {s: 0 for s in ("critical", "high", "medium", "low")}
    for alert in alerts:
        sev = triage_severity(extract_severity(alert))
        if sev in counts:
            counts[sev] += 1
        else:
            counts["medium"] += 1
    return counts


def _cs_extract_severity(alert: dict) -> str | None:
    rule = alert.get("rule") or {}
    return rule.get("security_severity_level") or rule.get("severity")


def _db_extract_severity(alert: dict) -> str | None:
    return (alert.get("security_advisory") or {}).get("severity")


def _artifact_extract_severity(finding: dict) -> str | None:
    """Severity extractor for shipwright-security ``findings.json`` entries.

    The artifact's ``findings[].severity`` is a top-level lowercase string
    (``"critical"`` / ``"high"`` / etc.) — flat, unlike cs_alerts' nested
    ``rule.security_severity_level`` and db_alerts' ``security_advisory.severity``.

    Iterate C openai-9: derive truth from the list, never from the
    redundant ``by_severity`` aggregate. The mapper iterates the
    ``findings`` array via ``_severity_breakdown`` and ``_max_severity``,
    both of which call this extractor.
    """
    return finding.get("severity")


def _format_breakdown(counts: dict[str, int]) -> str:
    """Render a severity breakdown as a stable, comma-separated string.

    Always iterates in fixed severity order (critical → low) so the same
    counts produce byte-identical output. Empty severities are omitted to
    keep the line concise; the total is always present in the caller.
    """
    parts = [f"{n} {sev}" for sev, n in counts.items() if n > 0]
    return ", ".join(parts) if parts else "0"


def security_action_unit(
    *,
    code_scanning: list[dict],
    dependabot: list[dict],
    owner_repo: str | None,
) -> dict | None:
    """Collapse code-scanning + dependabot into one action-unit per repo.

    Returns ``None`` when both feeds are empty (nothing to triage) or
    when ``owner_repo`` is ``None`` (can't form a stable dedup key —
    review finding #4).
    """
    if owner_repo is None:
        return None
    cs_count = len(code_scanning)
    db_count = len(dependabot)
    if cs_count == 0 and db_count == 0:
        return None

    cs_breakdown = _severity_breakdown(code_scanning, _cs_extract_severity)
    db_breakdown = _severity_breakdown(dependabot, _db_extract_severity)

    all_severities = [
        triage_severity(_cs_extract_severity(a)) for a in code_scanning
    ] + [
        triage_severity(_db_extract_severity(a)) for a in dependabot
    ]
    severity = _max_severity(all_severities)
    url = _security_url(owner_repo)

    title = (
        f"GitHub security: {cs_count} code-scanning + "
        f"{db_count} Dependabot ({severity})"
    )
    detail = (
        f"Repo {owner_repo} | "
        f"code-scanning: {_format_breakdown(cs_breakdown)} | "
        f"dependabot: {_format_breakdown(db_breakdown)} | "
        f"see {url}"
    )
    payload = (
        f"/shipwright-security\n"
        f"\n"
        f"Context: GitHub reports {cs_count} open code-scanning finding(s) and "
        f"{db_count} open Dependabot alert(s) for {owner_repo}.\n"
        f"Severity breakdown — code-scanning: {_format_breakdown(cs_breakdown)}; "
        f"dependabot: {_format_breakdown(db_breakdown)}.\n"
        f"Live state: {url}\n"
        f"Source: triage item gh-security:{owner_repo}"
    )
    return {
        "severity": severity,
        "kind": _kind_for(severity),
        "title": title[:160],
        "detail": detail,
        "dedup_key": f"{PREFIX_SECURITY}{owner_repo}",
        "launch_payload": payload,
    }


# Length cap for the artifact-source detail line — protects against
# pathological finding-array sizes (review finding openai-11).
_ARTIFACT_DETAIL_MAX_LEN = 1024


def security_action_unit_from_artifact(
    *,
    findings: list[dict],
    owner_repo: str | None,
    workflow_run_url: str | None = None,
    dependabot: list[dict] | None = None,
) -> dict | None:
    """Collapse shipwright-security ``findings.json`` into the SAME
    ``gh-security:{owner}/{repo}`` action-unit emitted by the GHAS-based
    ``security_action_unit``, just sourced from the artifact instead.

    Iterate C — security-artifact-producer. The artifact path fires when
    GHAS Code Scanning is unavailable (``cs_alerts is None``). Output
    shape is identical to the API path: same ``dedup_key``, same
    ``severity`` / ``kind`` semantics, same ``launch_payload`` slash-
    command shape — only the *source* of the data differs.

    Hygiene boundaries enforced (external LLM review):

    - **openai-9** — severity counts derived from iterating ``findings[]``,
      never from the redundant aggregate. Each entry's ``severity`` is
      normalised via ``triage_severity``; unknown values fall back to
      ``medium``.
    - **openai-11** — no raw finding strings (``rule``, ``description``,
      ``affected_file``) are rendered into ``detail`` or
      ``launch_payload``. Only aggregated counts + the stable workflow
      run URL appear.
    - **openai-13 / general** — ``detail`` is capped at
      ``_ARTIFACT_DETAIL_MAX_LEN`` bytes so a pathological scanner
      payload can't bloat the inbox.
    - Stable shape (deterministic ordering via ``_format_breakdown``)
      keeps the persisted ``launch_payload`` byte-identical across
      reorder.

    Returns ``None`` when:
    - ``owner_repo`` is ``None`` (can't form a stable dedup key) — same
      contract as the API path.
    - ``findings`` is empty AND no other security source is available
      (nothing to triage). A 0-finding scan is a *clean* state, handled
      by the orchestrator's auto-resolve gate; this function never emits
      an empty action-unit unless Dependabot has its own findings to
      surface.

    ``dependabot`` may be provided when Dependabot succeeded but GHAS
    Code Scanning didn't — the artifact path is the SAST source but
    Dependabot is orthogonal and free, so its real counts are rendered
    alongside the artifact's in the detail line (external review code
    finding openai-4 — Dependabot is not gated by `cs_alerts`).
    """
    if owner_repo is None:
        return None

    artifact_breakdown = _severity_breakdown(findings, _artifact_extract_severity)
    db_breakdown = (
        _severity_breakdown(dependabot, _db_extract_severity)
        if dependabot
        else None
    )
    # Emit only when at least one source has findings to surface.
    # Empty artifact + empty/missing dependabot → no-op (orchestrator
    # routes to auto-resolve for clean state).
    if not findings and not dependabot:
        return None

    all_severities = [
        triage_severity(_artifact_extract_severity(f)) for f in findings
    ]
    if dependabot:
        all_severities += [
            triage_severity(_db_extract_severity(a)) for a in dependabot
        ]
    severity = _max_severity(all_severities)
    tab_url = _security_url(owner_repo)
    # Workflow run URL takes the operator straight to the CI summary;
    # the security tab URL is the long-term curation surface. Both
    # appear in the payload; only the run URL is repo-stable enough to
    # link directly to current findings on a private-no-GHAS repo.
    run_url = workflow_run_url or tab_url

    artifact_total = len(findings)
    db_total = len(dependabot or [])
    title = (
        f"GitHub security: {artifact_total} shipwright-security"
        + (f" + {db_total} Dependabot" if db_total else "")
        + f" finding(s) ({severity})"
    )
    db_summary = (
        _format_breakdown(db_breakdown) if db_breakdown is not None
        else "(unavailable)"
    )
    detail = (
        f"Repo {owner_repo} | "
        f"code-scanning: (unavailable) | "
        f"dependabot: {db_summary} | "
        f"shipwright-security: {_format_breakdown(artifact_breakdown)} | "
        f"run: {run_url}"
    )
    if len(detail) > _ARTIFACT_DETAIL_MAX_LEN:
        detail = detail[: _ARTIFACT_DETAIL_MAX_LEN - 1] + "…"
    db_payload_summary = (
        f"; dependabot: {_format_breakdown(db_breakdown)}"
        if db_breakdown is not None
        else ""
    )
    payload = (
        f"/shipwright-security\n"
        f"\n"
        f"Context: the shipwright-security CI workflow reports "
        f"{artifact_total} open finding(s) for {owner_repo} "
        f"(GHAS Code Scanning is not configured).\n"
        f"Severity breakdown — shipwright-security: "
        f"{_format_breakdown(artifact_breakdown)}"
        f"{db_payload_summary}.\n"
        f"Workflow run: {run_url}\n"
        f"Re-scan locally: see docs/security-ci-setup.md\n"
        f"Source: triage item gh-security:{owner_repo}"
    )
    return {
        "severity": severity,
        "kind": _kind_for(severity),
        "title": title[:160],
        "detail": detail,
        "dedup_key": f"{PREFIX_SECURITY}{owner_repo}",
        "launch_payload": payload,
    }


def secrets_action_unit(
    *,
    secret_scanning: list[dict],
    owner_repo: str | None,
) -> dict | None:
    """Collapse secret-scanning into one action-unit per repo.

    Whitelist-only ``launchPayload`` — no slash command, no alert content,
    no per-alert URLs (review finding #9: hygiene boundary). Secret
    rotation is manual by design.

    Returns ``None`` when no alerts or when ``owner_repo`` is ``None``.
    """
    if owner_repo is None or not secret_scanning:
        return None
    count = len(secret_scanning)
    url = _secret_scanning_url(owner_repo)
    title = f"GitHub secret-scanning: {count} active credential(s) to rotate"
    # Detail intentionally does NOT carry per-alert content.
    detail = (
        f"Repo {owner_repo} | {count} open secret-scanning alert(s). "
        f"Rotate via the GitHub secret-scanning tab."
    )
    payload = (
        f"# Manual credential rotation\n"
        f"\n"
        f"GitHub secret-scanning has flagged {count} active credential(s) "
        f"in {owner_repo}.\n"
        f"Rotation is manual — do NOT run a Shipwright skill.\n"
        f"\n"
        f"Checklist:\n"
        f"  1. Open the GitHub secret-scanning tab: {url}\n"
        f"  2. For each alert: identify the secret type and rotate it at "
        f"the issuer (cloud provider, OAuth app, package registry, etc.).\n"
        f"  3. Revoke the leaked credential.\n"
        f"  4. Mark the alert resolved on GitHub (revoked / used in tests / "
        f"false positive).\n"
        f"  5. Audit access logs for unauthorized use during the exposure "
        f"window.\n"
        f"\n"
        f"Source: triage item gh-secrets:{owner_repo}"
    )
    return {
        "severity": "critical",
        "kind": _kind_for("critical"),
        "title": title[:160],
        "detail": detail,
        "dedup_key": f"{PREFIX_SECRETS}{owner_repo}",
        "launch_payload": payload,
    }


def _workflow_identity(run: dict):
    """Stable workflow identity — the immutable ``workflow_id`` when present,
    else the display ``name``. Used for the dedup key (no sha component in
    the action-unit model)."""
    return run.get("workflow_id") or run.get("name") or "workflow"


def ci_action_unit(run: dict, *, owner_repo: str | None) -> dict | None:
    """One action-unit per failed default-branch workflow.

    Dedup key is ``gh-ci:{workflow_identity}`` — the head_sha is dropped
    (review finding #7) so the persisted ``launchPayload`` stays meaningful
    across reruns of the same workflow. The payload links to the workflow
    PAGE URL (stable), NOT the per-run URL (would be stale by the next
    failure).

    Returns ``None`` when ``owner_repo`` is unresolvable (the workflow-page
    URL is repo-scoped — review finding #4).
    """
    if owner_repo is None:
        return None
    workflow_id = _workflow_identity(run)
    name = run.get("name") or run.get("display_title") or "workflow"
    branch = run.get("head_branch") or "?"
    conclusion = run.get("conclusion") or "failure"
    head_sha = run.get("head_sha") or ""
    page_url = _workflow_page_url(owner_repo, workflow_id)
    run_url = run.get("html_url") or ""
    title = f"[ci] {name} failing on {branch}"
    detail = (
        f"Workflow '{name}' last concluded '{conclusion}' on "
        f"{branch}@{head_sha[:7]} | latest run: {run_url}"
    )
    payload = (
        f"/shipwright-iterate --type bug\n"
        f"\n"
        f"Context: GitHub Actions workflow '{name}' is failing on the "
        f"default branch ({branch}) in {owner_repo}.\n"
        f"Last conclusion: {conclusion}.\n"
        f"Live workflow history: {page_url}\n"
        f"Source: triage item gh-ci:{workflow_id}"
    )
    return {
        "severity": "high",
        "kind": _kind_for("high"),
        "title": title[:160],
        "detail": detail,
        "dedup_key": f"{PREFIX_CI}{workflow_id}",
        "launch_payload": payload,
    }


def latest_failed_ci_runs(runs: list[dict]) -> list[dict]:
    """Reduce raw workflow runs (newest first) to the latest *concluded* run
    per workflow, keeping only those whose conclusion is a failure.

    In-progress runs (``conclusion is None``) are skipped so a pending run
    never hides a workflow's last real result. Branch scope is set by the
    caller — the producer calls ``fetch_workflow_runs(default_branch())``
    so this helper sees only default-branch runs by construction.
    """
    seen: set = set()
    failed: list[dict] = []
    for run in runs:
        conclusion = run.get("conclusion")
        if conclusion is None:
            continue
        workflow = _workflow_identity(run)
        if workflow in seen:
            continue
        seen.add(workflow)
        if str(conclusion).lower() in _FAILED_CONCLUSIONS:
            failed.append(run)
    return failed


# ---------------------------------------------------------------------------
# Throttle state (.shipwright/github_import_state.json)
# ---------------------------------------------------------------------------

def _state_path(project_root) -> Path:
    return Path(project_root) / ".shipwright" / STATE_FILENAME


def _run_config(project_root) -> dict:
    try:
        raw = (
            Path(project_root) / "shipwright_run_config.json"
        ).read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def throttle_hours(project_root) -> float:
    """Throttle interval in hours. Resolution order: run-config
    ``triage.github_import_throttle_hours`` -> env var -> default. Non-positive
    or unparseable values are ignored in favour of the next source.
    """
    triage_cfg = _run_config(project_root).get("triage")
    if isinstance(triage_cfg, dict):
        value = triage_cfg.get("github_import_throttle_hours")
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value > 0
        ):
            return float(value)
    env_value = os.environ.get(_ENV_THROTTLE)
    if env_value:
        try:
            parsed = float(env_value)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return DEFAULT_THROTTLE_HOURS


def read_last_import(project_root) -> datetime | None:
    """Last-import timestamp from the state file; ``None`` if absent/malformed."""
    try:
        raw = _state_path(project_root).read_text(encoding="utf-8")
        stored = json.loads(raw).get("lastImport")
        parsed = datetime.fromisoformat(str(stored).replace("Z", "+00:00"))
    except (OSError, json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def write_last_import(project_root, when: datetime) -> None:
    """Persist ``when`` as the last-import timestamp (ISO-8601 UTC, Z-suffix)."""
    path = _state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    iso = when.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    path.write_text(json.dumps({"v": 1, "lastImport": iso}), encoding="utf-8")


def is_due(project_root, *, now: datetime | None = None) -> bool:
    """True if an import is due — no prior state, or the throttle interval
    has elapsed since the last import."""
    now = now or datetime.now(timezone.utc)
    last = read_last_import(project_root)
    if last is None:
        return True
    return (now - last) >= timedelta(hours=throttle_hours(project_root))


# ---------------------------------------------------------------------------
# Auto-resolve + legacy migration
# ---------------------------------------------------------------------------

def _resolve_stale(
    project_root,
    resolvable_prefixes: set[str],
    current_keys: set[str],
) -> int:
    """Dismiss this producer's stale OPEN action-unit items.

    An item is stale when its dedup key belongs to one of the three owned
    action-unit prefixes, that prefix's fetch SUCCEEDED this run, and the
    key is absent from ``current_keys``. Scoped per ADR-052 — items from
    other producers and prefixes whose fetch failed are left alone.
    Legacy items are handled separately by ``_migrate_legacy_items``.
    """
    resolved = 0
    for item in read_all_items(project_root):
        if item.get("source") != SOURCE or item.get("status") != "triage":
            continue
        dedup_key = item.get("dedupKey") or ""
        prefix = next(
            (p for p in _OWNED_PREFIXES if dedup_key.startswith(p)), None
        )
        if prefix is None or prefix not in resolvable_prefixes:
            continue
        if dedup_key in current_keys:
            continue
        try:
            mark_status(
                project_root,
                item["id"],
                new_status="dismissed",
                by="githubImporter",
                reason="githubResolved",
            )
            resolved += 1
        except Exception as exc:  # noqa: BLE001 — best-effort
            sys.stderr.write(
                f"[github-triage] resolve failed for {item.get('id')}: "
                f"{type(exc).__name__}: {exc}\n"
            )
    return resolved


def _migrate_legacy_items(
    project_root,
    fetch_succeeded: dict[str, bool],
) -> int:
    """Dismiss legacy per-finding items whose original source fetch succeeded.

    One-shot migration from the per-finding model (iterate-2026-05-19) to
    the action-unit model (iterate-2026-05-20). Per-source-gated — a failed
    fetch for source X leaves source-X legacy items UNTOUCHED, even if
    other sources succeeded (review finding #3).

    Idempotent: items already at status ``dismissed`` / ``promoted`` /
    ``snoozed`` are skipped (review finding #12) — only items whose
    current resolved status is ``triage`` get a fresh ``schemaMigration``
    event.
    """
    migrated = 0
    for item in read_all_items(project_root):
        if item.get("source") != SOURCE or item.get("status") != "triage":
            continue
        dedup_key = item.get("dedupKey") or ""
        for source_name, legacy_prefix in _LEGACY_MIGRATIONS:
            if not dedup_key.startswith(legacy_prefix):
                continue
            if not fetch_succeeded.get(source_name):
                # Per-source-gating — that source's fetch failed; leave
                # the item alone so a transient outage never mass-resolves.
                break
            try:
                mark_status(
                    project_root,
                    item["id"],
                    new_status="dismissed",
                    by="githubImporter",
                    reason="schemaMigration",
                )
                migrated += 1
            except Exception as exc:  # noqa: BLE001
                sys.stderr.write(
                    f"[github-triage] legacy migration failed for "
                    f"{item.get('id')}: {type(exc).__name__}: {exc}\n"
                )
            break  # one prefix per item
    return migrated


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def import_findings(project_root) -> dict:
    """Import all GitHub findings into the triage inbox as action-units.

    Returns ``{"gh_available": bool, "appended": int, "resolved": int,
    "migrated": int, "by_source": {prefix: int | None}}``. ``migrated``
    counts the one-shot legacy items dismissed this run; ``resolved``
    counts current-model items dismissed because their key left the
    finding set (mirror of #39's behavior).

    The ``by_source`` map carries one key per action-unit prefix; the
    value is the emission count this run, or ``None`` when that prefix's
    underlying fetch failed (auto-resolve is gated on success — ADR-052).

    Iterate C (security-artifact-producer) adds the parallel artifact
    ingestion path. When GHAS Code Scanning is unavailable
    (``cs_alerts is None``), the ``shipwright-security`` workflow's
    ``findings.json`` artifact is fetched as a third source and emitted
    as the SAME ``gh-security:{owner}/{repo}`` action-unit. The
    ``by_source`` map then carries an additional ``gh-security:artifact``
    key whose value is the artifact-sourced emission count this run —
    so telemetry / audit can distinguish API vs artifact emission.
    """
    if not github_api.gh_available():
        return {
            "gh_available": False,
            "appended": 0,
            "resolved": 0,
            "migrated": 0,
            "by_source": {},
        }

    owner_repo = github_api.owner_repo(project_root)

    raw_runs = github_api.fetch_workflow_runs(github_api.default_branch())
    ci_runs = None if raw_runs is None else latest_failed_ci_runs(raw_runs)

    cs_alerts = github_api.fetch_code_scanning_alerts()
    db_alerts = github_api.fetch_dependabot_alerts()
    ss_alerts = github_api.fetch_secret_scanning_alerts()

    # Iterate C — security-artifact-producer. The artifact path fires ONLY
    # when ``cs_alerts is None`` (i.e. GHAS Code Scanning is unavailable —
    # private repo without GHAS). Probing gh-run-download when GHAS works
    # would (a) waste network bandwidth and (b) risk double-counting the
    # same semgrep/trivy findings that the workflow's SARIF upload already
    # streamed into Code Scanning. Dependabot's status is irrelevant —
    # Dependabot is free and orthogonal to the SAST source (external LLM
    # review HIGH #1 — gemini-1).
    artifact_run: dict | None = None
    artifact_findings: list[dict] | None = None
    if cs_alerts is None:
        try:
            artifact_run = github_api.latest_security_workflow_run()
            if artifact_run is not None:
                artifact_findings = github_api.download_security_findings(
                    artifact_run.get("id") or 0,
                )
        except Exception as exc:  # noqa: BLE001 — fail-soft, never block
            sys.stderr.write(
                f"[github-triage] artifact fetch failed: "
                f"{type(exc).__name__}: {exc}\n"
            )
            artifact_run = None
            artifact_findings = None

    fetch_succeeded = {
        "code_scanning": cs_alerts is not None,
        "dependabot": db_alerts is not None,
        "secret_scanning": ss_alerts is not None,
        "runs": ci_runs is not None,
        # Distinguish ``download succeeded with 0/n findings`` from
        # ``download failed / never tried``. Auto-resolve depends on
        # this per ADR-052.
        "artifact": artifact_findings is not None,
    }

    # Run the legacy-migration sweep FIRST so it never races against the
    # action-unit append loop and never misclassifies a freshly-appended
    # new-prefix item.
    try:
        migrated = _migrate_legacy_items(project_root, fetch_succeeded)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[github-triage] legacy migration sweep failed: "
            f"{type(exc).__name__}: {exc}\n"
        )
        migrated = 0

    # Build action-units (None when nothing to triage or repo unresolvable).
    # Security requires BOTH GHAS feeds succeeded — emitting on partial fetch
    # would freeze a payload claiming "0 X alerts" when X actually failed to
    # fetch. The auto-resolve gate has the same shape; emit and resolve are
    # symmetric. Code review MED #1 of iterate-2026-05-20-triage-launch-surface.
    both_security_feeds_ok = (
        cs_alerts is not None and db_alerts is not None
    )
    security_unit = (
        security_action_unit(
            code_scanning=cs_alerts,
            dependabot=db_alerts,
            owner_repo=owner_repo,
        )
        if both_security_feeds_ok
        else None
    )

    # Iterate C — security-artifact-producer: parallel-source path. Only
    # consulted when GHAS Code Scanning is unavailable (``cs_alerts is None``).
    # Dependabot is orthogonal — its real counts (when available) are
    # passed through to the artifact mapper so the detail line surfaces
    # them alongside the artifact source. External review code finding
    # openai-4: hard-coding dependabot=(unavailable) would lose signal.
    artifact_unit = (
        security_action_unit_from_artifact(
            findings=artifact_findings,
            owner_repo=owner_repo,
            workflow_run_url=(artifact_run or {}).get("html_url"),
            dependabot=db_alerts,
        )
        if (cs_alerts is None and artifact_findings is not None)
        else None
    )
    secrets_unit = (
        secrets_action_unit(secret_scanning=ss_alerts, owner_repo=owner_repo)
        if ss_alerts is not None
        else None
    )
    ci_units = (
        [ci_action_unit(run, owner_repo=owner_repo) for run in ci_runs]
        if ci_runs is not None
        else []
    )

    # The auto-resolve pass is per-action-unit-prefix. A prefix is
    # "resolvable" when (a) the underlying fetch succeeded AND (b) at
    # least one of the relevant action-unit mappers is willing to emit
    # for this run (otherwise an unresolvable owner_repo would mass-
    # resolve every gh-security: item incorrectly).
    resolvable_prefixes: set[str] = set()
    current_keys: set[str] = set()

    by_source: dict = {}

    def _maybe_append(unit, prefix_key):
        nonlocal current_keys
        if unit is None:
            return None
        current_keys.add(unit["dedup_key"])
        try:
            return append_triage_item_idempotent(
                project_root,
                source=SOURCE,
                severity=unit["severity"],
                kind=unit["kind"],
                title=unit["title"],
                detail=unit["detail"],
                dedup_key=unit["dedup_key"],
                match_commit=False,
                window_seconds=None,
                launch_payload=unit["launch_payload"],
            )
        except Exception as exc:  # noqa: BLE001 — best-effort
            sys.stderr.write(
                f"[github-triage] append failed for {unit['dedup_key']}: "
                f"{type(exc).__name__}: {exc}\n"
            )
            return None

    appended = 0

    # Security — emit + resolve are gated symmetrically on BOTH feeds.
    if both_security_feeds_ok:
        if owner_repo is not None:
            resolvable_prefixes.add(PREFIX_SECURITY)
        sec_id = _maybe_append(security_unit, PREFIX_SECURITY)
        by_source[PREFIX_SECURITY] = 1 if sec_id else 0
        if sec_id:
            appended += 1
    elif cs_alerts is None and fetch_succeeded["artifact"]:
        # Iterate C — artifact path. ``cs_alerts is None`` (no GHAS) AND
        # the shipwright-security workflow yielded a fresh artifact.
        # Dependabot's availability is independent — its real counts
        # are already passed into the artifact mapper above. The
        # auto-resolve gate is opened for PREFIX_SECURITY so a clean
        # scan (0 findings) can dismiss a previously-open item — same
        # githubResolved semantics as the GHAS API path. ``by_source``
        # records this ingestion path distinctly per AC-5.
        if owner_repo is not None:
            resolvable_prefixes.add(PREFIX_SECURITY)
        art_id = _maybe_append(artifact_unit, PREFIX_SECURITY)
        by_source[PREFIX_SECURITY] = None  # API path not active
        by_source["gh-security:artifact"] = 1 if art_id else 0
        if art_id:
            appended += 1
    else:
        by_source[PREFIX_SECURITY] = None

    # Secrets
    if fetch_succeeded["secret_scanning"]:
        if owner_repo is not None:
            resolvable_prefixes.add(PREFIX_SECRETS)
        secrets_id = _maybe_append(secrets_unit, PREFIX_SECRETS)
        by_source[PREFIX_SECRETS] = 1 if secrets_id else 0
        if secrets_id:
            appended += 1
    else:
        by_source[PREFIX_SECRETS] = None

    # CI
    if fetch_succeeded["runs"]:
        if owner_repo is not None:
            resolvable_prefixes.add(PREFIX_CI)
        ci_emitted = 0
        for unit in ci_units:
            new_id = _maybe_append(unit, PREFIX_CI)
            if new_id:
                ci_emitted += 1
                appended += 1
        by_source[PREFIX_CI] = ci_emitted
    else:
        by_source[PREFIX_CI] = None

    try:
        resolved = _resolve_stale(project_root, resolvable_prefixes, current_keys)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[github-triage] resolve pass failed: "
            f"{type(exc).__name__}: {exc}\n"
        )
        resolved = 0

    return {
        "gh_available": True,
        "appended": appended,
        "resolved": resolved,
        "migrated": migrated,
        "by_source": by_source,
    }
