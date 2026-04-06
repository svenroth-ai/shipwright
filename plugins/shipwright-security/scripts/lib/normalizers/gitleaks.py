"""Normalize Gitleaks JSON output to the standard finding schema.

Gitleaks JSON structure (--report-format json):
[
  {
    "Description": "Generic API Key",
    "StartLine": 42,
    "EndLine": 42,
    "StartColumn": 10,
    "EndColumn": 55,
    "Match": "api_key = 'sk-...'",
    "Secret": "sk-...",
    "File": "scripts/config.py",
    "Commit": "abc123...",
    "Entropy": 4.5,
    "Author": "dev@example.com",
    "Date": "2024-01-15",
    "RuleID": "generic-api-key",
    "Fingerprint": "scripts/config.py:generic-api-key:42"
  }
]
"""

from __future__ import annotations

from typing import Any


def normalize(raw: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    """Convert Gitleaks JSON output to normalized findings."""
    # Gitleaks outputs a JSON array at the top level
    if isinstance(raw, dict):
        items = raw.get("results", raw.get("data", []))
    elif isinstance(raw, list):
        items = raw
    else:
        return []

    findings = []
    for i, item in enumerate(items):
        rule_id = item.get("RuleID", "unknown")
        entropy = item.get("Entropy", 0)

        # Higher entropy → more likely a real secret → higher severity
        if entropy >= 5.0:
            severity = "critical"
            severity_score = 9.0
        elif entropy >= 4.0:
            severity = "high"
            severity_score = 7.5
        elif entropy >= 3.0:
            severity = "medium"
            severity_score = 5.0
        else:
            severity = "high"  # Default: secrets are always at least high
            severity_score = 7.0

        finding = {
            "id": f"gitleaks-{i+1:04d}",
            "severity": severity,
            "severity_score": severity_score,
            "type": "secret_detection",
            "rule": rule_id,
            "cve_id": None,
            "affected_package": None,
            "affected_file": item.get("File"),
            "affected_line": item.get("StartLine"),
            "description": item.get("Description", f"Secret detected: {rule_id}"),
            "remediation_hint": "Remove the secret from source code and rotate the credential.",
            "cwe_classes": ["CWE-798"],  # Use of Hard-coded Credentials
            "source": "gitleaks",
        }
        findings.append(finding)

    return findings
