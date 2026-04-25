"""Tests for plugins/shipwright-security/scripts/lib/sarif_writer.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

import sarif_writer  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _semgrep_finding(**overrides):
    base = {
        "id": "semgrep-0001",
        "severity": "high",
        "severity_score": 7.5,
        "type": "sast",
        "rule": "python.lang.security.hardcoded-credentials",
        "cve_id": None,
        "affected_package": None,
        "affected_file": "scripts/api.py",
        "affected_line": 42,
        "description": "Hardcoded credentials detected",
        "remediation_hint": "Move to env var",
        "cwe_classes": ["CWE-798"],
        "source": "semgrep",
    }
    base.update(overrides)
    return base


def _trivy_finding(**overrides):
    base = {
        "id": "trivy-0001",
        "severity": "critical",
        "severity_score": 9.8,
        "type": "sca",
        "rule": "CVE-2024-12345",
        "cve_id": "CVE-2024-12345",
        "affected_package": "django",
        "affected_file": "requirements.txt",
        "affected_line": None,
        "description": "Critical vulnerability in django",
        "remediation_hint": "Upgrade to django>=4.2.10",
        "cwe_classes": [],
        "source": "trivy",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Schema-level checks
# ---------------------------------------------------------------------------

class TestSarifShape:

    def test_empty_findings_produces_valid_sarif(self):
        doc = sarif_writer.to_sarif([], source="semgrep")
        assert doc["version"] == "2.1.0"
        assert doc["$schema"].endswith("sarif-schema-2.1.0.json")
        assert isinstance(doc["runs"], list) and len(doc["runs"]) == 1
        run = doc["runs"][0]
        assert run["tool"]["driver"]["name"] == "semgrep"
        assert run["tool"]["driver"]["rules"] == []
        assert run["results"] == []

    def test_runs_grouped_under_supplied_driver(self):
        doc = sarif_writer.to_sarif([_semgrep_finding()], source="semgrep")
        assert doc["runs"][0]["tool"]["driver"]["name"] == "semgrep"
        assert doc["runs"][0]["tool"]["driver"]["informationUri"] == "https://semgrep.dev"

    def test_blank_source_raises(self):
        with pytest.raises(ValueError):
            sarif_writer.to_sarif([], source="")
        with pytest.raises(ValueError):
            sarif_writer.to_sarif([], source="   ")

    def test_unknown_source_still_valid(self):
        doc = sarif_writer.to_sarif([], source="custom-tool")
        # informationUri falls back to a project pointer
        assert doc["runs"][0]["tool"]["driver"]["informationUri"].startswith("https://")


# ---------------------------------------------------------------------------
# Severity → level mapping (Gemini #2)
# ---------------------------------------------------------------------------

class TestSeverityMapping:

    @pytest.mark.parametrize(
        "severity,expected_level",
        [
            ("critical", "error"),
            ("high", "error"),
            ("medium", "warning"),
            ("low", "note"),
            ("info", "note"),
            ("unknown", "none"),
            ("", "none"),
            (None, "none"),
        ],
    )
    def test_level_mapping(self, severity, expected_level):
        finding = _semgrep_finding(severity=severity)
        doc = sarif_writer.to_sarif([finding], source="semgrep")
        result = doc["runs"][0]["results"][0]
        assert result["level"] == expected_level
        rule = doc["runs"][0]["tool"]["driver"]["rules"][0]
        assert rule["defaultConfiguration"]["level"] == expected_level

    def test_uppercase_severity_normalized(self):
        finding = _semgrep_finding(severity="HIGH")
        doc = sarif_writer.to_sarif([finding], source="semgrep")
        assert doc["runs"][0]["results"][0]["level"] == "error"


# ---------------------------------------------------------------------------
# Rule construction
# ---------------------------------------------------------------------------

class TestRules:

    def test_rule_id_is_source_prefixed(self):
        finding = _semgrep_finding(rule="spawn-shell-true")
        doc = sarif_writer.to_sarif([finding], source="semgrep")
        rule = doc["runs"][0]["tool"]["driver"]["rules"][0]
        assert rule["id"] == "semgrep/spawn-shell-true"
        assert doc["runs"][0]["results"][0]["ruleId"] == "semgrep/spawn-shell-true"

    def test_rules_deduplicated(self):
        a = _semgrep_finding(rule="r1", affected_line=10)
        b = _semgrep_finding(rule="r1", affected_line=20)
        c = _semgrep_finding(rule="r2", affected_line=30)
        doc = sarif_writer.to_sarif([a, b, c], source="semgrep")
        rules = doc["runs"][0]["tool"]["driver"]["rules"]
        rule_ids = sorted(r["id"] for r in rules)
        assert rule_ids == ["semgrep/r1", "semgrep/r2"]
        assert len(doc["runs"][0]["results"]) == 3  # results NOT deduplicated

    def test_security_severity_carried_as_string(self):
        finding = _semgrep_finding(severity_score=7.5)
        doc = sarif_writer.to_sarif([finding], source="semgrep")
        rule = doc["runs"][0]["tool"]["driver"]["rules"][0]
        assert rule["properties"]["security-severity"] == "7.5"

    def test_severity_score_missing_skipped(self):
        finding = _semgrep_finding()
        finding.pop("severity_score", None)
        doc = sarif_writer.to_sarif([finding], source="semgrep")
        rule = doc["runs"][0]["tool"]["driver"]["rules"][0]
        assert "security-severity" not in rule["properties"]

    def test_cwe_tags_propagate(self):
        finding = _semgrep_finding(cwe_classes=["CWE-798", "CWE-259"])
        doc = sarif_writer.to_sarif([finding], source="semgrep")
        rule = doc["runs"][0]["tool"]["driver"]["rules"][0]
        assert "CWE-798" in rule["properties"]["tags"]
        assert "CWE-259" in rule["properties"]["tags"]


# ---------------------------------------------------------------------------
# Result construction
# ---------------------------------------------------------------------------

class TestResults:

    def test_location_for_file_with_line(self):
        finding = _semgrep_finding(affected_file="scripts/api.py", affected_line=42)
        doc = sarif_writer.to_sarif([finding], source="semgrep")
        result = doc["runs"][0]["results"][0]
        loc = result["locations"][0]["physicalLocation"]
        assert loc["artifactLocation"]["uri"] == "scripts/api.py"
        assert loc["region"]["startLine"] == 42

    def test_location_for_file_without_line(self):
        finding = _trivy_finding(affected_file="requirements.txt", affected_line=None)
        doc = sarif_writer.to_sarif([finding], source="trivy")
        result = doc["runs"][0]["results"][0]
        loc = result["locations"][0]["physicalLocation"]
        assert loc["artifactLocation"]["uri"] == "requirements.txt"
        assert "region" not in loc

    def test_no_location_when_file_missing(self):
        finding = _semgrep_finding(affected_file=None, affected_line=None)
        doc = sarif_writer.to_sarif([finding], source="semgrep")
        result = doc["runs"][0]["results"][0]
        assert "locations" not in result

    def test_partial_fingerprint_present(self):
        finding = _semgrep_finding()
        doc = sarif_writer.to_sarif([finding], source="semgrep")
        fp = doc["runs"][0]["results"][0]["partialFingerprints"]
        assert "shipwright/v1" in fp
        assert len(fp["shipwright/v1"]) == 64  # sha256 hex

    def test_fingerprint_stable_across_calls(self):
        finding = _semgrep_finding()
        a = sarif_writer.to_sarif([finding], source="semgrep")
        b = sarif_writer.to_sarif([finding], source="semgrep")
        assert (
            a["runs"][0]["results"][0]["partialFingerprints"]["shipwright/v1"]
            == b["runs"][0]["results"][0]["partialFingerprints"]["shipwright/v1"]
        )

    def test_fingerprint_changes_with_file(self):
        a = _semgrep_finding(affected_file="a.py")
        b = _semgrep_finding(affected_file="b.py")
        doc_a = sarif_writer.to_sarif([a], source="semgrep")
        doc_b = sarif_writer.to_sarif([b], source="semgrep")
        assert (
            doc_a["runs"][0]["results"][0]["partialFingerprints"]["shipwright/v1"]
            != doc_b["runs"][0]["results"][0]["partialFingerprints"]["shipwright/v1"]
        )


# ---------------------------------------------------------------------------
# Robustness — non-dict items, missing fields
# ---------------------------------------------------------------------------

class TestRobustness:

    def test_non_dict_findings_skipped(self):
        doc = sarif_writer.to_sarif(
            [_semgrep_finding(), "junk", None, 42, _semgrep_finding(rule="r2")],
            source="semgrep",
        )
        assert len(doc["runs"][0]["results"]) == 2

    def test_missing_rule_uses_unknown(self):
        finding = _semgrep_finding()
        finding.pop("rule")
        doc = sarif_writer.to_sarif([finding], source="semgrep")
        rule = doc["runs"][0]["tool"]["driver"]["rules"][0]
        assert rule["id"] == "semgrep/unknown"

    def test_finding_source_overrides_per_finding(self):
        # A finding with source=trivy fed into a semgrep group should use
        # its own source for the rule prefix (defensive — caller is expected
        # to pre-group, but mis-grouping shouldn't crash).
        a = _semgrep_finding(source="trivy", rule="CVE-1")
        doc = sarif_writer.to_sarif([a], source="semgrep")
        # Driver name remains the supplied one (semgrep), but the rule id
        # honours the finding's own source.
        assert doc["runs"][0]["tool"]["driver"]["name"] == "semgrep"
        assert doc["runs"][0]["results"][0]["ruleId"] == "trivy/CVE-1"
