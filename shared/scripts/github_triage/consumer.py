"""Consumer side: triage-inbox dispatch + import orchestration.

This submodule owns the side-effects of one ``import_findings`` run:

- Calling the GitHub-API client (``github_api``) for the five raw sources.
- Calling the action-unit mappers in ``producer.py`` / ``mappers.py``.
- Appending action-units to the triage inbox via
  ``triage.append_triage_item_idempotent``.
- Delegating the auto-resolve + legacy-migration sweeps to ``resolve.py``.

Public surface re-exported from ``github_triage``:

- ``import_findings(project_root) -> dict`` — single orchestration entry.
- ``SOURCE`` — the triage-item source key.
"""

from __future__ import annotations

import sys

import github_api
from triage import append_triage_item_idempotent

from .mappers import ci_action_unit, latest_failed_ci_runs, secrets_action_unit
from .producer import (
    PREFIX_CI,
    PREFIX_SECRETS,
    PREFIX_SECURITY,
    security_action_unit,
    security_action_unit_from_artifact,
)
from .resolve import SOURCE, migrate_legacy_items, resolve_stale


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
        migrated = migrate_legacy_items(project_root, fetch_succeeded)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[github-triage] legacy migration sweep failed: "
            f"{type(exc).__name__}: {exc}\n"
        )
        migrated = 0

    # Build action-units (None when nothing to triage or repo unresolvable).
    # Security requires BOTH GHAS feeds succeeded — emitting on partial fetch
    # would freeze a payload claiming "0 X alerts" when X actually failed to
    # fetch. Code review MED #1 of iterate-2026-05-20-triage-launch-surface.
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

    # Iterate C — security-artifact-producer: parallel-source path.
    # Consulted only when GHAS Code Scanning is unavailable (cs_alerts is None).
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

    resolvable_prefixes: set[str] = set()
    current_keys: set[str] = set()
    by_source: dict = {}

    def _maybe_append(unit):
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
        sec_id = _maybe_append(security_unit)
        by_source[PREFIX_SECURITY] = 1 if sec_id else 0
        if sec_id:
            appended += 1
    elif cs_alerts is None and fetch_succeeded["artifact"]:
        # Artifact path. The auto-resolve gate is opened for PREFIX_SECURITY
        # so a clean scan (0 findings) can dismiss a previously-open item.
        if owner_repo is not None:
            resolvable_prefixes.add(PREFIX_SECURITY)
        art_id = _maybe_append(artifact_unit)
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
        secrets_id = _maybe_append(secrets_unit)
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
            new_id = _maybe_append(unit)
            if new_id:
                ci_emitted += 1
                appended += 1
        by_source[PREFIX_CI] = ci_emitted
    else:
        by_source[PREFIX_CI] = None

    try:
        resolved = resolve_stale(project_root, resolvable_prefixes, current_keys)
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
