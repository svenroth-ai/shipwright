"""Producer side: code-scanning / Dependabot / artifact -> security action-unit.

This submodule transforms raw GitHub security feeds (code-scanning alerts,
Dependabot alerts, and the shipwright-security findings.json artifact)
into the ``gh-security:{owner}/{repo}`` action-unit. Pure functions —
no I/O, no state, no triage-inbox dispatch (that lives in ``consumer.py``).

Secrets + CI mappers live in ``mappers.py`` (sibling submodule).
Severity helpers + per-feed extractors live in ``severity.py``.

Key prefixes this producer owns (shared with mappers.py):

- ``gh-security:{owner}/{repo}`` — code-scanning + Dependabot collapse
  (one unit per repo; ``launch_payload`` starts with ``/shipwright-security``).
- ``gh-secrets:{owner}/{repo}`` — secret-scanning collapse (mappers.py).
- ``gh-ci:{workflow_id}`` — one unit per failing workflow (mappers.py).

Public surface re-exported from ``github_triage``:

- ``security_action_unit``, ``security_action_unit_from_artifact``
"""

from __future__ import annotations

from .severity import (
    artifact_extract_severity,
    cs_extract_severity,
    db_extract_severity,
    format_breakdown,
    kind_for,
    max_severity,
    security_url,
    severity_breakdown,
    triage_severity,
)

# Action-unit dedup-key prefixes this producer owns. The auto-resolve pass
# (consumer.py) is scoped strictly to these (ADR-052).
PREFIX_SECURITY = "gh-security:"
PREFIX_SECRETS = "gh-secrets:"
PREFIX_CI = "gh-ci:"
PREFIX_PROMPT = "gh-prompt:"
_OWNED_PREFIXES = (PREFIX_SECURITY, PREFIX_SECRETS, PREFIX_CI, PREFIX_PROMPT)

# Length cap for the artifact-source detail line — protects against
# pathological finding-array sizes (review finding openai-11).
_ARTIFACT_DETAIL_MAX_LEN = 1024


def prompt_injection_action_unit_from_artifact(
    *,
    findings: list[dict],
    owner_repo: str | None,
    workflow_run_url: str | None = None,
) -> dict | None:
    """Collapse shipwright-security prompt-injection findings (``prompt_risks.json``
    artifact) into a ``gh-prompt:{owner}/{repo}`` action-unit — a SEPARATE source
    from the SAST/SCA ``gh-security`` unit (different finding class, independently
    dismissable). Same ADR-052 + hygiene contract as
    ``security_action_unit_from_artifact``: severity derived by iterating
    ``findings`` (never the aggregate); no raw finding strings in ``detail`` /
    ``launch_payload``; ``detail`` capped. Returns ``None`` when ``owner_repo`` is
    ``None`` OR ``findings`` is empty — an empty (clean) scan is handled by the
    orchestrator's auto-resolve gate.
    """
    if owner_repo is None or not findings:
        return None
    breakdown = severity_breakdown(findings, artifact_extract_severity)
    severity = max_severity(
        [triage_severity(artifact_extract_severity(f)) for f in findings]
    )
    total = len(findings)
    run_url = workflow_run_url or security_url(owner_repo)
    title = f"GitHub prompt-injection: {total} finding(s) ({severity})"
    detail = (
        f"Repo {owner_repo} | "
        f"prompt-injection (prompt_risks.json): {format_breakdown(breakdown)} | "
        f"run: {run_url}"
    )
    if len(detail) > _ARTIFACT_DETAIL_MAX_LEN:
        detail = detail[: _ARTIFACT_DETAIL_MAX_LEN - 1] + "…"
    payload = (
        f"/shipwright-security\n"
        f"\n"
        f"Context: the shipwright-security prompt-injection scan reports "
        f"{total} open finding(s) for {owner_repo}.\n"
        f"Severity breakdown — prompt-injection: {format_breakdown(breakdown)}.\n"
        f"Workflow run: {run_url}\n"
        f"Re-scan locally: see docs/security-ci-setup.md\n"
        f"Source: triage item {PREFIX_PROMPT}{owner_repo}"
    )
    return {
        "severity": severity,
        "kind": kind_for(severity),
        "title": title[:160],
        "detail": detail,
        "dedup_key": f"{PREFIX_PROMPT}{owner_repo}",
        "launch_payload": payload,
    }


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

    cs_breakdown = severity_breakdown(code_scanning, cs_extract_severity)
    db_breakdown = severity_breakdown(dependabot, db_extract_severity)

    all_severities = [
        triage_severity(cs_extract_severity(a)) for a in code_scanning
    ] + [
        triage_severity(db_extract_severity(a)) for a in dependabot
    ]
    severity = max_severity(all_severities)
    url = security_url(owner_repo)

    title = (
        f"GitHub security: {cs_count} code-scanning + "
        f"{db_count} Dependabot ({severity})"
    )
    detail = (
        f"Repo {owner_repo} | "
        f"code-scanning: {format_breakdown(cs_breakdown)} | "
        f"dependabot: {format_breakdown(db_breakdown)} | "
        f"see {url}"
    )
    payload = (
        f"/shipwright-security\n"
        f"\n"
        f"Context: GitHub reports {cs_count} open code-scanning finding(s) and "
        f"{db_count} open Dependabot alert(s) for {owner_repo}.\n"
        f"Severity breakdown — code-scanning: {format_breakdown(cs_breakdown)}; "
        f"dependabot: {format_breakdown(db_breakdown)}.\n"
        f"Live state: {url}\n"
        f"Source: triage item gh-security:{owner_repo}"
    )
    return {
        "severity": severity,
        "kind": kind_for(severity),
        "title": title[:160],
        "detail": detail,
        "dedup_key": f"{PREFIX_SECURITY}{owner_repo}",
        "launch_payload": payload,
    }


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
      never from the redundant aggregate.
    - **openai-11** — no raw finding strings (``rule``, ``description``,
      ``affected_file``) are rendered into ``detail`` or ``launch_payload``.
      Only aggregated counts + the stable workflow run URL appear.
    - **openai-13 / general** — ``detail`` is capped at
      ``_ARTIFACT_DETAIL_MAX_LEN`` bytes so a pathological scanner
      payload can't bloat the inbox.

    Returns ``None`` when ``owner_repo`` is ``None`` OR when ``findings``
    is empty AND no other security source is available. A 0-finding scan
    is a *clean* state handled by the orchestrator's auto-resolve gate.

    ``dependabot`` may be provided when Dependabot succeeded but GHAS
    Code Scanning didn't — its real counts are rendered alongside the
    artifact's in the detail line (external review code finding openai-4).
    """
    if owner_repo is None:
        return None

    artifact_breakdown = severity_breakdown(findings, artifact_extract_severity)
    db_breakdown = (
        severity_breakdown(dependabot, db_extract_severity)
        if dependabot
        else None
    )
    if not findings and not dependabot:
        return None

    all_severities = [
        triage_severity(artifact_extract_severity(f)) for f in findings
    ]
    if dependabot:
        all_severities += [
            triage_severity(db_extract_severity(a)) for a in dependabot
        ]
    severity = max_severity(all_severities)
    tab_url = security_url(owner_repo)
    # Workflow run URL takes the operator straight to the CI summary;
    # the security tab URL is the long-term curation surface.
    run_url = workflow_run_url or tab_url

    artifact_total = len(findings)
    db_total = len(dependabot or [])
    title = (
        f"GitHub security: {artifact_total} shipwright-security"
        + (f" + {db_total} Dependabot" if db_total else "")
        + f" finding(s) ({severity})"
    )
    db_summary = (
        format_breakdown(db_breakdown) if db_breakdown is not None
        else "(unavailable)"
    )
    detail = (
        f"Repo {owner_repo} | "
        f"code-scanning: (unavailable) | "
        f"dependabot: {db_summary} | "
        f"shipwright-security: {format_breakdown(artifact_breakdown)} | "
        f"run: {run_url}"
    )
    if len(detail) > _ARTIFACT_DETAIL_MAX_LEN:
        detail = detail[: _ARTIFACT_DETAIL_MAX_LEN - 1] + "…"
    db_payload_summary = (
        f"; dependabot: {format_breakdown(db_breakdown)}"
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
        f"{format_breakdown(artifact_breakdown)}"
        f"{db_payload_summary}.\n"
        f"Workflow run: {run_url}\n"
        f"Re-scan locally: see docs/security-ci-setup.md\n"
        f"Source: triage item gh-security:{owner_repo}"
    )
    return {
        "severity": severity,
        "kind": kind_for(severity),
        "title": title[:160],
        "detail": detail,
        "dedup_key": f"{PREFIX_SECURITY}{owner_repo}",
        "launch_payload": payload,
    }
