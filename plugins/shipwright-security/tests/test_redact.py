"""Tests for the redact module — secret-evidence sanitisation.

Two layers:
  1. Allowlist-based structural redaction (drop unknown fields by deletion;
     types preserved; never replace ints/bools with strings).
  2. Free-text content masking on description / remediation_hint to scrub
     high-entropy or known-shape secret payloads that a scanner pasted into
     prose (Gitleaks 'description' often quotes the matched secret).
"""
from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

from redact import (  # noqa: E402
    REDACTED_TOKEN,
    SAFE_FIELD_ALLOWLIST,
    mask_secrets_in_text,
    redact_finding,
    redact_findings,
)


# ---------------------------------------------------------------------------
# Allowlist-based redaction
# ---------------------------------------------------------------------------


class TestAllowlistRedaction:

    def test_drops_unknown_fields(self):
        finding = {
            "id": "f-01",
            "severity": "high",
            "rule": "generic-api-key",
            "affected_file": "tests/fixtures/sample.json",
            "affected_line": 8,
            "match": "sk-live-abcd1234",          # raw secret — must drop
            "secret": "sk-live-abcd1234",         # raw secret — must drop
            "fingerprint": "abc:123:line:8",      # tool fingerprint — must drop
            "commit": "deadbeef",                  # git metadata — must drop
            "author": "alice",                     # git metadata — must drop
            "email": "alice@example.com",          # git metadata — must drop
        }
        out = redact_finding(finding)
        assert "match" not in out
        assert "secret" not in out
        assert "fingerprint" not in out
        assert "commit" not in out
        assert "author" not in out
        assert "email" not in out

    def test_keeps_safe_fields_unchanged(self):
        finding = {
            "id": "f-01",
            "severity": "high",
            "rule": "generic-api-key",
            "affected_file": "tests/fixtures/sample.json",
            "affected_line": 8,
        }
        out = redact_finding(finding)
        assert out["id"] == "f-01"
        assert out["severity"] == "high"
        assert out["rule"] == "generic-api-key"
        assert out["affected_file"] == "tests/fixtures/sample.json"
        assert out["affected_line"] == 8

    def test_preserves_types_for_safe_fields(self):
        """Type-safety: ints stay ints, bools stay bools.

        We MUST NOT replace an int with the string '<redacted>' — that breaks
        downstream JSON / SARIF / UI consumers expecting integer line numbers.
        """
        finding = {
            "id": "f-01",
            "severity": "high",
            "rule": "x",
            "affected_file": "a.py",
            "affected_line": 42,
            "severity_score": 7.5,
        }
        out = redact_finding(finding)
        assert isinstance(out["affected_line"], int)
        assert isinstance(out["severity_score"], float)

    def test_redact_findings_handles_list(self):
        findings = [
            {"id": "f-1", "severity": "high", "rule": "x", "match": "secret-a"},
            {"id": "f-2", "severity": "low", "rule": "y", "secret": "secret-b"},
        ]
        out = redact_findings(findings)
        assert len(out) == 2
        assert all("match" not in f for f in out)
        assert all("secret" not in f for f in out)

    def test_full_evidence_disables_allowlist(self):
        finding = {
            "id": "f-01",
            "severity": "high",
            "rule": "x",
            "match": "sk-live-abcd1234",
            "secret": "sk-live-abcd1234",
        }
        out = redact_finding(finding, full_evidence=True)
        assert out["match"] == "sk-live-abcd1234"
        assert out["secret"] == "sk-live-abcd1234"

    def test_safe_field_allowlist_includes_expected(self):
        """Spot-check the contract — adding fields requires conscious update."""
        for name in (
            "id", "severity", "severity_score", "type", "rule", "cve_id",
            "affected_file", "affected_line", "affected_package",
            "installed_version", "fixed_version", "cwe_classes",
            "source", "_remediation_class", "_remediation_status",
            "description", "remediation_hint",
        ):
            assert name in SAFE_FIELD_ALLOWLIST, f"missing safe field: {name}"


# ---------------------------------------------------------------------------
# Free-text masking
# ---------------------------------------------------------------------------


class TestFreeTextMasking:

    def test_masks_sk_live_prefix(self):
        text = "Found credential sk-live-1234567890abcdef in config"
        masked = mask_secrets_in_text(text)
        assert "sk-live-1234567890abcdef" not in masked
        assert REDACTED_TOKEN in masked

    def test_masks_aws_access_key(self):
        text = "AWS key AKIAIOSFODNN7EXAMPLE detected"
        masked = mask_secrets_in_text(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in masked
        assert REDACTED_TOKEN in masked

    def test_masks_github_token(self):
        text = "Use token ghp_abc123def456ghi789jkl012mno345pqr678stuv01 to authenticate"
        masked = mask_secrets_in_text(text)
        assert "ghp_abc123def456ghi789jkl012mno345pqr678stuv01" not in masked
        assert REDACTED_TOKEN in masked

    def test_masks_slack_bot_token(self):
        text = "Use xoxb-1234567890-1234567890-AbCdEfGhIjKlMnOpQrStUvWx for slack"
        masked = mask_secrets_in_text(text)
        assert "xoxb-1234567890-1234567890-AbCdEfGhIjKlMnOpQrStUvWx" not in masked
        assert REDACTED_TOKEN in masked

    def test_masks_bearer_header(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJpZCI6MX0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        masked = mask_secrets_in_text(text)
        assert "eyJhbGciOiJIUzI1NiJ9" not in masked
        assert REDACTED_TOKEN in masked

    def test_masks_high_entropy_string(self):
        # 40-char alphanumeric — looks entropy-y enough to mask
        text = "Found credential abcdefghij0123456789ABCDEFGHIJ0123456789xx in file"
        masked = mask_secrets_in_text(text)
        assert "abcdefghij0123456789ABCDEFGHIJ0123456789xx" not in masked
        assert REDACTED_TOKEN in masked

    def test_does_not_mask_normal_prose(self):
        text = "Use parameterized queries instead of string concatenation."
        masked = mask_secrets_in_text(text)
        assert masked == text

    def test_does_not_mask_short_words(self):
        text = "Hardcoded password 'admin' detected"
        masked = mask_secrets_in_text(text)
        # 'admin' is too short to look like an entropy secret
        assert "admin" in masked

    def test_does_not_mask_normal_uuid_in_prose(self):
        text = "See run-12345678 for details"
        masked = mask_secrets_in_text(text)
        # 16-char hyphen segment doesn't trip entropy patterns
        assert masked == text

    def test_redact_finding_masks_description_field(self):
        finding = {
            "id": "f-01",
            "severity": "high",
            "rule": "generic-api-key",
            "description": "Detected key sk-live-1234567890abcdef in source",
            "affected_file": "a.py",
        }
        out = redact_finding(finding)
        assert "sk-live-1234567890abcdef" not in out["description"]
        assert REDACTED_TOKEN in out["description"]

    def test_redact_finding_masks_remediation_hint_field(self):
        finding = {
            "id": "f-01",
            "severity": "high",
            "rule": "x",
            "remediation_hint": "Replace ghp_abc123def456ghi789jkl012mno345pqr678stuv01 with env var",
            "affected_file": "a.py",
        }
        out = redact_finding(finding)
        assert "ghp_abc123def456ghi789jkl012mno345pqr678stuv01" not in out["remediation_hint"]
        assert REDACTED_TOKEN in out["remediation_hint"]

    def test_full_evidence_disables_masking(self):
        finding = {
            "id": "f-01",
            "severity": "high",
            "rule": "x",
            "description": "Detected key sk-live-1234567890abcdef in source",
            "affected_file": "a.py",
        }
        out = redact_finding(finding, full_evidence=True)
        assert "sk-live-1234567890abcdef" in out["description"]


# ---------------------------------------------------------------------------
# Idempotence
# ---------------------------------------------------------------------------


class TestIdempotence:

    def test_redacting_a_redacted_finding_is_a_noop(self):
        finding = {
            "id": "f-01",
            "severity": "high",
            "rule": "x",
            "affected_file": "a.py",
            "affected_line": 1,
        }
        once = redact_finding(finding)
        twice = redact_finding(once)
        assert once == twice
