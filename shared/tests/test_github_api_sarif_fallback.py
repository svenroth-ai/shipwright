"""AR-10 SARIF-ingestion fallback for the security-scan-results artifact.

When a repo's ``security.yml`` uploads SARIF but no ``findings.json`` — every
``/shipwright-adopt`` repo runs the SARIF-only scanner template —
``download_security_findings`` falls back to parsing ``sarif/*.sarif`` so the
Control-Grade Security dimension still lights. Impl: ``security_findings.py``
(re-exported through ``github_api``). Split out of
``test_github_api_artifact.py`` to keep both test modules under the bloat ceiling.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import github_api  # noqa: E402


def _stub_gh_download_writing(files: dict[str, str]) -> Any:
    """Fake subprocess.run that writes ``{relpath: content}`` into the --dir."""
    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        assert isinstance(cmd, list), "argv list only (no shell=True)"
        if "--dir" in cmd:
            base = Path(cmd[cmd.index("--dir") + 1])
            for rel, content in files.items():
                target = base / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
    return fake_run


# A Trivy-style SARIF: security-severity lives on the RULE, results point by id.
_SARIF_TRIVY = json.dumps({
    "runs": [{
        "tool": {"driver": {"name": "Trivy", "rules": [
            {"id": "GL-CRIT", "properties": {"security-severity": "9.8"}},
            {"id": "GL-HIGH", "properties": {"security-severity": "7.5"}},
            {"id": "GL-MED", "properties": {"security-severity": "5.0"}},
            {"id": "GL-NONE", "properties": {}},
        ]}},
        "results": [
            {"ruleId": "GL-CRIT"}, {"ruleId": "GL-HIGH"},
            {"ruleId": "GL-MED"}, {"ruleId": "GL-NONE"},
        ],
    }],
})

# Gitleaks SARIF: any result is a committed-credential leak → critical.
_SARIF_GITLEAKS = json.dumps({
    "runs": [{
        "tool": {"driver": {"name": "gitleaks", "rules": []}},
        "results": [{"ruleId": "generic-rule"}],
    }],
})


def test_sarif_fallback_buckets_by_cvss_band(monkeypatch: pytest.MonkeyPatch) -> None:
    """No findings.json but SARIF present → results bucketed by CVSS band
    (>=9 critical, >=7 high, >=4 medium, else/none low)."""
    monkeypatch.setattr(
        subprocess, "run",
        _stub_gh_download_writing({"sarif/trivy.sarif": _SARIF_TRIVY}))
    result = github_api.download_security_findings(900)
    assert result is not None
    assert sorted(f["severity"] for f in result) == [
        "critical", "high", "low", "medium"]


def test_sarif_fallback_gitleaks_is_critical(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Gitleaks finding maps to critical regardless of (absent) score."""
    monkeypatch.setattr(
        subprocess, "run",
        _stub_gh_download_writing({"sarif/gitleaks.sarif": _SARIF_GITLEAKS}))
    assert github_api.download_security_findings(900) == [{"severity": "critical"}]


def test_findings_json_wins_over_sarif(monkeypatch: pytest.MonkeyPatch) -> None:
    """A present findings.json is authoritative — SARIF is not consulted."""
    monkeypatch.setattr(subprocess, "run", _stub_gh_download_writing({
        "findings.json": json.dumps({"findings": [{"id": "j1", "severity": "high"}]}),
        "sarif/trivy.sarif": _SARIF_TRIVY,
    }))
    assert github_api.download_security_findings(900) == [
        {"id": "j1", "severity": "high"}]


def test_empty_findings_json_not_overridden_by_sarif(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty findings.json (clean scan) stays [] — never falls through to SARIF."""
    monkeypatch.setattr(subprocess, "run", _stub_gh_download_writing({
        "findings.json": json.dumps({"findings": []}),
        "sarif/trivy.sarif": _SARIF_TRIVY,
    }))
    assert github_api.download_security_findings(900) == []


def test_no_json_no_sarif_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither findings.json nor SARIF in the artifact → None (no scan output)."""
    monkeypatch.setattr(
        subprocess, "run",
        _stub_gh_download_writing({"pr-comment.md": "no scanner output"}))
    assert github_api.download_security_findings(900) is None


def test_prompt_risks_has_no_sarif_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """download_prompt_risks never consults SARIF — absent prompt_risks.json → None."""
    monkeypatch.setattr(
        subprocess, "run",
        _stub_gh_download_writing({"sarif/trivy.sarif": _SARIF_TRIVY}))
    assert github_api.download_prompt_risks(900) is None
