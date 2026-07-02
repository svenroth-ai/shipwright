"""Tests for the prompt_risks.json triage producer (``gh-prompt:`` source).

Prompt-injection findings ship in the SAME ``security-scan-results`` artifact as
``findings.json``; this source emits a SEPARATE, independently-dismissable
``gh-prompt:{owner}/{repo}`` action-unit (parallel to the ``gh-security``
artifact path). Same ADR-052 None-vs-``[]`` + hygiene contract.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import github_api  # noqa: E402
import github_triage  # noqa: E402

OWNER_REPO = "acme/foo"
_mapper = github_triage.prompt_injection_action_unit_from_artifact


# --------------------------------------------------------------------------- #
# Mapper (pure function)
# --------------------------------------------------------------------------- #
def test_returns_none_when_owner_repo_none() -> None:
    assert _mapper(findings=[{"severity": "high"}], owner_repo=None) is None


def test_returns_none_when_findings_empty() -> None:
    # Empty (clean) scan -> None; the orchestrator's auto-resolve gate handles it.
    assert _mapper(findings=[], owner_repo=OWNER_REPO) is None


def test_builds_gh_prompt_unit() -> None:
    unit = _mapper(
        findings=[{"severity": "high"}, {"severity": "critical"}],
        owner_repo=OWNER_REPO,
        workflow_run_url="https://github.com/acme/foo/actions/runs/900",
    )
    assert unit is not None
    assert unit["dedup_key"] == "gh-prompt:acme/foo"
    assert unit["severity"] == "critical"  # max of the two findings
    assert "prompt-injection" in unit["title"]
    assert "2 finding" in unit["title"]
    assert unit["launch_payload"].startswith("/shipwright-security")
    assert "gh-prompt:acme/foo" in unit["launch_payload"]


def test_no_raw_finding_strings_leak() -> None:
    # Hygiene: only aggregated counts + run URL — never raw rule/desc/file text.
    unit = _mapper(
        findings=[{
            "severity": "high",
            "rule": "PY_EVAL_SECRET_RULE",
            "description": "do-not-leak-this-text",
            "file": "secret/path/leak.py",
        }],
        owner_repo=OWNER_REPO,
    )
    assert unit is not None
    blob = unit["detail"] + unit["launch_payload"]
    assert "PY_EVAL_SECRET_RULE" not in blob
    assert "do-not-leak-this-text" not in blob
    assert "secret/path/leak.py" not in blob


# --------------------------------------------------------------------------- #
# Consumer integration (artifact path)
# --------------------------------------------------------------------------- #
def _patch(monkeypatch, *, prompt_findings: Any, findings: Any = None) -> None:
    monkeypatch.setattr(github_api, "gh_available", lambda: True)
    monkeypatch.setattr(github_api, "default_branch", lambda: "main")
    monkeypatch.setattr(github_api, "owner_repo", lambda _: OWNER_REPO)
    monkeypatch.setattr(github_api, "fetch_code_scanning_alerts", lambda: None)
    monkeypatch.setattr(github_api, "fetch_dependabot_alerts", lambda: None)
    monkeypatch.setattr(github_api, "fetch_secret_scanning_alerts", lambda: None)
    monkeypatch.setattr(github_api, "fetch_workflow_runs", lambda b: None)
    monkeypatch.setattr(
        github_api, "latest_security_workflow_run",
        lambda: {"id": 900, "html_url": "https://github.com/acme/foo/actions/runs/900"},
    )
    monkeypatch.setattr(github_api, "download_security_findings", lambda rid: findings)
    monkeypatch.setattr(github_api, "download_prompt_risks", lambda rid: prompt_findings)


def test_prompt_findings_emit_gh_prompt_item(tmp_path, monkeypatch) -> None:
    _patch(monkeypatch, prompt_findings=[{"severity": "high"}])
    result = github_triage.import_findings(tmp_path)
    assert result["by_source"][github_triage.PREFIX_PROMPT] == 1


def test_clean_prompt_scan_emits_nothing(tmp_path, monkeypatch) -> None:
    # [] = clean scan: fetch succeeded, but no item emitted (auto-resolve opens).
    _patch(monkeypatch, prompt_findings=[])
    result = github_triage.import_findings(tmp_path)
    assert result["by_source"][github_triage.PREFIX_PROMPT] == 0


def test_prompt_fetch_failed_is_none(tmp_path, monkeypatch) -> None:
    # None = fetch failed: by_source marks None (auto-resolve stays gated, ADR-052).
    _patch(monkeypatch, prompt_findings=None)
    result = github_triage.import_findings(tmp_path)
    assert result["by_source"][github_triage.PREFIX_PROMPT] is None


# --------------------------------------------------------------------------- #
# Decoupling from Code Scanning (iterate-2026-07-02-gh-prompt-ghost-fix, defect A)
# --------------------------------------------------------------------------- #
# Prompt-injection findings are NEVER uploaded to GitHub Code Scanning
# (security.yml streams only the OSS SAST SARIF). Gating the prompt source on
# ``cs_alerts is None`` therefore left the repo BLIND to prompt-injection whenever
# Code Scanning was available (the healthy-repo case) — a signal loss, and the
# root of the recurring gh-prompt ghost. The prompt source must be evaluated on
# every run, independent of Code Scanning availability. The SAST artifact path
# stays gated (it CAN double-count SARIF findings; prompt-injection cannot).
def _patch_cs_available(
    monkeypatch, *, prompt_findings: Any, sast_findings: Any = None
) -> dict[str, int]:
    """Like ``_patch`` but Code Scanning is AVAILABLE (cs_alerts non-None).

    Returns a call-counter dict so tests can assert the SAST findings.json is NOT
    downloaded when Code Scanning is up (no double-count, no wasted bandwidth).
    """
    calls = {"security_findings": 0, "prompt_risks": 0}

    def _dl_security(rid: Any) -> Any:
        calls["security_findings"] += 1
        return sast_findings

    def _dl_prompt(rid: Any) -> Any:
        calls["prompt_risks"] += 1
        return prompt_findings

    monkeypatch.setattr(github_api, "gh_available", lambda: True)
    monkeypatch.setattr(github_api, "default_branch", lambda: "main")
    monkeypatch.setattr(github_api, "owner_repo", lambda _: OWNER_REPO)
    # Code Scanning AVAILABLE — returns a (possibly empty) list, NOT None.
    monkeypatch.setattr(github_api, "fetch_code_scanning_alerts", lambda: [])
    monkeypatch.setattr(github_api, "fetch_dependabot_alerts", lambda: [])
    monkeypatch.setattr(github_api, "fetch_secret_scanning_alerts", lambda: None)
    monkeypatch.setattr(github_api, "fetch_workflow_runs", lambda b: None)
    monkeypatch.setattr(
        github_api, "latest_security_workflow_run",
        lambda: {"id": 900, "html_url": "https://github.com/acme/foo/actions/runs/900"},
    )
    monkeypatch.setattr(github_api, "download_security_findings", _dl_security)
    monkeypatch.setattr(github_api, "download_prompt_risks", _dl_prompt)
    return calls


def test_prompt_source_fires_when_code_scanning_available(tmp_path, monkeypatch) -> None:
    # Defect A regression: with Code Scanning UP, an open prompt finding must still
    # be surfaced. Pre-fix this returned None (source dead when repo healthy).
    _patch_cs_available(monkeypatch, prompt_findings=[{"severity": "high"}])
    result = github_triage.import_findings(tmp_path)
    assert result["by_source"][github_triage.PREFIX_PROMPT] == 1


def test_clean_prompt_scan_resolves_when_code_scanning_available(tmp_path, monkeypatch) -> None:
    # [] = clean scan with Code Scanning up: fetch succeeded, no item emitted, and
    # the auto-resolve gate opens for PREFIX_PROMPT (so a fixed finding can clear).
    _patch_cs_available(monkeypatch, prompt_findings=[])
    result = github_triage.import_findings(tmp_path)
    assert result["by_source"][github_triage.PREFIX_PROMPT] == 0


def test_sast_findings_stay_gated_when_code_scanning_available(tmp_path, monkeypatch) -> None:
    # Invariant preserved: prompt_risks.json IS fetched (orthogonal to Code Scanning),
    # but the SAST findings.json is NOT — it would double-count the SARIF alerts.
    calls = _patch_cs_available(
        monkeypatch, prompt_findings=[{"severity": "high"}], sast_findings=[{"severity": "critical"}]
    )
    github_triage.import_findings(tmp_path)
    assert calls["prompt_risks"] == 1, "prompt_risks.json must be fetched even when Code Scanning is up"
    assert calls["security_findings"] == 0, "SAST findings.json must stay gated on cs_alerts is None"
