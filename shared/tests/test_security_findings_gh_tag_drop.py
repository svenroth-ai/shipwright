"""Accepted-risk GH-owned mutable-action-tag drop in the artifact-ingest path.

The plugin's Semgrep tailoring (``SHIPWRIGHT_SEMGREP_ACCEPT_GH_OWNED_ACTION_TAGS``)
only ran in the LOCAL scan path (``oss_backend -> normalize_tailored``). Every
``/shipwright-adopt`` repo runs the SARIF-only template (raw ``semgrep scan``),
so the un-tailored SARIF flowed into ``download_security_findings`` ->
``_findings_from_sarif`` -> the ``gh-security`` triage producer, which counted
the GH-owned mutable-tag findings the repo had formally ACCEPTED (declined
SHA-pin posture, 2026-06-30). Result: a recurring false "N low" triage alarm in
every adopted repo (shipwright-webui run 28784266061: 18 open, all GH-owned).

This lifts the owner-scoped predicate into ``gh_action_tag_owner`` and applies
the SAME opt-in drop at the SARIF-ingest boundary, right beside the existing
inSource-suppression filter. Third-party mutable tags STAY counted — the
supply-chain guard the rule exists for. Owner is read from the workflow FILE at
the finding's line (via ``workflow_base``, the repo root at triage-import time);
an unresolvable owner KEEPS the finding (fail toward the signal).
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
import github_triage  # noqa: E402
import security_findings  # noqa: E402
from gh_action_tag_owner import action_owner_from_file  # noqa: E402
from security_findings import _findings_from_sarif  # noqa: E402

_ACCEPT_ENV = "SHIPWRIGHT_SEMGREP_ACCEPT_GH_OWNED_ACTION_TAGS"

# The real (doubled) registry check_id from the actual weekly self-scan.
MUTABLE_TAG_RULE = (
    "yaml.github-actions.security.github-actions-mutable-action-tag"
    ".github-actions-mutable-action-tag"
)

# Workflow with GitHub-owned (lines 5, 6) and third-party (line 7) `uses:`.
_WORKFLOW = (
    "name: x\n"                                       # 1
    "jobs:\n"                                         # 2
    "  a:\n"                                          # 3
    "    steps:\n"                                    # 4
    "      - uses: actions/checkout@v4\n"             # 5  github-owned
    "      - uses: github/codeql-action/init@v3\n"    # 6  github-owned
    "      - uses: evilcorp/thing@v1\n"               # 7  third-party
)


def _tag_result(line: int) -> dict:
    """A mutable-action-tag SARIF result pointing at ci.yml:``line``."""
    return {
        "ruleId": MUTABLE_TAG_RULE,
        "locations": [{
            "physicalLocation": {
                "artifactLocation": {"uri": ".github/workflows/ci.yml"},
                "region": {"startLine": line},
            }
        }],
    }


def _semgrep_sarif() -> str:
    """SARIF with 3 mutable-tag findings (2 GH-owned, 1 third-party) plus one
    unrelated live high finding that must always survive."""
    return json.dumps({
        "runs": [{
            "tool": {"driver": {"name": "Semgrep", "rules": [
                {"id": MUTABLE_TAG_RULE, "properties": {}},
                {"id": "py.high", "properties": {"security-severity": "7.5"}},
            ]}},
            "results": [
                _tag_result(5),   # actions/*  -> GH-owned
                _tag_result(6),   # github/*   -> GH-owned
                _tag_result(7),   # evilcorp/* -> third-party
                {"ruleId": "py.high",
                 "locations": [{"physicalLocation": {
                     "artifactLocation": {"uri": "app/x.py"},
                     "region": {"startLine": 1}}}]},
            ],
        }],
    })


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A project root containing the referenced workflow file."""
    wf = tmp_path / ".github" / "workflows" / "ci.yml"
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(_WORKFLOW, encoding="utf-8")
    return tmp_path


@pytest.fixture
def sarif_root(tmp_path: Path) -> Path:
    """A separate dir holding the downloaded SARIF (mirrors the artifact zip)."""
    root = tmp_path / "artifact"
    (root / "sarif").mkdir(parents=True, exist_ok=True)
    (root / "sarif" / "semgrep.sarif").write_text(_semgrep_sarif(), encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# action_owner_from_file — base_dir enforces the repo-relative ingest contract
# ---------------------------------------------------------------------------

def test_owner_base_dir_rejects_absolute_and_traversal(tmp_path):
    """Under a base_dir (the ingest contract), an absolute or ``..``-escaping uri
    is rejected → KEEP, even when the target file DOES hold a GH-owned `uses:`.
    Without a base_dir (plugin path) an absolute path is still honoured."""
    outside = tmp_path / "outside.yml"
    outside.write_text("      - uses: actions/checkout@v4\n" * 5, encoding="utf-8")
    base = tmp_path / "repo"
    base.mkdir()
    # Absolute uri to a GH-owned workflow: guarded under base_dir, allowed without.
    assert action_owner_from_file(str(outside), 1, base_dir=base) is None
    assert action_owner_from_file(str(outside), 1, base_dir=None) == "actions"
    # `..` escape that WOULD resolve to the GH-owned file is rejected → KEEP.
    assert action_owner_from_file("../outside.yml", 1, base_dir=base) is None


# ---------------------------------------------------------------------------
# _findings_from_sarif — the drop lives here, beside the suppression filter
# ---------------------------------------------------------------------------

def test_default_env_keeps_every_tag(sarif_root, repo, monkeypatch):
    """Opt-in default OFF: nothing dropped — 3 tags (low) + 1 high."""
    monkeypatch.delenv(_ACCEPT_ENV, raising=False)
    out = _findings_from_sarif(sarif_root, workflow_base=repo)
    assert sorted(f["severity"] for f in out) == ["high", "low", "low", "low"]


def test_accept_drops_gh_owned_keeps_third_party(sarif_root, repo, monkeypatch):
    """Env ON + workflow_base set: the 2 GH-owned tags drop, the third-party
    tag stays (count 1), and the unrelated high finding always survives."""
    monkeypatch.setenv(_ACCEPT_ENV, "1")
    out = _findings_from_sarif(sarif_root, workflow_base=repo)
    # actions/* + github/* dropped; evilcorp/* (low) + py.high (high) remain.
    assert sorted(f["severity"] for f in out) == ["high", "low"]


def test_accept_without_workflow_base_keeps_all(sarif_root, monkeypatch):
    """Env ON but no workflow_base: owner is unresolvable → KEEP every tag
    (fail toward the signal, never silently over-suppress)."""
    monkeypatch.setenv(_ACCEPT_ENV, "1")
    out = _findings_from_sarif(sarif_root, workflow_base=None)
    assert sorted(f["severity"] for f in out) == ["high", "low", "low", "low"]


def test_accept_keeps_tag_when_line_drifted(sarif_root, tmp_path, monkeypatch):
    """Env ON but the workflow line no longer holds a GH-owned `uses:` (the
    committed tree drifted from the scanned commit): owner unresolvable → KEEP."""
    monkeypatch.setenv(_ACCEPT_ENV, "1")
    drifted = tmp_path / "drift"
    wf = drifted / ".github" / "workflows" / "ci.yml"
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text("name: x\njobs: {}\n", encoding="utf-8")  # no uses on line 5-7
    out = _findings_from_sarif(sarif_root, workflow_base=drifted)
    assert sorted(f["severity"] for f in out) == ["high", "low", "low", "low"]


# ---------------------------------------------------------------------------
# download_security_findings — end-to-end producer count (the reported alarm)
# ---------------------------------------------------------------------------

def _stub_gh_download_writing(files: dict[str, str]) -> Any:
    """Fake subprocess.run that writes ``{relpath: content}`` into --dir."""
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


def test_download_counts_zero_gh_owned_when_accepted(repo, monkeypatch):
    """The producer count the triage alarm reads: GH-owned tags accepted ->
    the two GH-owned tags are gone (only third-party + high remain)."""
    monkeypatch.setenv(_ACCEPT_ENV, "1")
    monkeypatch.setattr(
        subprocess, "run",
        _stub_gh_download_writing({"sarif/semgrep.sarif": _semgrep_sarif()}))
    result = security_findings.download_security_findings(900, workflow_base=repo)
    assert result is not None
    assert sorted(f["severity"] for f in result) == ["high", "low"]


def test_download_counts_all_when_not_accepted(repo, monkeypatch):
    """Default OFF: the raw SARIF count is unchanged (3 tags + 1 high)."""
    monkeypatch.delenv(_ACCEPT_ENV, raising=False)
    monkeypatch.setattr(
        subprocess, "run",
        _stub_gh_download_writing({"sarif/semgrep.sarif": _semgrep_sarif()}))
    result = security_findings.download_security_findings(900, workflow_base=repo)
    assert sorted(f["severity"] for f in result) == ["high", "low", "low", "low"]


# ---------------------------------------------------------------------------
# End-to-end via import_findings — the reported alarm actually goes away
# ---------------------------------------------------------------------------

_ALL_GH_OWNED_SARIF = json.dumps({
    "runs": [{
        "tool": {"driver": {"name": "Semgrep", "rules": [
            {"id": MUTABLE_TAG_RULE, "properties": {}},
        ]}},
        "results": [_tag_result(5), _tag_result(6)],  # actions/* + github/*
    }],
})


def _patch_artifact_only(monkeypatch, repo: Path, sarif: str) -> None:
    """GHAS Code Scanning down → the SARIF artifact path fires; the gh download
    is stubbed to write ``sarif`` and the repo tree holds the workflow file."""
    monkeypatch.setattr(github_api, "gh_available", lambda: True)
    monkeypatch.setattr(github_api, "default_branch", lambda: "main")
    monkeypatch.setattr(github_api, "owner_repo", lambda _: "acme/foo")
    monkeypatch.setattr(github_api, "fetch_code_scanning_alerts", lambda: None)
    monkeypatch.setattr(github_api, "fetch_dependabot_alerts", lambda: None)
    monkeypatch.setattr(github_api, "fetch_secret_scanning_alerts", lambda: None)
    monkeypatch.setattr(github_api, "fetch_workflow_runs", lambda b: None)
    monkeypatch.setattr(
        github_api, "latest_security_workflow_run",
        lambda: {"id": 900, "html_url": "https://github.com/acme/foo/actions/runs/900"})
    monkeypatch.setattr(github_api, "download_prompt_risks", lambda rid, *a, **k: None)
    monkeypatch.setattr(
        subprocess, "run", _stub_gh_download_writing({"sarif/semgrep.sarif": sarif}))


def _gh_security_appends(project_root: Path) -> list[dict]:
    path = project_root / ".shipwright" / "triage.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("event") == "append" and str(
                obj.get("dedupKey", "")).startswith("gh-security:"):
            out.append(obj)
    return out


def test_import_findings_no_alarm_when_gh_owned_accepted(repo, monkeypatch):
    """The reported symptom, fixed end-to-end: an adopted repo whose CI uploads
    raw SARIF with ONLY GH-owned mutable-tags + the accept env set → the tags
    drop to an empty findings list, so import_findings emits NO gh-security item
    (no recurring false 'N low' alarm). Mirrors shipwright-webui run 28784266061."""
    monkeypatch.setenv(_ACCEPT_ENV, "1")
    _patch_artifact_only(monkeypatch, repo, _ALL_GH_OWNED_SARIF)
    result = github_triage.import_findings(repo)
    assert result["gh_available"] is True
    assert _gh_security_appends(repo) == []
    assert result["by_source"].get("gh-security:artifact", 0) == 0


def test_import_findings_alarm_fires_without_accept(repo, monkeypatch):
    """Causality guard: the SAME SARIF WITHOUT the accept env still surfaces the
    two GH-owned tags as a gh-security item — proving the drop (not some other
    gate) is what silences the alarm, and that opt-out repos are unaffected."""
    monkeypatch.delenv(_ACCEPT_ENV, raising=False)
    _patch_artifact_only(monkeypatch, repo, _ALL_GH_OWNED_SARIF)
    result = github_triage.import_findings(repo)
    appends = _gh_security_appends(repo)
    assert len(appends) == 1
    assert result["by_source"].get("gh-security:artifact") == 1
