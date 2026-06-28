#!/usr/bin/env python3
"""Download + normalize the ``security-scan-results`` CI artifact.

Split out of :mod:`github_api` (anti-ratchet — that module was at its
grandfathered ceiling) so the artifact-ingestion subsystem lives on its own.
:mod:`github_api` re-exports :func:`download_security_findings` /
:func:`download_prompt_risks` for back-compat, so existing
``github_api.download_security_findings`` callers are unchanged.

Two sources, in priority order:

1. ``findings.json`` — scan.py's normalized output (the monorepo's own
   ``security.yml``). Authoritative when present, even as an empty list.
2. ``sarif/*.sarif`` — every repo onboarded via ``/shipwright-adopt`` runs the
   SARIF-only scanner template, which uploads SARIF but no ``findings.json``.
   Parsing it as a fallback lets AR-10 light the Control-Grade Security
   dimension for adopted repos too, not just the monorepo (iterate
   2026-06-28-ar10-sarif-ingestion).

Every fetch is best-effort and returns ``None`` on ANY failure, distinct from a
successful empty (``[]``) — the ADR-052 None-vs-``[]`` invariant the
auto-resolve pass depends on.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# Name of the artifact both the monorepo and the adopt-template security.yml
# upload (``actions/upload-artifact`` step).
_SECURITY_ARTIFACT_NAME = "security-scan-results"

# Artifact download can pull a few-MB zip on slow networks. Bounded so a hung
# `gh` never stalls a session.
_DOWNLOAD_TIMEOUT_SECONDS = 60

# CVSS severity bands (GitHub's 0.0–10.0 ``security-severity`` mapping) → the
# {critical|high|medium|low} buckets ``ci_security.summarize`` counts.
_SARIF_CRITICAL = 9.0
_SARIF_HIGH = 7.0
_SARIF_MEDIUM = 4.0


def download_security_findings(run_id: int) -> list[dict] | None:
    """SAST/SCA findings from the ``security-scan-results`` artifact.

    Primary source is scan.py's normalized ``findings.json``. When that file is
    absent — every ``/shipwright-adopt`` repo runs the SARIF-only template, which
    uploads ``sarif/*.sarif`` but no ``findings.json`` — the SARIF in the *same*
    artifact is parsed as a fallback, so AR-10 lights the Security dimension for
    adopted repos too.
    """
    def _extract(root: Path) -> list[dict] | None:
        json_findings = _findings_from_json(root, "findings.json")
        # A present ``findings.json`` (even an empty list) is authoritative;
        # only fall back to SARIF when scan.py's file is genuinely absent.
        if json_findings is not None:
            return json_findings
        return _findings_from_sarif(root)

    return _with_downloaded_artifact(run_id, _extract)


def download_prompt_risks(run_id: int) -> list[dict] | None:
    """Prompt-injection findings from the artifact's ``prompt_risks.json`` (same
    download contract). No SARIF fallback: prompt-injection risk is not a SARIF
    concept."""
    return _with_downloaded_artifact(
        run_id, lambda root: _findings_from_json(root, "prompt_risks.json"))


def _with_downloaded_artifact(run_id, extract):
    """Download the ``security-scan-results`` artifact into a tempdir, pass the
    extracted root to ``extract``, and always clean up. ``None`` on any fetch
    failure (gh missing, non-zero exit, OS error)."""
    tmpdir = tempfile.mkdtemp(prefix="shipwright-artifact-")
    try:
        cmd: list[str] = [
            "gh", "run", "download", str(run_id),
            "--name", _SECURITY_ARTIFACT_NAME,
            "--dir", tmpdir,
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=_DOWNLOAD_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        return extract(Path(tmpdir))
    finally:
        # Best-effort cleanup — never raise if the tempdir already vanished.
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except OSError:
            pass


def _findings_from_json(root: Path, filename: str) -> list[dict] | None:
    """Return the ``findings`` array from ``filename`` under ``root`` (robust
    rglob discovery), or ``None`` when the file is absent / unparseable / not the
    expected ``{findings: [...]}`` shape. Non-dict entries are dropped so a
    caller's mapper never crashes on a malformed individual entry."""
    matches = list(root.rglob(filename))
    if not matches:
        return None
    try:
        payload = json.loads(matches[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    findings = payload.get("findings")
    if not isinstance(findings, list):
        return None
    return [f for f in findings if isinstance(f, dict)]


def _sarif_severity_bucket(value: Any, is_gitleaks: bool) -> str:
    """Map a SARIF ``security-severity`` number (or a Gitleaks finding) to a
    severity bucket. A Gitleaks finding is always ``critical`` — a committed
    credential is merge-blocking in the CI gate regardless of score. A
    missing/non-numeric score → ``low``: a scanner that emits no severity (e.g.
    Semgrep ``--config auto``) must not inflate the open-high/critical count the
    grade reads."""
    if is_gitleaks:
        return "critical"
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "low"
    if score >= _SARIF_CRITICAL:
        return "critical"
    if score >= _SARIF_HIGH:
        return "high"
    if score >= _SARIF_MEDIUM:
        return "medium"
    return "low"


def _findings_from_sarif(root: Path) -> list[dict] | None:
    """Parse every ``*.sarif`` under ``root`` into severity-only findings (the
    minimal shape ``ci_security.summarize`` needs). ``None`` when no SARIF file
    exists at all, so the caller distinguishes "no scan output" from a clean
    empty scan. SARIF carries ``security-severity`` on the RULE, so each result
    is resolved to its rule by ``ruleId`` (``ruleIndex`` as a fallback) — reading
    it off the result directly is the bug the CI critical-gate documents."""
    sarifs = list(root.rglob("*.sarif"))
    if not sarifs:
        return None
    findings: list[dict] = []
    for path in sarifs:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue  # a single broken SARIF must not void the whole ingest
        if not isinstance(doc, dict):
            continue
        for run in doc.get("runs") or []:
            if not isinstance(run, dict):
                continue
            driver = (run.get("tool") or {}).get("driver") or {}
            is_gitleaks = "gitleaks" in str(driver.get("name", "")).lower()
            rules = driver.get("rules") or []
            by_id: dict[Any, Any] = {}
            for rule in rules:
                if isinstance(rule, dict) and rule.get("id") is not None:
                    by_id[rule["id"]] = (rule.get("properties") or {}).get(
                        "security-severity")
            for res in run.get("results") or []:
                if not isinstance(res, dict):
                    continue
                score = (res.get("properties") or {}).get("security-severity")
                if score is None:
                    score = by_id.get(res.get("ruleId"))
                idx = res.get("ruleIndex")
                if (score is None and isinstance(idx, int)
                        and 0 <= idx < len(rules)):
                    rule = rules[idx]
                    if isinstance(rule, dict):
                        score = (rule.get("properties") or {}).get(
                            "security-severity")
                findings.append(
                    {"severity": _sarif_severity_bucket(score, is_gitleaks)})
    return findings
