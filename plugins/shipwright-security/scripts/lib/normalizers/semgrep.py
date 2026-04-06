"""Normalize Semgrep JSON output to the standard finding schema.

Semgrep JSON structure (--json flag):
{
  "results": [
    {
      "check_id": "python.lang.security.hardcoded-credentials.hardcoded-credentials",
      "path": "scripts/api.py",
      "start": {"line": 42, "col": 1},
      "end": {"line": 42, "col": 50},
      "extra": {
        "message": "Hardcoded credentials detected",
        "severity": "ERROR",   # ERROR | WARNING | INFO
        "metadata": {
          "cwe": ["CWE-798"],
          "confidence": "HIGH",
          "impact": "HIGH",
          "fix": "Move credentials to environment variables"
        }
      }
    }
  ],
  "errors": [...]
}
"""

from __future__ import annotations

from typing import Any

# Semgrep severity → normalized severity
_SEVERITY_MAP = {
    "ERROR": "high",
    "WARNING": "medium",
    "INFO": "low",
}


def normalize(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert Semgrep JSON output to normalized findings."""
    results = raw.get("results", [])
    findings = []

    for i, r in enumerate(results):
        check_id = r.get("check_id", "unknown")
        extra = r.get("extra", {})
        metadata = extra.get("metadata", {})

        semgrep_severity = extra.get("severity", "INFO")
        severity = _SEVERITY_MAP.get(semgrep_severity, "low")

        # Build severity score from impact/confidence metadata
        severity_score = _estimate_score(severity, metadata)

        # CWE can be a list of strings or dicts
        cwe_raw = metadata.get("cwe", [])
        cwe_classes = []
        for c in cwe_raw:
            if isinstance(c, str):
                cwe_classes.append(c)
            elif isinstance(c, dict):
                cwe_classes.append(c.get("id", str(c)))

        finding = {
            "id": f"semgrep-{i+1:04d}",
            "severity": severity,
            "severity_score": severity_score,
            "type": "sast",
            "rule": check_id,
            "cve_id": None,
            "affected_package": None,
            "affected_file": r.get("path"),
            "affected_line": r.get("start", {}).get("line"),
            "description": extra.get("message", ""),
            "remediation_hint": metadata.get("fix"),
            "cwe_classes": cwe_classes,
            "source": "semgrep",
        }
        findings.append(finding)

    return findings


def _estimate_score(severity: str, metadata: dict[str, Any]) -> float:
    """Estimate a 0-10 severity score."""
    base = {"critical": 9.0, "high": 7.0, "medium": 5.0, "low": 2.0, "info": 0.5}
    score = base.get(severity, 3.0)
    # Bump up if metadata says HIGH impact
    if metadata.get("impact", "").upper() == "HIGH":
        score = min(score + 1.0, 10.0)
    return score
