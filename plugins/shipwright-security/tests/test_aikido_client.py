"""Tests for aikido_client.py — classification, normalization, CLI parsing."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts to path — must come before imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.aikido_client import (  # noqa: E402
    AikidoClient,
    build_parser,
    classify_finding,
    normalize_issues,
)


# ---------------------------------------------------------------------------
# normalize_issues
# ---------------------------------------------------------------------------

class TestNormalizeIssues:
    def test_list_input(self, sample_aikido_response):
        result = normalize_issues(sample_aikido_response)
        assert len(result) == 5
        assert result[0]["id"] == "aikido-001"

    def test_dict_with_issues_key(self):
        data = {"issues": [{"id": "1"}, {"id": "2"}]}
        assert normalize_issues(data) == [{"id": "1"}, {"id": "2"}]

    def test_dict_with_data_key(self):
        data = {"data": [{"id": "1"}]}
        assert normalize_issues(data) == [{"id": "1"}]

    def test_dict_with_results_key(self):
        data = {"results": [{"id": "1"}]}
        assert normalize_issues(data) == [{"id": "1"}]

    def test_empty_list(self):
        assert normalize_issues([]) == []

    def test_none_input(self):
        assert normalize_issues(None) == []

    def test_string_input(self):
        assert normalize_issues("unexpected") == []


# ---------------------------------------------------------------------------
# classify_finding
# ---------------------------------------------------------------------------

class TestClassifyFinding:
    def test_critical_sca_is_auto_fixable(self):
        finding = {"severity": "critical", "type": "sca"}
        assert classify_finding(finding) == "auto-fixable"

    def test_high_dependency_is_auto_fixable(self):
        finding = {"severity": "high", "type": "dependency"}
        assert classify_finding(finding) == "auto-fixable"

    def test_high_sast_is_agent_fixable(self):
        finding = {"severity": "high", "type": "sast"}
        assert classify_finding(finding) == "agent-fixable"

    def test_high_secret_detection_is_agent_fixable(self):
        finding = {"severity": "high", "type": "secret_detection"}
        assert classify_finding(finding) == "agent-fixable"

    def test_low_severity_is_informational(self):
        finding = {"severity": "low", "type": "sast"}
        assert classify_finding(finding) == "informational"

    def test_info_severity_is_informational(self):
        finding = {"severity": "info", "type": "sca"}
        assert classify_finding(finding) == "informational"

    def test_high_iac_is_needs_review(self):
        finding = {"severity": "high", "type": "iac"}
        assert classify_finding(finding) == "needs-review"

    def test_unknown_type_is_needs_review(self):
        finding = {"severity": "critical", "type": "unknown"}
        assert classify_finding(finding) == "needs-review"

    def test_missing_fields_defaults(self):
        finding = {}
        # Empty severity is "" which doesn't match low/info, empty type doesn't match known types
        assert classify_finding(finding) == "needs-review"

    def test_sample_findings_classification(self, sample_fixable_findings):
        """Verify all sample findings classify as expected."""
        for category, findings in sample_fixable_findings.items():
            for f in findings:
                result = classify_finding(f)
                assert result == f["expected_class"], (
                    f"Finding {f['id']} expected {f['expected_class']}, got {result}"
                )


# ---------------------------------------------------------------------------
# AikidoClient
# ---------------------------------------------------------------------------

class TestAikidoClient:
    def test_not_configured_without_env(self):
        with patch.dict("os.environ", {}, clear=True):
            client = AikidoClient()
            assert not client.is_configured

    def test_configured_with_env(self):
        with patch.dict("os.environ", {
            "AIKIDO_CLIENT_ID": "test-id",
            "AIKIDO_CLIENT_SECRET": "test-secret",
        }):
            client = AikidoClient()
            assert client.is_configured

    def test_authenticate_sends_basic_auth(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "test-token"}
        mock_resp.raise_for_status = MagicMock()

        mock_requests = MagicMock()
        mock_requests.post.return_value = mock_resp

        with patch.dict("os.environ", {
            "AIKIDO_CLIENT_ID": "my-id",
            "AIKIDO_CLIENT_SECRET": "my-secret",
        }):
            with patch.dict("sys.modules", {"requests": mock_requests}):
                client = AikidoClient()
                token = client._authenticate()

        assert token == "test-token"
        call_kwargs = mock_requests.post.call_args
        auth_header = call_kwargs.kwargs.get("headers", {}).get("Authorization", "")
        assert "Basic" in auth_header


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------

class TestBuildParser:
    def test_issues_command(self):
        parser = build_parser()
        args = parser.parse_args(["issues", "--repo", "owner/repo", "--severity", "critical,high"])
        assert args.command == "issues"
        assert args.repo == "owner/repo"
        assert args.severity == "critical,high"

    def test_repos_command(self):
        parser = build_parser()
        args = parser.parse_args(["repos"])
        assert args.command == "repos"

    def test_summary_command(self):
        parser = build_parser()
        args = parser.parse_args(["summary", "--repo", "owner/repo"])
        assert args.command == "summary"
        assert args.repo == "owner/repo"

    def test_report_command_with_output(self):
        parser = build_parser()
        args = parser.parse_args(["report", "--repo", "owner/repo", "--output", "report.md"])
        assert args.command == "report"
        assert args.output == "report.md"

    def test_no_command_raises(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])
