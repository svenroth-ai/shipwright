"""Tests for github_api artifact helpers (Iterate C — security-artifact-producer).

Two new helpers:

- ``latest_security_workflow_run()`` — pick the most recent successful run of
  ``.github/workflows/security.yml`` on the default branch, gated by
  ``SHIPWRIGHT_GITHUB_ARTIFACT_MAX_AGE_DAYS`` (default 14).
- ``download_security_findings(run_id)`` — pull the ``security-scan-results``
  artifact for a given run id and return the parsed ``findings`` list, or
  ``None`` on any failure (gh missing, run gone, artifact expired, malformed
  JSON, non-list findings, nested layout).

Both helpers follow the existing ``github_api`` ``None``-on-any-failure
contract — fail-soft so a dead artifact path never blocks SessionStart.

External-review HIGH findings drove these test cases:

- Freshness gate (openai-5): runs older than the env-configurable cutoff
  return ``None``.
- Default-branch filter (openai-6, gemini-3): API query carries
  ``branch=<default>`` and ``status=success`` so unrelated feature-branch
  runs are filtered out at the source.
- Subprocess hygiene (openai-10, gemini-4): argv list, never shell=True.
- Nested layout (openai-14): file discovery via rglob in case the artifact
  ever lands in a subdirectory.
- Semantic validation (openai-9): truth is the ``findings`` list — not the
  ``by_severity`` aggregate; a non-list ``findings`` returns ``None``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import github_api  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures — minimal run records (only the fields the helpers actually read)
# ---------------------------------------------------------------------------

def _run(
    *,
    id_: int = 100,
    created_offset_hours: float = -1.0,
    branch: str = "main",
    conclusion: str = "success",
) -> dict:
    """Build a workflow-run record, dated `created_offset_hours` from now."""
    ts = datetime.now(timezone.utc) + timedelta(hours=created_offset_hours)
    return {
        "id": id_,
        "name": "Security Scan",
        "head_branch": branch,
        "head_sha": "abc" * 10,
        "status": "completed",
        "conclusion": conclusion,
        "created_at": ts.isoformat().replace("+00:00", "Z"),
        "html_url": f"https://github.com/acme/foo/actions/runs/{id_}",
    }


FRESH_RUN = _run(id_=900, created_offset_hours=-1.0)
DAY_OLD_RUN = _run(id_=901, created_offset_hours=-24.0)
STALE_RUN = _run(id_=902, created_offset_hours=-24.0 * 30)  # 30 days


def _patch_api_call(monkeypatch, response: Any) -> list[str]:
    """Monkeypatch ``github_api._gh_api`` to capture the requested path."""
    captured: list[str] = []

    def fake_gh_api(path: str, *, paginate: bool = False) -> Any:
        captured.append(path)
        return response

    monkeypatch.setattr(github_api, "_gh_api", fake_gh_api)
    return captured


# ---------------------------------------------------------------------------
# latest_security_workflow_run — happy paths and filters
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.14")
def test_latest_security_workflow_run_returns_fresh_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Newest successful run within the freshness window → return it."""
    monkeypatch.setattr(github_api, "default_branch", lambda: "main")
    _patch_api_call(monkeypatch, {"total_count": 1, "workflow_runs": [FRESH_RUN]})
    result = github_api.latest_security_workflow_run()
    assert result is not None
    assert result["id"] == 900


@pytest.mark.covers("FR-01.14")
def test_latest_security_workflow_run_queries_default_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """API path embeds branch=<default> + status=success — openai-6, gemini-3."""
    monkeypatch.setattr(github_api, "default_branch", lambda: "master")
    captured = _patch_api_call(
        monkeypatch, {"workflow_runs": [_run(id_=1)]},
    )
    github_api.latest_security_workflow_run()
    assert len(captured) == 1
    path = captured[0]
    # The branch the helper resolved auto — not a caller arg.
    assert "branch=master" in path
    assert "status=success" in path
    # And we hit the file-name endpoint, not workflow_id (path lookup by basename)
    assert "actions/workflows/security.yml/runs" in path


@pytest.mark.covers("FR-01.14")
def test_latest_security_workflow_run_returns_none_on_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No matching runs → None, NOT an empty dict."""
    monkeypatch.setattr(github_api, "default_branch", lambda: "main")
    _patch_api_call(monkeypatch, {"total_count": 0, "workflow_runs": []})
    assert github_api.latest_security_workflow_run() is None


@pytest.mark.covers("FR-01.14")
def test_latest_security_workflow_run_returns_none_on_api_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_gh_api returns None (gh missing / 403 / network) → None."""
    monkeypatch.setattr(github_api, "default_branch", lambda: "main")
    _patch_api_call(monkeypatch, None)
    assert github_api.latest_security_workflow_run() is None


@pytest.mark.covers("FR-01.14")
def test_latest_security_workflow_run_returns_none_on_malformed_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing workflow_runs / non-list / non-dict → None."""
    monkeypatch.setattr(github_api, "default_branch", lambda: "main")
    for bad in ({}, {"workflow_runs": None}, {"workflow_runs": "not-a-list"}, []):
        _patch_api_call(monkeypatch, bad)
        assert github_api.latest_security_workflow_run() is None, (
            f"malformed payload {bad!r} should produce None"
        )


@pytest.mark.covers("FR-01.14")
def test_latest_security_workflow_run_freshness_gate_default_14d(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run older than the default 14-day cutoff → None — openai-5."""
    monkeypatch.delenv("SHIPWRIGHT_GITHUB_ARTIFACT_MAX_AGE_DAYS", raising=False)
    monkeypatch.setattr(github_api, "default_branch", lambda: "main")
    _patch_api_call(monkeypatch, {"workflow_runs": [STALE_RUN]})
    assert github_api.latest_security_workflow_run() is None


@pytest.mark.covers("FR-01.14")
def test_latest_security_workflow_run_freshness_gate_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Env var override allows tighter / looser cutoffs."""
    monkeypatch.setattr(github_api, "default_branch", lambda: "main")
    # Stale 30d run + cutoff bumped to 60d → accept.
    monkeypatch.setenv("SHIPWRIGHT_GITHUB_ARTIFACT_MAX_AGE_DAYS", "60")
    _patch_api_call(monkeypatch, {"workflow_runs": [STALE_RUN]})
    assert github_api.latest_security_workflow_run() is not None
    # Tight cutoff 0.5d + a 24h-old run → reject.
    monkeypatch.setenv("SHIPWRIGHT_GITHUB_ARTIFACT_MAX_AGE_DAYS", "0.5")
    _patch_api_call(monkeypatch, {"workflow_runs": [DAY_OLD_RUN]})
    assert github_api.latest_security_workflow_run() is None


@pytest.mark.covers("FR-01.14")
def test_latest_security_workflow_run_picks_first_fresh_skipping_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mixed stale + fresh runs — return the first fresh one (newest by API order)."""
    monkeypatch.setattr(github_api, "default_branch", lambda: "main")
    # API returns newest-first; the stale entries shouldn't disqualify fresher ones.
    _patch_api_call(monkeypatch, {"workflow_runs": [FRESH_RUN, STALE_RUN]})
    result = github_api.latest_security_workflow_run()
    assert result is not None
    assert result["id"] == FRESH_RUN["id"]


@pytest.mark.covers("FR-01.14")
def test_latest_security_workflow_run_invalid_created_at_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run with an unparseable created_at is skipped — never raise."""
    monkeypatch.setattr(github_api, "default_branch", lambda: "main")
    bad_run = dict(FRESH_RUN)
    bad_run["created_at"] = "not-a-timestamp"
    # Bad first, fresh second → still picks the fresh one.
    _patch_api_call(monkeypatch, {"workflow_runs": [bad_run, FRESH_RUN]})
    assert github_api.latest_security_workflow_run()["id"] == FRESH_RUN["id"]


# ---------------------------------------------------------------------------
# download_security_findings — artifact extraction
# ---------------------------------------------------------------------------

_FINDINGS_PAYLOAD: dict[str, Any] = {
    "scan_date": "2026-05-20T22:13:23Z",
    "total_findings": 2,
    "by_severity": {"critical": 0, "high": 1, "medium": 1, "low": 0, "info": 0},
    "findings": [
        {
            "id": "semgrep-0001",
            "severity": "high",
            "rule": "py.injection",
            "affected_file": "app/db.py",
            "affected_line": 88,
            "source": "semgrep",
        },
        {
            "id": "trivy-0001",
            "severity": "medium",
            "cve_id": "CVE-2026-0001",
            "affected_package": "urllib3",
            "source": "trivy",
        },
    ],
}


def _stub_gh_run_download(
    *,
    success: bool = True,
    artifact_layout: str = "flat",  # "flat", "nested", "missing"
    file_contents: str | None = None,
) -> Any:
    """Build a fake subprocess.run that simulates `gh run download`.

    Writes a fake findings.json under the requested --dir argument.
    """
    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        # Argv-list discipline: cmd must be a list, never a shell string.
        assert isinstance(cmd, list), "subprocess.run must be passed a list (no shell=True)"
        assert kwargs.get("shell") is not True, "shell=True forbidden"
        # Find the --dir argument
        if "--dir" in cmd:
            tmpdir = Path(cmd[cmd.index("--dir") + 1])
            if success and artifact_layout != "missing":
                if artifact_layout == "nested":
                    target = tmpdir / "subdir" / "findings.json"
                    target.parent.mkdir(parents=True, exist_ok=True)
                else:
                    target = tmpdir / "findings.json"
                content = (
                    file_contents
                    if file_contents is not None
                    else json.dumps(_FINDINGS_PAYLOAD)
                )
                target.write_text(content, encoding="utf-8")
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0 if success else 1,
            stdout="",
            stderr="" if success else "no artifact found",
        )
    return fake_run


@pytest.mark.covers("FR-01.14")
def test_download_security_findings_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Successful download + valid JSON → returns the findings list."""
    monkeypatch.setattr(subprocess, "run", _stub_gh_run_download(success=True))
    result = github_api.download_security_findings(900)
    assert result is not None
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["id"] == "semgrep-0001"


@pytest.mark.covers("FR-01.14")
def test_download_security_findings_uses_argv_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Subprocess invocation uses argv list with shell=False — openai-10/gemini-4."""
    captured: list[Any] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        captured.append((cmd, kwargs))
        # Provide the expected file so the path doesn't fail downstream.
        if "--dir" in cmd:
            tmpdir = Path(cmd[cmd.index("--dir") + 1])
            (tmpdir / "findings.json").write_text(
                json.dumps(_FINDINGS_PAYLOAD), encoding="utf-8"
            )
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    github_api.download_security_findings(900)
    assert captured, "subprocess.run must be invoked"
    cmd, kwargs = captured[0]
    assert isinstance(cmd, list), "argv must be a list, never a string"
    assert cmd[0] == "gh"
    assert "run" in cmd and "download" in cmd
    assert "900" in cmd, "run_id must appear in argv (as str)"
    # `shell=True` would be a command-injection footgun
    assert kwargs.get("shell") is not True
    # And a bounded timeout is set so a hung gh never freezes a session.
    assert "timeout" in kwargs


@pytest.mark.covers("FR-01.14")
def test_download_security_findings_returns_none_on_subprocess_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-zero exit from gh → None, not a raise."""
    monkeypatch.setattr(subprocess, "run", _stub_gh_run_download(success=False))
    assert github_api.download_security_findings(900) is None


@pytest.mark.covers("FR-01.14")
def test_download_security_findings_returns_none_when_gh_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FileNotFoundError on subprocess (gh not installed) → None."""

    def raising_run(*args: Any, **kwargs: Any) -> Any:
        raise FileNotFoundError("gh not found")

    monkeypatch.setattr(subprocess, "run", raising_run)
    assert github_api.download_security_findings(900) is None


@pytest.mark.covers("FR-01.14")
def test_download_security_findings_returns_none_when_file_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """gh exited 0 but findings.json absent → None, not crash."""
    monkeypatch.setattr(
        subprocess, "run", _stub_gh_run_download(success=True, artifact_layout="missing"),
    )
    assert github_api.download_security_findings(900) is None


@pytest.mark.covers("FR-01.14")
def test_download_security_findings_discovers_nested_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Robust discovery via rglob — openai-14: nested artifact layouts work."""
    monkeypatch.setattr(
        subprocess, "run", _stub_gh_run_download(success=True, artifact_layout="nested"),
    )
    result = github_api.download_security_findings(900)
    assert result is not None
    assert len(result) == 2


@pytest.mark.covers("FR-01.14")
def test_download_security_findings_returns_none_on_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Truncated / non-JSON content → None."""
    monkeypatch.setattr(
        subprocess, "run",
        _stub_gh_run_download(success=True, file_contents='{"findings": [trunc'),
    )
    assert github_api.download_security_findings(900) is None


@pytest.mark.covers("FR-01.14")
def test_download_security_findings_returns_none_when_findings_not_a_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Semantic validation: ``findings`` must be a list — openai-9."""
    bad_payloads = [
        '{"findings": null}',
        '{"findings": "not-a-list"}',
        '{"findings": 42}',
        '{"findings": {"keyed": "by-id"}}',
        '{}',  # missing entirely
    ]
    for bad in bad_payloads:
        monkeypatch.setattr(
            subprocess, "run",
            _stub_gh_run_download(success=True, file_contents=bad),
        )
        result = github_api.download_security_findings(900)
        assert result is None, f"bad payload {bad!r} should yield None"


@pytest.mark.covers("FR-01.14")
def test_download_security_findings_accepts_empty_findings_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clean scan: empty list is a valid SUCCESS state (≠ None / failure)."""
    monkeypatch.setattr(
        subprocess, "run",
        _stub_gh_run_download(
            success=True,
            file_contents=json.dumps({"findings": []}),
        ),
    )
    result = github_api.download_security_findings(900)
    assert result == []  # NOT None — clean scan must be distinguishable from failure


@pytest.mark.covers("FR-01.14")
def test_download_security_findings_cleans_up_tempdir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Tempdir lifecycle: created, used, removed even on success."""
    created: list[str] = []

    real_run = _stub_gh_run_download(success=True)

    def tracking_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        if "--dir" in cmd:
            created.append(cmd[cmd.index("--dir") + 1])
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", tracking_run)
    github_api.download_security_findings(900)
    assert created, "subprocess.run must have been invoked with --dir"
    # The temp dir should NOT exist after the helper returns.
    for d in created:
        assert not Path(d).exists(), f"temp dir {d} must be cleaned up"


# ---------------------------------------------------------------------------
# artifact_max_age_days — env override
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.14")
def test_artifact_max_age_days_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHIPWRIGHT_GITHUB_ARTIFACT_MAX_AGE_DAYS", raising=False)
    assert github_api.artifact_max_age_days() == 14.0


@pytest.mark.covers("FR-01.14")
def test_artifact_max_age_days_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHIPWRIGHT_GITHUB_ARTIFACT_MAX_AGE_DAYS", "30")
    assert github_api.artifact_max_age_days() == 30.0


@pytest.mark.covers("FR-01.14")
def test_artifact_max_age_days_invalid_env_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for bad in ("not-a-number", "", "-1", "0"):
        monkeypatch.setenv("SHIPWRIGHT_GITHUB_ARTIFACT_MAX_AGE_DAYS", bad)
        assert github_api.artifact_max_age_days() == 14.0


# ---------------------------------------------------------------------------
# Round-trip against the real captured artifact
# ---------------------------------------------------------------------------

_ITERATE_RUNS = Path(__file__).resolve().parents[2] / ".shipwright" / "runs"
_CAPTURED_SAMPLE = (
    _ITERATE_RUNS / "iterate-2026-05-21-security-artifact-producer" / "findings_sample.json"
)


@pytest.mark.skipif(  # test-hygiene: allow-silent-skip: dev-local captured artifact (gitignored .shipwright/runs) — absent in CI, runs only in the main repo where the sample was recorded
    not _CAPTURED_SAMPLE.exists(),
    reason="captured sample artifact absent (run captured in main repo only)",
)
@pytest.mark.covers("FR-01.14")
def test_real_findings_sample_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Boundary probe: real findings.json captured from run 26192978904 round-trips.

    35 findings, mixed semgrep/trivy/gitleaks sources, real severity mix.
    """
    payload = _CAPTURED_SAMPLE.read_text(encoding="utf-8")
    monkeypatch.setattr(
        subprocess, "run",
        _stub_gh_run_download(success=True, file_contents=payload),
    )
    result = github_api.download_security_findings(900)
    assert result is not None
    assert isinstance(result, list)
    assert len(result) == 35  # matches the PR-comment count for run 26192978904
    severities = {f.get("severity") for f in result}
    assert severities <= {"critical", "high", "medium", "low", "info"}
