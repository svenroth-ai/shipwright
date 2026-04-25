"""SARIF 2.1.0 writer for normalized shipwright-security findings.

Pure transform: takes a list of normalized findings (the output of
ScannerBackend.scan() — see scanner_backend.py) and returns a SARIF 2.1.0
document. Designed to be called once per scanner source (semgrep, trivy,
gitleaks, ...) so each tool gets its own SARIF file.

Why a translator instead of native scanner SARIF flags:
- Single-pass: scanners run once, SARIF is a pure transform of the same
  normalized data already in memory.
- Consistent: same severity / rule-id semantics across tools, no
  per-tool SARIF dialect quirks.
- Empty-aware: caller can request a valid empty SARIF document by passing
  an empty findings list plus an explicit ``source`` — required because
  ``upload-sarif`` fails on an empty directory.

GitHub Security tab consumes SARIF strictly:
- ``level`` enum is ``error | warning | note | none`` only.
- ``security-severity`` (CVSS 0-10, as a string) drives the severity badge.
- ``partialFingerprints`` lets GitHub dedup the same finding across scans.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

SARIF_SCHEMA_URI = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/"
    "sarif-schema-2.1.0.json"
)
SARIF_VERSION = "2.1.0"

# severity (normalized) → SARIF level enum (strict GitHub validation)
_SEVERITY_TO_LEVEL = {
    "critical": "error",
    "high": "error",
    "medium": "warning",
    "low": "note",
    "info": "note",
}

_DRIVER_INFO_URI = {
    "semgrep": "https://semgrep.dev",
    "trivy": "https://github.com/aquasecurity/trivy",
    "gitleaks": "https://github.com/gitleaks/gitleaks",
    "aikido": "https://www.aikido.dev",
}


def _level_for(severity: Any) -> str:
    if not isinstance(severity, str):
        return "none"
    return _SEVERITY_TO_LEVEL.get(severity.lower(), "none")


def _fingerprint(finding: dict, source: str) -> str:
    """Stable per-finding fingerprint used for cross-scan dedup in GitHub UI."""
    parts = [
        str(finding.get("source") or source or ""),
        str(finding.get("rule") or ""),
        str(finding.get("affected_file") or ""),
        str(finding.get("affected_line") if finding.get("affected_line") is not None else ""),
        str(finding.get("cve_id") or ""),
    ]
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _build_rule(finding: dict, source: str, rule_id: str) -> dict:
    description = finding.get("description") or rule_id
    short = _truncate(description, 120) if description else rule_id
    cwe = finding.get("cwe_classes") or []
    rule = {
        "id": rule_id,
        "name": finding.get("rule") or rule_id,
        "shortDescription": {"text": short},
        "fullDescription": {"text": description},
        "defaultConfiguration": {"level": _level_for(finding.get("severity"))},
        "properties": {
            "tags": [t for t in cwe if isinstance(t, str)],
        },
    }
    score = finding.get("severity_score")
    if isinstance(score, (int, float)):
        rule["properties"]["security-severity"] = f"{float(score):.1f}"
    help_uri = finding.get("help_uri")
    if isinstance(help_uri, str) and help_uri:
        rule["helpUri"] = help_uri
    return rule


def _build_result(finding: dict, source: str, rule_id: str) -> dict:
    description = finding.get("description") or rule_id
    result: dict[str, Any] = {
        "ruleId": rule_id,
        "level": _level_for(finding.get("severity")),
        "message": {"text": description},
        "partialFingerprints": {
            "shipwright/v1": _fingerprint(finding, source),
        },
    }
    affected_file = finding.get("affected_file")
    if isinstance(affected_file, str) and affected_file:
        physical: dict[str, Any] = {
            "artifactLocation": {"uri": affected_file},
        }
        line = finding.get("affected_line")
        if isinstance(line, int) and line > 0:
            physical["region"] = {"startLine": line}
        result["locations"] = [{"physicalLocation": physical}]
    score = finding.get("severity_score")
    if isinstance(score, (int, float)):
        result.setdefault("properties", {})["security-severity"] = f"{float(score):.1f}"
    return result


def to_sarif(findings: Iterable[dict], source: str) -> dict:
    """Translate a list of normalized findings (single source) to SARIF 2.1.0.

    Args:
        findings: Iterable of normalized finding dicts (see scanner_backend.py).
                  All findings should share the same ``source``; if not, the
                  function still groups them under the supplied ``source`` driver
                  but uses each finding's own source for its rule prefix.
        source: Required scanner name (``"semgrep"``, ``"trivy"``, ...). Used as
                the SARIF tool driver name AND as the rule-id prefix for every
                rule. Required even when ``findings`` is empty so the caller can
                emit a valid placeholder SARIF document.

    Returns:
        SARIF 2.1.0 root object (a single ``run``). Empty findings produce a
        valid document with ``runs[0].results = []`` and ``rules = []``.
    """
    if not isinstance(source, str) or not source.strip():
        raise ValueError("sarif_writer.to_sarif requires a non-empty 'source'")
    source = source.strip().lower()

    rules_by_id: dict[str, dict] = {}
    results: list[dict] = []

    for finding in findings:
        if not isinstance(finding, dict):
            continue
        finding_source = (finding.get("source") or source).strip().lower() or source
        rule_name = finding.get("rule") or "unknown"
        rule_id = f"{finding_source}/{rule_name}"

        if rule_id not in rules_by_id:
            rules_by_id[rule_id] = _build_rule(finding, source, rule_id)

        results.append(_build_result(finding, source, rule_id))

    return {
        "$schema": SARIF_SCHEMA_URI,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": source,
                        "informationUri": _DRIVER_INFO_URI.get(
                            source, "https://github.com/svenroth-ai/shipwright"
                        ),
                        "rules": list(rules_by_id.values()),
                    }
                },
                "results": results,
            }
        ],
    }
