"""Tests for the AR-10 producer — refresh_ci_security (network half).

The network calls are injected via a fake ``api`` object, so these run
offline + deterministically. Covers the happy path (writes a summary the
renderer/grader can read) and every fail-soft branch (gh down, no run,
fetch failed, unexpected error) — the producer must NEVER raise and never
clobber a good summary with empty data (AC6).
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.lib.ci_security import load_ci_security, write_ci_security  # noqa: E402
from scripts.tools.refresh_ci_security import refresh_ci_security  # noqa: E402


class _FakeApi:
    """Stand-in for the shared ``github_api`` module."""

    def __init__(self, *, available=True, run=None, findings=None, prompt=None):
        self._available = available
        self._run = run
        self._findings = findings
        self._prompt = prompt
        self.workflow_base_seen = "unset"

    def gh_available(self):
        return self._available

    def latest_security_workflow_run(self):
        return self._run

    def download_security_findings(self, run_id, workflow_base=None):  # noqa: ARG002
        self.workflow_base_seen = workflow_base
        return self._findings

    def download_prompt_risks(self, run_id):  # noqa: ARG002
        return self._prompt


_RUN = {"id": 27950188761, "run_started_at": "2026-06-22T11:44:18+00:00"}
_FINDINGS = [{"severity": "high"}, {"severity": "high"},
             {"severity": "high"}, {"severity": "medium"}]


def test_happy_path_writes_summary(tmp_path):
    api = _FakeApi(run=_RUN, findings=_FINDINGS, prompt=[])
    result = refresh_ci_security(tmp_path, api=api)
    assert result["status"] == "written"
    assert result["open_high_critical"] == 3
    assert result["critical_gate"] == "pass"
    summary = load_ci_security(tmp_path)
    assert summary["by_severity"] == {"critical": 0, "high": 3, "medium": 1, "low": 0}
    assert summary["source"] == "security.yml#27950188761"
    assert summary["scan_date"] == "2026-06-22T11:44:18+00:00"


def test_skips_when_gh_unavailable_without_clobber(tmp_path):
    # A good summary already exists; a fail-soft skip must leave it intact.
    write_ci_security(tmp_path, {"open_high_critical": 0, "by_severity": {},
                                 "scan_date": "keep-me"})
    api = _FakeApi(available=False)
    result = refresh_ci_security(tmp_path, api=api)
    assert result["status"] == "skipped"
    assert result["reason"] == "gh-unavailable"
    assert load_ci_security(tmp_path)["scan_date"] == "keep-me"  # untouched


def test_skips_when_no_fresh_run(tmp_path):
    api = _FakeApi(run=None)
    assert refresh_ci_security(tmp_path, api=api)["status"] == "skipped"
    assert load_ci_security(tmp_path) is None  # nothing fabricated


def test_skips_when_findings_fetch_fails(tmp_path):
    # ADR-052: None (fetch failed) is NOT empty — must not write a green summary.
    api = _FakeApi(run=_RUN, findings=None)
    result = refresh_ci_security(tmp_path, api=api)
    assert result["status"] == "skipped"
    assert result["reason"] == "findings-fetch-failed"
    assert load_ci_security(tmp_path) is None


def test_empty_findings_is_a_real_clean_scan(tmp_path):
    # [] (not None) is a genuine green scan → write a measurable 0 summary.
    api = _FakeApi(run=_RUN, findings=[], prompt=[])
    result = refresh_ci_security(tmp_path, api=api)
    assert result["status"] == "written"
    assert result["open_high_critical"] == 0
    assert load_ci_security(tmp_path)["critical_gate"] == "pass"


def test_unexpected_error_is_caught(tmp_path):
    class _Boom:
        def gh_available(self):
            raise RuntimeError("network exploded")
    result = refresh_ci_security(tmp_path, api=_Boom())
    assert result["status"] == "error"
    assert "RuntimeError" in result["reason"]


def test_prompt_none_treated_as_empty(tmp_path):
    api = _FakeApi(run=_RUN, findings=[], prompt=None)
    result = refresh_ci_security(tmp_path, api=api)
    assert result["status"] == "written"
    assert load_ci_security(tmp_path)["prompt_injection"] == 0


def test_passes_project_root_as_workflow_base(tmp_path):
    # The grade path must forward the repo root so the SARIF fallback can drop
    # opted-in accepted GH-owned mutable-action-tags (same posture as triage).
    api = _FakeApi(run=_RUN, findings=[], prompt=[])
    refresh_ci_security(tmp_path, api=api)
    assert api.workflow_base_seen == tmp_path
