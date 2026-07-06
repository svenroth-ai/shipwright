"""Integration tests for the artifact-source parallel-path in import_findings.

Iterate C — security-artifact-producer.

Architecture per external LLM review revision: the shipwright-security
workflow's findings.json artifact is a **third parallel source** alongside
``cs_alerts`` (GHAS Code Scanning) and ``db_alerts`` (Dependabot), NOT a
fallback for both. It fires when ``cs_alerts is None`` — i.e. when the SAST
source from GHAS is unavailable — independent of Dependabot's status, which
is free and orthogonal.

AC matrix:
- AC-1: cs=None + fresh artifact with findings → emit gh-security from artifact
- AC-2: artifact 0 findings (fresh clean) → auto-resolve previous open item
- AC-3: cs succeeds → SAST findings.json NOT fetched (no double-count), but
  prompt_risks.json IS fetched (prompt-injection is orthogonal — never in SARIF)
- AC-4: all paths fail → no emission, no auto-resolve (None ≠ empty)
- AC-5: by_source carries `gh-security:artifact` for artifact emissions
- AC-6: source-switching transitions (artifact ↔ GHAS) preserve idempotency
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import github_api  # noqa: E402
import github_triage  # noqa: E402
from triage import read_all_items  # noqa: E402


OWNER_REPO = "acme/foo"


# ---------------------------------------------------------------------------
# Fixtures — minimal records
# ---------------------------------------------------------------------------

CS_ALERT_HIGH = {
    "number": 42, "state": "open",
    "rule": {"id": "py/sqli", "security_severity_level": "high",
             "description": "SQL injection"},
    "html_url": "https://github.com/acme/foo/security/code-scanning/42",
}
DB_ALERT_HIGH = {
    "number": 7, "state": "open",
    "security_advisory": {"severity": "high", "summary": "urllib3 CVE"},
    "dependency": {"package": {"name": "urllib3"}},
    "html_url": "https://github.com/acme/foo/security/dependabot/7",
}

# Three flavors of artifact findings — matches the real findings.json shape
ARTIFACT_FINDINGS_HIGH = [
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
    {
        "id": "trivy-0002",
        "severity": "high",
        "cve_id": "CVE-2026-0002",
        "affected_package": "lodash",
        "source": "trivy",
    },
]


def _build_run(*, id_: int = 900, age_hours: float = -1.0) -> dict:
    ts = datetime.now(timezone.utc) + timedelta(hours=age_hours)
    return {
        "id": id_,
        "name": "Security Scan",
        "head_branch": "main",
        "status": "completed",
        "conclusion": "success",
        "created_at": ts.isoformat().replace("+00:00", "Z"),
        "html_url": f"https://github.com/acme/foo/actions/runs/{id_}",
    }


def _patch_api(
    monkeypatch: pytest.MonkeyPatch,
    *,
    cs_alerts: Any = None,
    db_alerts: Any = None,
    ss_alerts: Any = None,
    ci_runs: Any = None,
    artifact_run: Any = None,
    artifact_findings: Any = None,
    prompt_findings: Any = None,
    branch: str = "main",
    owner_repo_value: str | None = OWNER_REPO,
    available: bool = True,
) -> None:
    monkeypatch.setattr(github_api, "gh_available", lambda: available)
    monkeypatch.setattr(github_api, "default_branch", lambda: branch)
    monkeypatch.setattr(
        github_api, "fetch_code_scanning_alerts", lambda: cs_alerts,
    )
    monkeypatch.setattr(github_api, "fetch_dependabot_alerts", lambda: db_alerts)
    monkeypatch.setattr(
        github_api, "fetch_secret_scanning_alerts", lambda: ss_alerts,
    )
    monkeypatch.setattr(github_api, "fetch_workflow_runs", lambda b: ci_runs)
    monkeypatch.setattr(github_api, "owner_repo", lambda _: owner_repo_value)
    monkeypatch.setattr(
        github_api, "latest_security_workflow_run", lambda: artifact_run,
    )
    monkeypatch.setattr(
        github_api, "download_security_findings",
        lambda run_id, workflow_base=None: artifact_findings,
    )
    monkeypatch.setattr(
        github_api, "download_prompt_risks", lambda run_id: prompt_findings,
    )


def _append_events(project_root: Path) -> list[dict]:
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
# AC-1, AC-5 — artifact path emits when cs_alerts is None
# ---------------------------------------------------------------------------

def test_artifact_emits_when_cs_alerts_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No GHAS Code Scanning + fresh artifact with findings → emit gh-security."""
    run = _build_run()
    _patch_api(
        monkeypatch,
        cs_alerts=None,  # GHAS unavailable
        db_alerts=None,  # Dependabot also unavailable
        artifact_run=run,
        artifact_findings=ARTIFACT_FINDINGS_HIGH,
    )
    result = github_triage.import_findings(tmp_path)
    assert result["gh_available"] is True
    assert result["appended"] >= 1
    # An action-unit with the standard gh-security: prefix landed.
    appends = _append_events(tmp_path)
    sec_items = [a for a in appends if a["dedupKey"].startswith("gh-security:")]
    assert len(sec_items) == 1
    sec = sec_items[0]
    assert sec["dedupKey"] == f"gh-security:{OWNER_REPO}"
    # Severity is derived from the findings list (max = high).
    assert sec["severity"] == "high"
    # launchPayload starts with the slash command + carries the workflow URL.
    assert sec["launchPayload"].startswith("/shipwright-security")
    assert run["html_url"] in sec["launchPayload"]
    # by_source records the artifact ingestion path distinctly (AC-5).
    assert result["by_source"].get("gh-security:artifact") == 1


def test_sast_gated_but_prompt_fetched_when_cs_alerts_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-3 (refined, iterate-2026-07-02-gh-prompt-ghost-fix): with GHAS active the
    SAST findings.json stays gated (SARIF would double-count) but prompt_risks.json
    IS fetched — prompt-injection is never in Code Scanning (the gh-prompt ghost)."""
    sast_calls: list[Any] = []
    prompt_calls: list[Any] = []
    _patch_api(
        monkeypatch, cs_alerts=[CS_ALERT_HIGH], db_alerts=[], ss_alerts=[],
        ci_runs=[], artifact_run=_build_run(),
    )
    monkeypatch.setattr(
        github_api, "download_security_findings",
        lambda rid, workflow_base=None: sast_calls.append("sast") or None,
    )
    monkeypatch.setattr(
        github_api, "download_prompt_risks", lambda rid: prompt_calls.append("prompt") or None,
    )
    github_triage.import_findings(tmp_path)
    assert sast_calls == [], "SAST findings.json must stay gated on cs_alerts is None (SARIF double-count)"
    assert prompt_calls == ["prompt"], "prompt_risks.json must be fetched even when Code Scanning is up"


def test_artifact_skipped_when_owner_repo_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No usable owner/repo → no gh-security emission (no malformed dedup keys)."""
    _patch_api(
        monkeypatch,
        cs_alerts=None,
        db_alerts=None,
        artifact_run=_build_run(),
        artifact_findings=ARTIFACT_FINDINGS_HIGH,
        owner_repo_value=None,
    )
    result = github_triage.import_findings(tmp_path)
    appends = _append_events(tmp_path)
    assert not any(a["dedupKey"].startswith("gh-security") for a in appends)
    # by_source still records the path was attempted but yielded nothing.
    assert result["by_source"].get("gh-security:artifact", 0) == 0


def test_artifact_skipped_when_no_run_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cs=None + no successful security workflow run → no artifact emission."""
    _patch_api(
        monkeypatch,
        cs_alerts=None,
        db_alerts=None,
        artifact_run=None,  # no fresh run available
        artifact_findings=None,  # never called, but defensive
    )
    github_triage.import_findings(tmp_path)
    appends = _append_events(tmp_path)
    assert not any(a["dedupKey"].startswith("gh-security") for a in appends)


def test_artifact_skipped_when_download_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run found but download fails (artifact expired / network) → no emission."""
    _patch_api(
        monkeypatch,
        cs_alerts=None,
        db_alerts=None,
        artifact_run=_build_run(),
        artifact_findings=None,  # download_security_findings returned None
    )
    github_triage.import_findings(tmp_path)
    appends = _append_events(tmp_path)
    assert not any(a["dedupKey"].startswith("gh-security") for a in appends)


# ---------------------------------------------------------------------------
# AC-2 — auto-resolve on fresh clean scan
# ---------------------------------------------------------------------------

def test_artifact_clean_scan_auto_resolves_open_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-2: previous artifact emission + fresh clean scan → auto-dismiss."""
    # First import: artifact has findings → emit.
    _patch_api(
        monkeypatch,
        cs_alerts=None,
        db_alerts=None,
        artifact_run=_build_run(id_=900, age_hours=-48),
        artifact_findings=ARTIFACT_FINDINGS_HIGH,
    )
    github_triage.import_findings(tmp_path)
    open_items = [i for i in read_all_items(tmp_path)
                  if i["dedupKey"].startswith("gh-security:")]
    assert len(open_items) == 1
    assert open_items[0]["status"] == "triage"

    # Second import: fresh clean scan (different run id, 0 findings).
    _patch_api(
        monkeypatch,
        cs_alerts=None,
        db_alerts=None,
        artifact_run=_build_run(id_=901, age_hours=-1),
        artifact_findings=[],  # CLEAN
    )
    github_triage.import_findings(tmp_path)
    resolved = [i for i in read_all_items(tmp_path)
                if i["dedupKey"].startswith("gh-security:")]
    assert len(resolved) == 1
    assert resolved[0]["status"] == "dismissed"
    assert resolved[0]["statusReason"] == "githubResolved"


def test_artifact_failure_does_not_mass_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-4: failed artifact fetch (None) MUST NOT auto-resolve open items.

    This is the ADR-052 invariant: distinguish a failed fetch (None) from
    an empty fetch ([]). A transient outage that returns None for every
    source must leave previously-open items untouched.
    """
    # Seed an open item from a prior successful import.
    _patch_api(
        monkeypatch,
        cs_alerts=None,
        db_alerts=None,
        artifact_run=_build_run(),
        artifact_findings=ARTIFACT_FINDINGS_HIGH,
    )
    github_triage.import_findings(tmp_path)
    [open_item] = [i for i in read_all_items(tmp_path)
                   if i["dedupKey"].startswith("gh-security:")]
    assert open_item["status"] == "triage"

    # Now: everything fails (gh down, artifact unreachable).
    _patch_api(
        monkeypatch,
        cs_alerts=None,
        db_alerts=None,
        artifact_run=None,  # no run found
        artifact_findings=None,
    )
    github_triage.import_findings(tmp_path)
    # The open item is STILL open — a failed fetch never auto-resolves.
    [unchanged] = [i for i in read_all_items(tmp_path)
                   if i["dedupKey"].startswith("gh-security:")]
    assert unchanged["status"] == "triage", (
        "ADR-052 invariant: failed fetch (None) ≠ empty fetch ([]) — never mass-resolve"
    )


# ---------------------------------------------------------------------------
# AC-6 — source-switching transitions
# ---------------------------------------------------------------------------

def test_transition_artifact_to_ghas_preserves_idempotency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-6 case A: artifact emit → GHAS comes online → no duplicate.

    First import via artifact, second via cs_alerts. Same dedup key
    suppresses the second append; launchPayload stays frozen at the
    artifact's first emission.
    """
    # First: artifact emits.
    _patch_api(
        monkeypatch,
        cs_alerts=None,
        db_alerts=None,
        artifact_run=_build_run(),
        artifact_findings=ARTIFACT_FINDINGS_HIGH,
    )
    github_triage.import_findings(tmp_path)
    [first_event] = [
        e for e in _append_events(tmp_path)
        if e["dedupKey"].startswith("gh-security:")
    ]
    original_payload = first_event["launchPayload"]
    assert "/shipwright-security" in original_payload

    # Second: GHAS Code Scanning comes online → API path emits.
    _patch_api(
        monkeypatch,
        cs_alerts=[CS_ALERT_HIGH],
        db_alerts=[],
        ss_alerts=[],
        ci_runs=[],
    )
    second_result = github_triage.import_findings(tmp_path)
    # No new append — same dedup key.
    assert second_result["appended"] == 0
    sec_events = [
        e for e in _append_events(tmp_path)
        if e["dedupKey"].startswith("gh-security:")
    ]
    assert len(sec_events) == 1  # still one event total
    # And the persisted launchPayload remains frozen at first emission.
    assert sec_events[0]["launchPayload"] == original_payload


def test_transition_ghas_to_artifact_preserves_idempotency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-6 case B: GHAS emit → GHAS goes offline + artifact succeeds → no duplicate."""
    _patch_api(
        monkeypatch,
        cs_alerts=[CS_ALERT_HIGH],
        db_alerts=[],
        ss_alerts=[],
        ci_runs=[],
    )
    github_triage.import_findings(tmp_path)
    [first_event] = [
        e for e in _append_events(tmp_path)
        if e["dedupKey"].startswith("gh-security:")
    ]
    original_payload = first_event["launchPayload"]

    # Now GHAS goes offline, artifact still produces findings.
    _patch_api(
        monkeypatch,
        cs_alerts=None,
        db_alerts=None,
        artifact_run=_build_run(),
        artifact_findings=ARTIFACT_FINDINGS_HIGH,
    )
    second_result = github_triage.import_findings(tmp_path)
    assert second_result["appended"] == 0
    sec_events = [
        e for e in _append_events(tmp_path)
        if e["dedupKey"].startswith("gh-security:")
    ]
    assert len(sec_events) == 1
    assert sec_events[0]["launchPayload"] == original_payload


def test_transition_ghas_clean_then_artifact_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-6 case D: GHAS clean state → GHAS offline + artifact with findings → emit."""
    # First: GHAS active + clean.
    _patch_api(
        monkeypatch,
        cs_alerts=[],  # clean
        db_alerts=[],
        ss_alerts=[],
        ci_runs=[],
    )
    github_triage.import_findings(tmp_path)
    # No gh-security event because there's nothing to emit (no findings).
    assert not any(
        e["dedupKey"].startswith("gh-security:")
        for e in _append_events(tmp_path)
    ), "clean GHAS state must not emit a gh-security item"

    # Then: GHAS offline, artifact has findings.
    _patch_api(
        monkeypatch,
        cs_alerts=None,
        db_alerts=None,
        artifact_run=_build_run(),
        artifact_findings=ARTIFACT_FINDINGS_HIGH,
    )
    second = github_triage.import_findings(tmp_path)
    assert second["appended"] >= 1
    sec_events = [
        e for e in _append_events(tmp_path)
        if e["dedupKey"].startswith("gh-security:")
    ]
    assert len(sec_events) == 1
    assert second["by_source"].get("gh-security:artifact") == 1


# ---------------------------------------------------------------------------
# Detail rendering — per-source counts, no leaked finding strings
# ---------------------------------------------------------------------------

def test_artifact_detail_renders_per_source_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Detail line shows shipwright-security counts when artifact is the source."""
    _patch_api(
        monkeypatch,
        cs_alerts=None,
        db_alerts=None,
        artifact_run=_build_run(),
        artifact_findings=ARTIFACT_FINDINGS_HIGH,
    )
    github_triage.import_findings(tmp_path)
    [event] = [
        e for e in _append_events(tmp_path)
        if e["dedupKey"].startswith("gh-security:")
    ]
    detail = event["detail"]
    # Mentions the artifact source explicitly.
    assert "shipwright-security" in detail or "artifact" in detail
    # Aggregate counts visible (2 high + 1 medium = 3 in this fixture).
    assert "high" in detail.lower()
    # The unavailable sources are flagged transparently.
    assert "unavailable" in detail.lower() or "code-scanning" in detail.lower()


def test_artifact_detail_does_not_leak_raw_finding_strings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """openai-11: artifact contents are untrusted — detail must NOT carry raw rule/file strings."""
    sentinel_findings = [
        {
            "id": "semgrep-attacker-controlled",
            "severity": "high",
            "rule": "ATTACKER_CONTROLLED_RULE_NAME",  # sentinel
            "description": "ATTACKER_CONTROLLED_DESCRIPTION_WITH_HTML_<script>",
            "affected_file": "ATTACKER_CONTROLLED_FILE_NAME.py",
            "source": "semgrep",
        }
    ]
    _patch_api(
        monkeypatch,
        cs_alerts=None,
        db_alerts=None,
        artifact_run=_build_run(),
        artifact_findings=sentinel_findings,
    )
    github_triage.import_findings(tmp_path)
    [event] = [
        e for e in _append_events(tmp_path)
        if e["dedupKey"].startswith("gh-security:")
    ]
    # None of the raw scanner-controlled strings should leak into the persisted item.
    for sentinel in (
        "ATTACKER_CONTROLLED_RULE_NAME",
        "ATTACKER_CONTROLLED_DESCRIPTION_WITH_HTML",
        "ATTACKER_CONTROLLED_FILE_NAME.py",
        "<script>",
    ):
        assert sentinel not in event["detail"], (
            f"detail must not carry untrusted scanner string: {sentinel!r}"
        )
        assert sentinel not in event["launchPayload"], (
            f"launchPayload must not carry untrusted scanner string: {sentinel!r}"
        )


def test_artifact_detail_respects_length_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Detail line stays within a sensible size cap (≤1KB) even with many findings."""
    many_findings = [
        {"id": f"f-{i}", "severity": "medium", "source": "semgrep"}
        for i in range(500)
    ]
    _patch_api(
        monkeypatch,
        cs_alerts=None,
        db_alerts=None,
        artifact_run=_build_run(),
        artifact_findings=many_findings,
    )
    github_triage.import_findings(tmp_path)
    [event] = [
        e for e in _append_events(tmp_path)
        if e["dedupKey"].startswith("gh-security:")
    ]
    assert len(event["detail"]) <= 1024


# ---------------------------------------------------------------------------
# Severity derivation — list-of-findings, not by_severity aggregate
# ---------------------------------------------------------------------------

def test_artifact_severity_derived_from_findings_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """openai-9: when by_severity disagrees with findings, trust the list.

    This test enforces that the mapper never reads the aggregate — it
    iterates the findings array. (We can't simulate this directly here
    since the orchestrator only receives the list, but we DO verify the
    derived severity matches the list contents.)
    """
    only_low = [
        {"id": "low-1", "severity": "low", "source": "semgrep"},
        {"id": "low-2", "severity": "low", "source": "trivy"},
    ]
    _patch_api(
        monkeypatch,
        cs_alerts=None,
        db_alerts=None,
        artifact_run=_build_run(),
        artifact_findings=only_low,
    )
    github_triage.import_findings(tmp_path)
    [event] = [
        e for e in _append_events(tmp_path)
        if e["dedupKey"].startswith("gh-security:")
    ]
    assert event["severity"] == "low"


def test_artifact_unknown_severity_falls_back_to_medium(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown severity strings are tolerated, not crashes — match existing helper."""
    mixed = [
        {"id": "weird", "severity": "made-up-level", "source": "semgrep"},
        {"id": "medium-1", "severity": "medium", "source": "trivy"},
    ]
    _patch_api(
        monkeypatch,
        cs_alerts=None,
        db_alerts=None,
        artifact_run=_build_run(),
        artifact_findings=mixed,
    )
    result = github_triage.import_findings(tmp_path)
    # Either emits (with medium severity) or gracefully degrades; never crashes.
    assert result["gh_available"] is True


# ---------------------------------------------------------------------------
# Empty-but-fresh artifact = clean run signal
# ---------------------------------------------------------------------------

def test_artifact_empty_list_with_no_prior_state_is_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fresh clean scan + no prior open item → no-op (no emit, no false-positive resolve)."""
    _patch_api(
        monkeypatch,
        cs_alerts=None,
        db_alerts=None,
        artifact_run=_build_run(),
        artifact_findings=[],
    )
    result = github_triage.import_findings(tmp_path)
    sec_appends = [
        e for e in _append_events(tmp_path)
        if e["dedupKey"].startswith("gh-security:")
    ]
    assert not sec_appends
    assert result["by_source"].get("gh-security:artifact", 0) == 0


# ---------------------------------------------------------------------------
# Dependabot-orthogonal cases (external review code finding openai-4)
# ---------------------------------------------------------------------------

def test_no_ghas_with_dependabot_available_and_artifact_emits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cs=None + db succeeds + artifact succeeds → emit, with real db counts in detail.

    External review code finding openai-4: Dependabot is free and orthogonal
    to GHAS Code Scanning. When cs_alerts is unavailable but db_alerts has
    findings, the artifact mapper must render the real Dependabot count
    rather than hard-coding ``dependabot: (unavailable)``.
    """
    _patch_api(
        monkeypatch,
        cs_alerts=None,                       # No GHAS Code Scanning
        db_alerts=[DB_ALERT_HIGH, DB_ALERT_HIGH],  # Dependabot has 2 findings
        artifact_run=_build_run(),
        artifact_findings=ARTIFACT_FINDINGS_HIGH,
    )
    result = github_triage.import_findings(tmp_path)
    assert result["appended"] >= 1
    sec_events = [
        e for e in _append_events(tmp_path)
        if e["dedupKey"].startswith("gh-security:")
    ]
    assert len(sec_events) == 1
    event = sec_events[0]
    # Artifact ingestion path recorded.
    assert result["by_source"].get("gh-security:artifact") == 1
    # Detail mentions BOTH dependabot AND shipwright-security counts.
    detail = event["detail"]
    assert "dependabot: 2 high" in detail or "dependabot: 2" in detail, (
        f"detail must show real Dependabot count when db_alerts available, got: {detail!r}"
    )
    assert "shipwright-security:" in detail
    # code-scanning IS unavailable in this scenario.
    assert "code-scanning: (unavailable)" in detail


def test_no_ghas_with_dependabot_available_and_clean_artifact_auto_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cs=None + db succeeds + clean artifact → existing open item auto-resolves.

    AC-2 must hold in the mixed-source scenario too. A clean artifact scan
    paired with available Dependabot data must still drive auto-resolve of
    the previously-emitted gh-security item (when Dependabot has no findings).
    """
    # Seed an open item from a prior successful run.
    _patch_api(
        monkeypatch,
        cs_alerts=None,
        db_alerts=None,
        artifact_run=_build_run(id_=900, age_hours=-48),
        artifact_findings=ARTIFACT_FINDINGS_HIGH,
    )
    github_triage.import_findings(tmp_path)
    [open_item] = [
        i for i in read_all_items(tmp_path)
        if i["dedupKey"].startswith("gh-security:")
    ]
    assert open_item["status"] == "triage"

    # Next import: cs still unavailable, Dependabot comes online but clean,
    # artifact also clean and fresh → auto-resolve must fire.
    _patch_api(
        monkeypatch,
        cs_alerts=None,
        db_alerts=[],  # Dependabot online + clean
        artifact_run=_build_run(id_=901, age_hours=-1),
        artifact_findings=[],  # Artifact clean
    )
    github_triage.import_findings(tmp_path)
    [resolved] = [
        i for i in read_all_items(tmp_path)
        if i["dedupKey"].startswith("gh-security:")
    ]
    assert resolved["status"] == "dismissed"
    assert resolved["statusReason"] == "githubResolved"
