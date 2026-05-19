#!/usr/bin/env python3
"""GitHub findings -> triage inbox importer.

Maps GitHub-reported findings into ``.shipwright/triage.jsonl`` via the
idempotent triage producer API:

  - code-scanning alerts   -> github:code-scanning:<number>
  - Dependabot alerts      -> github:dependabot:<number>
  - secret-scanning alerts -> github:secret-scanning:<number>
  - failed CI workflow runs -> github-ci:<workflow>:<head_sha>

Dedup keys are stable, namespaced, and indefinite (``match_commit=False``,
``window_seconds=None`` — same shape as the drift/compliance producers), so
a finding stays exactly one inbox item until it clears.

Auto-resolve mirrors ADR-052: a stale open item whose key left the current
finding set is dismissed with ``reason="githubResolved"`` — scoped strictly
to the four owned key prefixes, and ONLY for sources whose fetch actually
succeeded (a failed fetch must never mass-resolve).

See sibling ``github_api`` for the `gh` client and the throttled
SessionStart entry point ``hooks/import_github_findings.py``.
Part of iterate-2026-05-19-github-triage-importer.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import github_api
from triage import append_triage_item_idempotent, mark_status, read_all_items

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
# `cancelled` is excluded — an operator cancelled it; it is not a defect.
_FAILED_CONCLUSIONS = frozenset({"failure", "startup_failure", "timed_out"})

# The dedup-key prefixes this producer owns — the auto-resolve pass is
# scoped strictly to these (ADR-052: never resolve by `source` alone).
_OWNED_PREFIXES = (
    "github:code-scanning:",
    "github:dependabot:",
    "github:secret-scanning:",
    "github-ci:",
)


# ---------------------------------------------------------------------------
# Pure mapping helpers
# ---------------------------------------------------------------------------

def triage_severity(gh_value: str | None) -> str:
    """Map a GitHub severity token to a canonical triage severity.

    Unknown / missing values fall back to ``medium`` — a finding is never
    dropped for an unrecognised severity.
    """
    return _GH_SEVERITY_TO_TRIAGE.get((gh_value or "").lower(), "medium")


def _kind_for(severity: str) -> str:
    """critical/high findings are bugs; lower severities are improvements
    (mirrors the security producer's kind rule)."""
    return "bug" if severity in ("critical", "high") else "improvement"


def code_scanning_item(alert: dict) -> dict | None:
    """Map a code-scanning alert to triage-item kwargs (None if unusable)."""
    number = alert.get("number")
    if number is None:
        return None
    rule = alert.get("rule") or {}
    severity = triage_severity(
        rule.get("security_severity_level") or rule.get("severity")
    )
    rule_id = rule.get("id") or rule.get("name") or "code-scanning"
    desc = rule.get("description") or rule.get("name") or rule_id
    location = (alert.get("most_recent_instance") or {}).get("location") or {}
    path = location.get("path") or "?"
    line = location.get("start_line") or "?"
    url = alert.get("html_url") or ""
    return {
        "severity": severity,
        "kind": _kind_for(severity),
        "title": f"[code-scanning] {rule_id}: {desc}"[:160],
        "detail": f"{path}:{line} | {desc} | {url}",
        "dedup_key": f"github:code-scanning:{number}",
    }


def dependabot_item(alert: dict) -> dict | None:
    """Map a Dependabot alert to triage-item kwargs (None if unusable)."""
    number = alert.get("number")
    if number is None:
        return None
    advisory = alert.get("security_advisory") or {}
    severity = triage_severity(advisory.get("severity"))
    summary = advisory.get("summary") or "dependency vulnerability"
    package = (
        ((alert.get("dependency") or {}).get("package") or {}).get("name") or "?"
    )
    url = alert.get("html_url") or ""
    return {
        "severity": severity,
        "kind": _kind_for(severity),
        "title": f"[dependabot] {package}: {summary}"[:160],
        "detail": f"{summary} | package: {package} | {url}",
        "dedup_key": f"github:dependabot:{number}",
    }


def secret_scanning_item(alert: dict) -> dict | None:
    """Map a secret-scanning alert to triage-item kwargs (None if unusable).

    A leaked credential is always ``critical``. The raw ``secret`` value on
    the API object is deliberately NEVER read — only the type display name
    and the alert URL are persisted (AC8 / secret hygiene).
    """
    number = alert.get("number")
    if number is None:
        return None
    display = (
        alert.get("secret_type_display_name")
        or alert.get("secret_type")
        or "undisclosed credential"
    )
    url = alert.get("html_url") or ""
    return {
        "severity": "critical",
        "kind": _kind_for("critical"),
        "title": f"[secret-scanning] {display}"[:160],
        "detail": f"Credential type: {display} | location: {url}",
        "dedup_key": f"github:secret-scanning:{number}",
    }


def _workflow_identity(run: dict):
    """Stable workflow identity — the immutable ``workflow_id`` when present,
    else the display ``name``. Used for BOTH run grouping and the dedup key
    so the two can never disagree about which workflow a run belongs to."""
    return run.get("workflow_id") or run.get("name") or "workflow"


def ci_item(run: dict) -> dict | None:
    """Map a failed workflow run to triage-item kwargs (None if unusable)."""
    head_sha = run.get("head_sha") or ""
    if not head_sha:
        return None
    name = run.get("name") or run.get("display_title") or "workflow"
    branch = run.get("head_branch") or "?"
    conclusion = run.get("conclusion") or "failure"
    url = run.get("html_url") or ""
    return {
        "severity": "high",
        "kind": _kind_for("high"),
        "title": f"[ci] {name} failed on {branch}"[:160],
        "detail": (
            f"Workflow '{name}' concluded '{conclusion}' on "
            f"{branch}@{head_sha[:7]} | {url}"
        ),
        "dedup_key": f"github-ci:{_workflow_identity(run)}:{head_sha}",
    }


def latest_failed_ci_runs(runs: list[dict]) -> list[dict]:
    """Reduce raw workflow runs (newest first) to the latest *concluded* run
    per workflow, keeping only those whose conclusion is a failure.

    In-progress runs (``conclusion is None``) are skipped so a pending run
    never hides a workflow's last real result.
    """
    seen: set = set()
    failed: list[dict] = []
    for run in runs:
        conclusion = run.get("conclusion")
        if conclusion is None:
            continue  # still running / queued — not yet concluded
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
    """Last-import timestamp from the state file; ``None`` if absent/malformed.

    The result is always timezone-aware (UTC): a naive timestamp from a
    hand-edited state file is normalised, so callers can compare it against
    ``datetime.now(timezone.utc)`` without a naive/aware ``TypeError``.
    """
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
    has elapsed since the last import. A malformed state file reads as
    ``None`` (conservative: due)."""
    now = now or datetime.now(timezone.utc)
    last = read_last_import(project_root)
    if last is None:
        return True
    return (now - last) >= timedelta(hours=throttle_hours(project_root))


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _resolve_stale(
    project_root, resolvable_prefixes: set[str], current_keys: set[str]
) -> int:
    """Dismiss this producer's stale open items.

    An item is stale when its dedup key belongs to one of the four owned
    prefixes, that prefix's fetch SUCCEEDED this run (``resolvable_prefixes``),
    and the key is absent from ``current_keys``. Scoped per ADR-052 — items
    from other producers, and prefixes whose fetch failed, are left alone.
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


def import_findings(project_root) -> dict:
    """Import all GitHub findings into the triage inbox.

    Returns ``{"gh_available": bool, "appended": int, "resolved": int,
    "by_source": {prefix: int | None}}``. A ``None`` per-source count means
    that fetch failed — its items are deliberately left untouched by the
    resolve pass.
    """
    if not github_api.gh_available():
        return {
            "gh_available": False,
            "appended": 0,
            "resolved": 0,
            "by_source": {},
        }

    raw_runs = github_api.fetch_workflow_runs(github_api.default_branch())
    ci_runs = None if raw_runs is None else latest_failed_ci_runs(raw_runs)

    # (owned prefix, raw fetch result | None, mapper)
    plan = [
        (
            "github:code-scanning:",
            github_api.fetch_code_scanning_alerts(),
            code_scanning_item,
        ),
        ("github:dependabot:", github_api.fetch_dependabot_alerts(), dependabot_item),
        (
            "github:secret-scanning:",
            github_api.fetch_secret_scanning_alerts(),
            secret_scanning_item,
        ),
        ("github-ci:", ci_runs, ci_item),
    ]

    appended = 0
    current_keys: set[str] = set()
    resolvable_prefixes: set[str] = set()
    by_source: dict = {}

    for prefix, raw, mapper in plan:
        if raw is None:
            by_source[prefix] = None  # fetch failed — do not resolve this prefix
            continue
        resolvable_prefixes.add(prefix)
        count = 0
        for entry in raw:
            item = mapper(entry)
            if item is None:
                continue
            current_keys.add(item["dedup_key"])
            try:
                new_id = append_triage_item_idempotent(
                    project_root,
                    source=SOURCE,
                    severity=item["severity"],
                    kind=item["kind"],
                    title=item["title"],
                    detail=item["detail"],
                    dedup_key=item["dedup_key"],
                    match_commit=False,
                    window_seconds=None,
                )
                if new_id is not None:
                    appended += 1
                    count += 1
            except Exception as exc:  # noqa: BLE001 — best-effort per item
                sys.stderr.write(
                    f"[github-triage] append failed for "
                    f"{item['dedup_key']}: {type(exc).__name__}: {exc}\n"
                )
        by_source[prefix] = count

    try:
        resolved = _resolve_stale(project_root, resolvable_prefixes, current_keys)
    except Exception as exc:  # noqa: BLE001 — best-effort; never lose append work
        sys.stderr.write(
            f"[github-triage] resolve pass failed: "
            f"{type(exc).__name__}: {exc}\n"
        )
        resolved = 0
    return {
        "gh_available": True,
        "appended": appended,
        "resolved": resolved,
        "by_source": by_source,
    }
