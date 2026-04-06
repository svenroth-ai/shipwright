"""Tests for OSS scanner output normalizers."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure scripts/lib is on path for normalizer imports
PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

from normalizers.semgrep import normalize as normalize_semgrep
from normalizers.trivy import normalize as normalize_trivy
from normalizers.gitleaks import normalize as normalize_gitleaks


# ---------------------------------------------------------------------------
# Semgrep normalizer
# ---------------------------------------------------------------------------

class TestSemgrepNormalizer:

    def test_basic_normalization(self, sample_semgrep_output):
        findings = normalize_semgrep(sample_semgrep_output)
        assert len(findings) == 3

    def test_finding_fields(self, sample_semgrep_output):
        findings = normalize_semgrep(sample_semgrep_output)
        f = findings[0]

        assert f["id"] == "semgrep-0001"
        assert f["severity"] == "high"  # ERROR -> high
        assert f["type"] == "sast"
        assert f["rule"] == "python.lang.security.hardcoded-credentials.hardcoded-credentials"
        assert f["affected_file"] == "scripts/api.py"
        assert f["affected_line"] == 42
        assert f["source"] == "semgrep"
        assert "CWE-798" in f["cwe_classes"]
        assert f["remediation_hint"] == "Move credentials to environment variables"

    def test_severity_mapping(self, sample_semgrep_output):
        findings = normalize_semgrep(sample_semgrep_output)
        assert findings[0]["severity"] == "high"    # ERROR
        assert findings[1]["severity"] == "medium"  # WARNING
        assert findings[2]["severity"] == "high"    # ERROR

    def test_severity_score_bump_for_high_impact(self, sample_semgrep_output):
        findings = normalize_semgrep(sample_semgrep_output)
        # First finding has impact=HIGH, so score should be bumped
        assert findings[0]["severity_score"] == 8.0  # 7.0 base + 1.0 impact

    def test_empty_results(self):
        findings = normalize_semgrep({"results": [], "errors": []})
        assert findings == []

    def test_missing_metadata(self):
        raw = {"results": [{"check_id": "test", "path": "a.py", "start": {"line": 1}, "extra": {"message": "test", "severity": "INFO"}}]}
        findings = normalize_semgrep(raw)
        assert len(findings) == 1
        assert findings[0]["severity"] == "low"
        assert findings[0]["cwe_classes"] == []


# ---------------------------------------------------------------------------
# Trivy normalizer
# ---------------------------------------------------------------------------

class TestTrivyNormalizer:

    def test_basic_normalization(self, sample_trivy_output):
        findings = normalize_trivy(sample_trivy_output)
        assert len(findings) == 3

    def test_finding_fields(self, sample_trivy_output):
        findings = normalize_trivy(sample_trivy_output)
        f = findings[0]

        assert f["id"] == "trivy-0001"
        assert f["severity"] == "high"
        assert f["type"] == "sca"
        assert f["rule"] == "CVE-2024-1234"
        assert f["cve_id"] == "CVE-2024-1234"
        assert f["affected_package"] == "lodash"
        assert f["affected_file"] == "package-lock.json"
        assert f["source"] == "trivy"
        assert "CWE-1321" in f["cwe_classes"]
        assert f["remediation_hint"] == "Update lodash to 4.17.21"

    def test_cvss_score_extraction(self, sample_trivy_output):
        findings = normalize_trivy(sample_trivy_output)
        assert findings[0]["severity_score"] == 7.5
        assert findings[1]["severity_score"] == 9.1

    def test_missing_cvss_uses_default(self, sample_trivy_output):
        findings = normalize_trivy(sample_trivy_output)
        # Third finding has empty CVSS → default score for medium
        assert findings[2]["severity_score"] == 5.0

    def test_severity_mapping(self, sample_trivy_output):
        findings = normalize_trivy(sample_trivy_output)
        assert findings[0]["severity"] == "high"
        assert findings[1]["severity"] == "critical"
        assert findings[2]["severity"] == "medium"

    def test_empty_results(self):
        findings = normalize_trivy({"Results": []})
        assert findings == []

    def test_null_vulnerabilities(self):
        raw = {"Results": [{"Target": "go.sum", "Type": "gomod", "Vulnerabilities": None}]}
        findings = normalize_trivy(raw)
        assert findings == []


# ---------------------------------------------------------------------------
# Gitleaks normalizer
# ---------------------------------------------------------------------------

class TestGitleaksNormalizer:

    def test_basic_normalization(self, sample_gitleaks_output):
        findings = normalize_gitleaks(sample_gitleaks_output)
        assert len(findings) == 2

    def test_finding_fields(self, sample_gitleaks_output):
        findings = normalize_gitleaks(sample_gitleaks_output)
        f = findings[0]

        assert f["id"] == "gitleaks-0001"
        assert f["type"] == "secret_detection"
        assert f["rule"] == "generic-api-key"
        assert f["affected_file"] == "scripts/config.py"
        assert f["affected_line"] == 42
        assert f["source"] == "gitleaks"
        assert "CWE-798" in f["cwe_classes"]

    def test_entropy_severity(self, sample_gitleaks_output):
        findings = normalize_gitleaks(sample_gitleaks_output)
        # First: entropy 4.8 → high (4.0-5.0 range)
        assert findings[0]["severity"] == "high"
        assert findings[0]["severity_score"] == 7.5
        # Second: entropy 3.2 → medium (3.0-4.0 range)
        assert findings[1]["severity"] == "medium"
        assert findings[1]["severity_score"] == 5.0

    def test_empty_list(self):
        findings = normalize_gitleaks([])
        assert findings == []

    def test_all_findings_have_required_keys(self, sample_gitleaks_output):
        findings = normalize_gitleaks(sample_gitleaks_output)
        required = {"id", "severity", "type", "rule", "source", "affected_file"}
        for f in findings:
            assert required.issubset(f.keys()), f"Missing keys: {required - f.keys()}"
