"""Normalize Trivy JSON output to the standard finding schema.

Trivy JSON structure (--format json --scanners vuln):
{
  "Results": [
    {
      "Target": "package-lock.json",
      "Type": "npm",
      "Vulnerabilities": [
        {
          "VulnerabilityID": "CVE-2024-1234",
          "PkgName": "lodash",
          "InstalledVersion": "4.17.20",
          "FixedVersion": "4.17.21",
          "Severity": "HIGH",          # CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN
          "Title": "Prototype Pollution in lodash",
          "Description": "...",
          "PrimaryURL": "https://avd.aquasec.com/nvd/cve-2024-1234",
          "CVSS": {
            "nvd": {"V3Score": 7.5}
          },
          "CweIDs": ["CWE-1321"]
        }
      ]
    }
  ]
}
"""

from __future__ import annotations

from typing import Any

_SEVERITY_MAP = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
    "UNKNOWN": "info",
}


def normalize(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert Trivy JSON output to normalized findings."""
    findings = []
    counter = 0

    for result in raw.get("Results", []):
        target_file = result.get("Target", "")
        vulns = result.get("Vulnerabilities") or []

        for vuln in vulns:
            counter += 1
            trivy_severity = vuln.get("Severity", "UNKNOWN")
            severity = _SEVERITY_MAP.get(trivy_severity, "info")

            # Extract CVSS score
            cvss = vuln.get("CVSS", {})
            severity_score = 0.0
            for source_scores in cvss.values():
                if isinstance(source_scores, dict):
                    score = source_scores.get("V3Score", 0)
                    if score > severity_score:
                        severity_score = float(score)
            if severity_score == 0.0:
                severity_score = _default_score(severity)

            # Build remediation hint from fixed version
            fixed = vuln.get("FixedVersion", "")
            pkg = vuln.get("PkgName", "")
            hint = f"Update {pkg} to {fixed}" if fixed else None

            finding = {
                "id": f"trivy-{counter:04d}",
                "severity": severity,
                "severity_score": severity_score,
                "type": "sca",
                "rule": vuln.get("VulnerabilityID", "unknown"),
                "cve_id": vuln.get("VulnerabilityID"),
                "affected_package": pkg or None,
                "affected_file": target_file or None,
                "affected_line": None,
                "description": vuln.get("Title", vuln.get("Description", "")),
                "remediation_hint": hint,
                "cwe_classes": vuln.get("CweIDs", []),
                "source": "trivy",
            }
            findings.append(finding)

    return findings


def _default_score(severity: str) -> float:
    return {"critical": 9.0, "high": 7.0, "medium": 5.0, "low": 2.0, "info": 0.5}.get(severity, 3.0)
