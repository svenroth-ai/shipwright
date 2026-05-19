"""Tests for the GitHub findings -> triage importer.

Covers iterate-2026-05-19-github-triage-importer AC1-AC8:
- code-scanning / dependabot / secret-scanning / CI-run -> triage item mapping
- idempotent import (AC4), key-shape-scoped auto-resolve (AC5)
- throttle gate (AC6), gh-absent fail-soft (AC7), secret value never persisted (AC8)
- Boundary Probe (ADR-024): gh-api JSON -> parser; state-file write->read round-trip
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
if str(_SHARED_SCRIPTS / "hooks") not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS / "hooks"))

import github_api  # noqa: E402
import github_triage  # noqa: E402
import import_github_findings as gh_hook  # noqa: E402
from triage import append_triage_item, read_all_items  # noqa: E402

# ---------------------------------------------------------------------------
# Realistic gh-api fixture shapes (trimmed to the fields the parsers read)
# ---------------------------------------------------------------------------

CS_ALERT = {
    "number": 42,
    "state": "open",
    "rule": {
        "id": "py/sql-injection",
        "severity": "error",
        "security_severity_level": "high",
        "description": "SQL query built from user-controlled sources",
    },
    "most_recent_instance": {"location": {"path": "app/db.py", "start_line": 88}},
    "html_url": "https://github.com/o/r/security/code-scanning/42",
}

DB_ALERT = {
    "number": 7,
    "state": "open",
    "security_advisory": {
        "severity": "critical",
        "summary": "Prototype pollution in lodash",
    },
    "dependency": {"package": {"name": "lodash", "ecosystem": "npm"}},
    "html_url": "https://github.com/o/r/security/dependabot/7",
}

# A deliberately NON-token-shaped sentinel: realistic enough to assert on,
# but low-entropy + no credential prefix so credential scanners don't flag it.
_SENTINEL = "SENTINEL-do-not-leak-fixture-marker"

SS_ALERT = {
    "number": 3,
    "state": "open",
    "secret_type": "github_personal_access_token",
    "secret_type_display_name": "GitHub Personal Access Token",
    "secret": _SENTINEL,  # MUST never reach triage.jsonl
    "html_url": "https://github.com/o/r/security/secret-scanning/3",
}

WORKFLOW_RUNS = [
    {  # wf 1 latest -> failure -> imported
        "id": 900, "workflow_id": 1, "name": "CI", "head_branch": "main",
        "head_sha": "abc1234def567", "status": "completed", "conclusion": "failure",
        "html_url": "https://github.com/o/r/actions/runs/900",
    },
    {  # wf 1 older -> success (not latest, ignored)
        "id": 899, "workflow_id": 1, "name": "CI", "head_branch": "main",
        "head_sha": "old0000000", "status": "completed", "conclusion": "success",
        "html_url": "https://github.com/o/r/actions/runs/899",
    },
    {  # wf 2 latest -> success -> not imported
        "id": 898, "workflow_id": 2, "name": "Security", "head_branch": "main",
        "head_sha": "abc1234def567", "status": "completed", "conclusion": "success",
        "html_url": "https://github.com/o/r/actions/runs/898",
    },
]


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


def _patch_api(
    monkeypatch,
    *,
    code_scanning=None,
    dependabot=None,
    secret_scanning=None,
    runs=None,
    available=True,
    branch="main",
):
    """Patch every github_api entry point. `None` = fetch failed; `[]` = empty OK."""
    monkeypatch.setattr(github_api, "gh_available", lambda: available)
    monkeypatch.setattr(github_api, "default_branch", lambda: branch)
    monkeypatch.setattr(
        github_api, "fetch_code_scanning_alerts", lambda: code_scanning
    )
    monkeypatch.setattr(github_api, "fetch_dependabot_alerts", lambda: dependabot)
    monkeypatch.setattr(
        github_api, "fetch_secret_scanning_alerts", lambda: secret_scanning
    )
    monkeypatch.setattr(github_api, "fetch_workflow_runs", lambda branch: runs)


def _append_events(project_root: Path) -> list[dict]:
    """Raw `append`-event lines in triage.jsonl (one per imported finding)."""
    path = project_root / ".shipwright" / "triage.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("event") == "append":
            out.append(obj)
    return out


# ---------------------------------------------------------------------------
# AC1-AC3, AC8 — pure alert -> triage-item mapping
# ---------------------------------------------------------------------------

def test_code_scanning_item_maps_fields():
    item = github_triage.code_scanning_item(CS_ALERT)
    assert item["dedup_key"] == "github:code-scanning:42"
    assert item["severity"] == "high"  # security_severity_level wins over rule.severity
    assert item["kind"] == "bug"
    assert "py/sql-injection" in item["title"]
    assert "app/db.py:88" in item["detail"]


def test_dependabot_item_maps_fields():
    item = github_triage.dependabot_item(DB_ALERT)
    assert item["dedup_key"] == "github:dependabot:7"
    assert item["severity"] == "critical"
    assert item["kind"] == "bug"
    assert "lodash" in item["title"]


def test_secret_scanning_item_maps_fields_and_never_leaks_secret():
    item = github_triage.secret_scanning_item(SS_ALERT)
    assert item["dedup_key"] == "github:secret-scanning:3"
    assert item["severity"] == "critical"
    assert "GitHub Personal Access Token" in item["title"]
    # AC8: the raw secret value must never appear in the persisted fields.
    assert _SENTINEL not in item["title"]
    assert _SENTINEL not in item["detail"]


def test_ci_item_maps_fields():
    item = github_triage.ci_item(WORKFLOW_RUNS[0])
    # dedup key uses the stable workflow_id (1), not the display name
    assert item["dedup_key"] == "github-ci:1:abc1234def567"
    assert item["severity"] == "high"
    assert item["kind"] == "bug"
    assert "CI" in item["title"]


@pytest.mark.parametrize(
    "gh_value,expected",
    [
        ("critical", "critical"), ("high", "high"), ("medium", "medium"),
        ("low", "low"), ("error", "high"), ("warning", "medium"),
        ("note", "low"), ("bogus", "medium"), (None, "medium"),
    ],
)
def test_severity_mapping(gh_value, expected):
    assert github_triage.triage_severity(gh_value) == expected


# ---------------------------------------------------------------------------
# CI: latest-concluded-run-per-workflow logic
# ---------------------------------------------------------------------------

def test_latest_failed_ci_runs_picks_latest_per_workflow():
    failed = github_triage.latest_failed_ci_runs(WORKFLOW_RUNS)
    # Only workflow 1 (latest run 900 = failure); workflow 2 latest = success.
    assert [r["id"] for r in failed] == [900]


def test_latest_failed_ci_runs_skips_in_progress():
    runs = [
        {"id": 2, "workflow_id": 1, "name": "CI", "conclusion": None,
         "head_sha": "x", "head_branch": "main"},  # in progress -> skip
        {"id": 1, "workflow_id": 1, "name": "CI", "conclusion": "failure",
         "head_sha": "y", "head_branch": "main"},  # latest concluded -> failed
    ]
    failed = github_triage.latest_failed_ci_runs(runs)
    assert [r["id"] for r in failed] == [1]


# ---------------------------------------------------------------------------
# AC1-AC4 — import_findings appends + idempotency
# ---------------------------------------------------------------------------

def test_import_findings_appends_items(project, monkeypatch):
    _patch_api(
        monkeypatch, code_scanning=[CS_ALERT], dependabot=[DB_ALERT],
        secret_scanning=[SS_ALERT], runs=WORKFLOW_RUNS,
    )
    result = github_triage.import_findings(project)
    assert result["gh_available"] is True
    assert result["appended"] == 4  # 1 cs + 1 db + 1 ss + 1 ci
    keys = {e["dedupKey"] for e in _append_events(project)}
    assert keys == {
        "github:code-scanning:42", "github:dependabot:7",
        "github:secret-scanning:3", "github-ci:1:abc1234def567",
    }
    assert all(e["source"] == "github" for e in _append_events(project))


def test_import_findings_idempotent(project, monkeypatch):
    _patch_api(
        monkeypatch, code_scanning=[CS_ALERT], dependabot=[], secret_scanning=[],
        runs=[],
    )
    first = github_triage.import_findings(project)
    second = github_triage.import_findings(project)
    assert first["appended"] == 1
    assert second["appended"] == 0  # AC4 — same alert, no duplicate
    assert len(_append_events(project)) == 1


def test_secret_value_never_written_to_triage_file(project, monkeypatch):
    _patch_api(
        monkeypatch, code_scanning=[], dependabot=[], secret_scanning=[SS_ALERT],
        runs=[],
    )
    github_triage.import_findings(project)
    raw = (project / ".shipwright" / "triage.jsonl").read_text(encoding="utf-8")
    assert _SENTINEL not in raw  # AC8


# ---------------------------------------------------------------------------
# AC5 — key-shape-scoped auto-resolve
# ---------------------------------------------------------------------------

def test_import_findings_auto_resolves_fixed_alert(project, monkeypatch):
    _patch_api(monkeypatch, code_scanning=[CS_ALERT], dependabot=[],
               secret_scanning=[], runs=[])
    github_triage.import_findings(project)
    # Alert 42 is now fixed on GitHub -> fetch returns [] (succeeded, empty).
    _patch_api(monkeypatch, code_scanning=[], dependabot=[],
               secret_scanning=[], runs=[])
    result = github_triage.import_findings(project)
    assert result["resolved"] == 1
    item = next(
        i for i in read_all_items(project)
        if i.get("dedupKey") == "github:code-scanning:42"
    )
    assert item["status"] == "dismissed"
    assert item["statusReason"] == "githubResolved"


def test_failed_fetch_does_not_resolve_items(project, monkeypatch):
    """A fetch that FAILED (None) must not auto-resolve that prefix's items."""
    _patch_api(monkeypatch, code_scanning=[CS_ALERT], dependabot=[],
               secret_scanning=[], runs=[])
    github_triage.import_findings(project)
    # code-scanning fetch now FAILS (None) — not "empty".
    _patch_api(monkeypatch, code_scanning=None, dependabot=[],
               secret_scanning=[], runs=[])
    result = github_triage.import_findings(project)
    assert result["resolved"] == 0
    item = next(
        i for i in read_all_items(project)
        if i.get("dedupKey") == "github:code-scanning:42"
    )
    assert item["status"] == "triage"  # still open — fetch failure != resolved


def test_resolve_leaves_other_sources_untouched(project, monkeypatch):
    # A pre-existing non-github triage item.
    append_triage_item(
        project, source="drift", severity="medium", kind="maintenance",
        title="drift item", detail="x", dedup_key="drift:CLAUDE.md:content",
    )
    _patch_api(monkeypatch, code_scanning=[], dependabot=[],
               secret_scanning=[], runs=[])
    github_triage.import_findings(project)
    drift = next(
        i for i in read_all_items(project)
        if i.get("dedupKey") == "drift:CLAUDE.md:content"
    )
    assert drift["status"] == "triage"  # untouched by the github resolve pass


def test_import_findings_gh_unavailable(project, monkeypatch):
    _patch_api(monkeypatch, available=False)
    result = github_triage.import_findings(project)
    assert result["gh_available"] is False
    assert result["appended"] == 0
    assert not (project / ".shipwright" / "triage.jsonl").exists()


# ---------------------------------------------------------------------------
# AC6 — throttle
# ---------------------------------------------------------------------------

def test_is_due_no_state_then_fresh_then_stale(project):
    assert github_triage.is_due(project) is True  # no state file -> due
    now = datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc)
    github_triage.write_last_import(project, now)
    assert github_triage.is_due(project, now=now + timedelta(hours=1)) is False
    assert github_triage.is_due(project, now=now + timedelta(hours=7)) is True


def test_read_last_import_handles_malformed_state(project):
    """A corrupt state file reads as None -> is_due stays conservative (True)."""
    state = project / ".shipwright" / "github_import_state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("{not valid json", encoding="utf-8")
    assert github_triage.read_last_import(project) is None
    assert github_triage.is_due(project) is True


def test_read_last_import_normalizes_naive_timestamp(project):
    """A naive (offset-less) timestamp is normalised to aware UTC, so is_due
    never hits a naive/aware `TypeError` (code-review MEDIUM-1)."""
    state = project / ".shipwright" / "github_import_state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(
        '{"v": 1, "lastImport": "2026-05-19T09:30:00"}', encoding="utf-8"
    )
    parsed = github_triage.read_last_import(project)
    assert parsed is not None
    assert parsed.tzinfo is not None  # normalised to aware
    assert isinstance(github_triage.is_due(project), bool)  # no TypeError raised


def test_throttle_hours_resolution(project, monkeypatch):
    monkeypatch.delenv("SHIPWRIGHT_GITHUB_IMPORT_THROTTLE_HOURS", raising=False)
    # 3. default
    assert github_triage.throttle_hours(project) == github_triage.DEFAULT_THROTTLE_HOURS
    # 2. env override
    monkeypatch.setenv("SHIPWRIGHT_GITHUB_IMPORT_THROTTLE_HOURS", "3")
    assert github_triage.throttle_hours(project) == 3.0
    # 1. run_config wins over env
    (project / "shipwright_run_config.json").write_text(
        json.dumps({"triage": {"github_import_throttle_hours": 2}}),
        encoding="utf-8",
    )
    assert github_triage.throttle_hours(project) == 2.0


def test_state_file_round_trip(project):
    """Boundary Probe — producer (write) -> file -> consumer (read)."""
    when = datetime(2026, 5, 19, 9, 30, 0, tzinfo=timezone.utc)
    github_triage.write_last_import(project, when)
    assert github_triage.read_last_import(project) == when


# ---------------------------------------------------------------------------
# github_api — gh-CLI client (subprocess mocked)
# ---------------------------------------------------------------------------

def test_gh_available_false_when_gh_missing(monkeypatch):
    monkeypatch.setattr(github_api.shutil, "which", lambda _: None)
    assert github_api.gh_available() is False


def test_fetch_returns_none_on_gh_error(monkeypatch):
    def _fake_run(*a, **k):
        return subprocess.CompletedProcess(a, returncode=1, stdout="", stderr="boom")
    monkeypatch.setattr(github_api.subprocess, "run", _fake_run)
    assert github_api.fetch_code_scanning_alerts() is None


def test_fetch_workflow_runs_extracts_list(monkeypatch):
    payload = json.dumps({"workflow_runs": WORKFLOW_RUNS})

    def _fake_run(*a, **k):
        return subprocess.CompletedProcess(a, returncode=0, stdout=payload, stderr="")

    monkeypatch.setattr(github_api.subprocess, "run", _fake_run)
    runs = github_api.fetch_workflow_runs("main")
    assert isinstance(runs, list)
    assert [r["id"] for r in runs] == [900, 899, 898]


# ---------------------------------------------------------------------------
# AC6/AC7 — SessionStart hook (throttle gate + fail-soft)
# ---------------------------------------------------------------------------

def test_hook_throttled_skips_import(project, monkeypatch):
    calls = []
    monkeypatch.setattr(github_triage, "is_due", lambda *a, **k: False)
    monkeypatch.setattr(
        github_triage, "import_findings", lambda *a, **k: calls.append(1)
    )
    assert gh_hook.run(str(project)) == 0
    assert calls == []  # throttled -> import_findings never called


def test_hook_gh_unavailable_exits_zero(project, monkeypatch):
    written = []
    monkeypatch.setattr(github_triage, "is_due", lambda *a, **k: True)
    monkeypatch.setattr(
        github_triage, "import_findings",
        lambda *a, **k: {"gh_available": False, "appended": 0, "resolved": 0},
    )
    monkeypatch.setattr(
        github_triage, "write_last_import", lambda *a, **k: written.append(1)
    )
    assert gh_hook.run(str(project)) == 0  # AC7 — fail-soft
    assert written == []  # gh unavailable -> throttle timestamp NOT advanced


def test_hook_writes_state_and_emits_context_on_success(project, monkeypatch, capsys):
    written = []
    monkeypatch.setattr(github_triage, "is_due", lambda *a, **k: True)
    monkeypatch.setattr(
        github_triage, "import_findings",
        lambda *a, **k: {"gh_available": True, "appended": 2, "resolved": 1},
    )
    monkeypatch.setattr(
        github_triage, "write_last_import", lambda *a, **k: written.append(1)
    )
    assert gh_hook.run(str(project)) == 0
    assert written == [1]  # state advanced after a real import
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "2 new" in payload["hookSpecificOutput"]["additionalContext"]


def test_hook_exits_zero_when_import_raises(project, monkeypatch):
    """AC7 — any exception from import_findings is swallowed; hook exits 0
    (code-review MEDIUM-3 — the central fail-soft guard gets coverage)."""
    monkeypatch.setattr(github_triage, "is_due", lambda *a, **k: True)

    def _boom(*a, **k):
        raise RuntimeError("network exploded")

    monkeypatch.setattr(github_triage, "import_findings", _boom)
    assert gh_hook.run(str(project)) == 0
