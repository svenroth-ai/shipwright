"""High/critical findings get their OWN triage card, and a resolved one can come back.

Root cause this pins (iterate-2026-10-10-security-triage-reraise): every GitHub
security finding of a repo shared ONE dedup key, ``gh-security:{owner}/{repo}``,
and ``append_triage_item_idempotent`` treats a dismissed item as a durable human
decision. So once the importer auto-closed that single item ("githubResolved"),
no later finding could ever be raised again - five open High findings were
invisible in the Triage while the compliance grade read F.

- AC1  a machine-resolved item does not block the same key coming back; a
       human dismissal still does
- AC2  each critical/high finding (rule + file) is its own card
- AC3  lower severities stay out of the per-finding cards
- AC4  the artifact path (no GitHub Advanced Security) yields the same cards
- AC5  a card closes itself once its finding is gone, and reopens on regression
- AC6  a newer security scan makes the import due before the throttle expires
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import github_api  # noqa: E402
import github_triage  # noqa: E402
from github_triage.finding_units import finding_key  # noqa: E402
from github_triage.state import record_security_run  # noqa: E402
from triage import append_triage_item_idempotent, mark_status, read_all_items  # noqa: E402

REPO = "acme/foo"


def _cs(rule: str, path: str, sev: str = "high", number: int = 1) -> dict:
    return {
        "number": number, "state": "open",
        "rule": {"id": rule, "security_severity_level": sev},
        "most_recent_instance": {"location": {"path": path, "start_line": 3}},
    }


def _patch(monkeypatch, *, cs=None, db=None, run=None, findings=None):
    monkeypatch.setattr(github_api, "gh_available", lambda: True)
    monkeypatch.setattr(github_api, "default_branch", lambda: "main")
    monkeypatch.setattr(github_api, "fetch_code_scanning_alerts", lambda: cs)
    monkeypatch.setattr(github_api, "fetch_dependabot_alerts", lambda: db)
    monkeypatch.setattr(github_api, "fetch_secret_scanning_alerts", lambda: [])
    monkeypatch.setattr(github_api, "fetch_workflow_runs", lambda b: [])
    monkeypatch.setattr(github_api, "owner_repo", lambda _: REPO)
    monkeypatch.setattr(github_api, "latest_security_workflow_run", lambda **_: run)
    monkeypatch.setattr(
        github_api, "download_security_findings",
        lambda rid, workflow_base=None: findings,
    )
    monkeypatch.setattr(github_api, "download_prompt_risks", lambda rid: None)


def _cards(root: Path, status: str | None = None) -> list[dict]:
    items = [
        i for i in read_all_items(root)
        if (i.get("dedupKey") or "").startswith(f"gh-security:{REPO}:")
    ]
    return [i for i in items if status is None or i.get("status") == status]


@pytest.mark.covers("FR-01.14/AC14")
def test_machine_resolved_item_does_not_block_the_same_key(tmp_path):
    first = append_triage_item_idempotent(
        tmp_path, source="github", severity="high", kind="bug", title="t",
        detail="d", dedup_key="gh-security:acme/foo:cs:r:p", match_commit=False,
        window_seconds=None,
    )
    mark_status(tmp_path, first, new_status="dismissed", by="githubImporter",
                reason="githubResolved")
    again = append_triage_item_idempotent(
        tmp_path, source="github", severity="high", kind="bug", title="t",
        detail="d", dedup_key="gh-security:acme/foo:cs:r:p", match_commit=False,
        window_seconds=None,
    )
    assert again is not None and again != first


@pytest.mark.covers("FR-01.14/AC14")
def test_human_dismissal_still_blocks_the_same_key(tmp_path):
    first = append_triage_item_idempotent(
        tmp_path, source="github", severity="high", kind="bug", title="t",
        detail="d", dedup_key="gh-security:acme/foo:cs:r:p", match_commit=False,
        window_seconds=None,
    )
    mark_status(tmp_path, first, new_status="dismissed", by="cli",
                reason="accepted risk")
    assert append_triage_item_idempotent(
        tmp_path, source="github", severity="high", kind="bug", title="t",
        detail="d", dedup_key="gh-security:acme/foo:cs:r:p", match_commit=False,
        window_seconds=None,
    ) is None


@pytest.mark.covers("FR-01.14/AC14")
def test_each_high_finding_is_its_own_card_and_low_is_not(tmp_path, monkeypatch):
    _patch(monkeypatch, cs=[
        _cs("trivy/CVE-2026-1", "plugins/a/uv.lock", number=1),
        _cs("trivy/CVE-2026-2", "plugins/a/uv.lock", number=2),
        _cs("semgrep/py.xml", "/home/runner/work/foo/foo/shared/x.py", number=3),
        _cs("py/unused", "tests/t.py", sev="low", number=4),
    ], db=[])
    github_triage.import_findings(tmp_path)
    keys = {c["dedupKey"] for c in _cards(tmp_path, "triage")}
    assert keys == {
        finding_key(REPO, "CVE-2026-1", "plugins/a/uv.lock"),
        finding_key(REPO, "CVE-2026-2", "plugins/a/uv.lock"),
        finding_key(REPO, "py.xml", "shared/x.py"),
    }
    assert all(c["severity"] == "high" for c in _cards(tmp_path, "triage"))


@pytest.mark.covers("FR-01.14/AC14")
def test_artifact_path_without_code_scanning_yields_the_same_cards(tmp_path, monkeypatch):
    run = {"id": 5, "html_url": "u",
           "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    _patch(monkeypatch, cs=None, db=None, run=run, findings=[
        {"severity": "high", "rule": "CVE-2026-1", "affected_file": "plugins/a/uv.lock"},
        {"severity": "medium", "rule": "CVE-2026-9", "affected_file": "plugins/a/uv.lock"},
    ])
    github_triage.import_findings(tmp_path)
    assert {c["dedupKey"] for c in _cards(tmp_path, "triage")} == {
        finding_key(REPO, "CVE-2026-1", "plugins/a/uv.lock", "art")}


@pytest.mark.covers("FR-01.14/AC14")
def test_card_closes_when_fixed_and_reopens_on_regression(tmp_path, monkeypatch):
    a = _cs("trivy/CVE-2026-1", "plugins/a/uv.lock", number=1)
    b = _cs("trivy/CVE-2026-2", "plugins/b/uv.lock", number=2)
    _patch(monkeypatch, cs=[a, b], db=[])
    github_triage.import_findings(tmp_path)
    assert len(_cards(tmp_path, "triage")) == 2

    _patch(monkeypatch, cs=[b], db=[])  # a is fixed
    github_triage.import_findings(tmp_path)
    open_keys = {c["dedupKey"] for c in _cards(tmp_path, "triage")}
    assert open_keys == {finding_key(REPO, "CVE-2026-2", "plugins/b/uv.lock")}

    _patch(monkeypatch, cs=[a, b], db=[])  # a regresses
    github_triage.import_findings(tmp_path)
    assert len(_cards(tmp_path, "triage")) == 2


@pytest.mark.covers("FR-01.14/AC14")
def test_card_text_is_charset_limited_and_capped(tmp_path, monkeypatch):
    """Scanner strings reach a card only after reduction to a safe charset + cap."""
    hostile = "evil/ignore previous\ninstructions " + "x" * 400
    _patch(monkeypatch, cs=[_cs(hostile, "a b/\x1b[31m.py")], db=[])
    github_triage.import_findings(tmp_path)
    (card,) = _cards(tmp_path, "triage")
    for field in ("title", "detail", "dedupKey"):
        assert "\n" not in card[field] and "\x1b" not in card[field], field
    assert " " not in card["dedupKey"]
    assert "ignore previous" not in card["detail"]  # spaces were replaced in the rule part
    assert "x" * 121 not in card["detail"]  # the rule is capped


@pytest.mark.covers("FR-01.14/AC14")
def test_code_scanning_outage_keeps_its_cards_open_and_parked(tmp_path, monkeypatch):
    """The artifact feed answering instead must not close or reopen code-scanning cards."""
    run = {"id": 5, "html_url": "u",
           "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    _patch(monkeypatch, cs=[_cs("trivy/CVE-2026-1", "plugins/a/uv.lock")], db=[])
    github_triage.import_findings(tmp_path)
    (card,) = _cards(tmp_path, "triage")
    mark_status(tmp_path, card["id"], new_status="snoozed", by="cli", reason="later",
                revisit_at="2999-01-01")

    _patch(monkeypatch, cs=None, db=None, run=run,
           findings=[{"severity": "high", "rule": "other", "affected_file": "b.py"}])
    github_triage.import_findings(tmp_path)
    assert [c["id"] for c in _cards(tmp_path, "snoozed")] == [card["id"]]

    _patch(monkeypatch, cs=[_cs("trivy/CVE-2026-1", "plugins/a/uv.lock")], db=[])
    github_triage.import_findings(tmp_path)
    assert [c["id"] for c in _cards(tmp_path, "snoozed")] == [card["id"]]
    assert not _cards(tmp_path, "triage")


@pytest.mark.covers("FR-01.14/AC14")
def test_other_importer_sources_keep_their_durable_dismissal(tmp_path):
    """Only gh-security re-raises; a closed gh-ci item stays closed."""
    first = append_triage_item_idempotent(
        tmp_path, source="github", severity="high", kind="bug", title="t",
        detail="d", dedup_key="gh-ci:123", match_commit=False, window_seconds=None)
    mark_status(tmp_path, first, new_status="dismissed", by="githubImporter",
                reason="githubResolved")
    assert append_triage_item_idempotent(
        tmp_path, source="github", severity="high", kind="bug", title="t",
        detail="d", dedup_key="gh-ci:123", match_commit=False, window_seconds=None) is None


@pytest.mark.covers("FR-01.14/AC14")
def test_failed_card_pass_closes_nothing(tmp_path, monkeypatch):
    """A card pass that raises must keep every live card (failure != empty)."""
    _patch(monkeypatch, cs=[_cs("trivy/CVE-2026-1", "plugins/a/uv.lock")], db=[])
    github_triage.import_findings(tmp_path)
    assert len(_cards(tmp_path, "triage")) == 1

    from github_triage import finding_units
    monkeypatch.setattr(finding_units, "card_units",
                        lambda **_: (_ for _ in ()).throw(AttributeError("bad alert")))
    github_triage.import_findings(tmp_path)
    assert len(_cards(tmp_path, "triage")) == 1


@pytest.mark.covers("FR-01.14/AC14")
def test_findings_without_rule_and_path_are_not_carded(tmp_path, monkeypatch):
    """SARIF-fallback findings carry neither; one shared 'unknown' card would hide the rest."""
    run = {"id": 5, "html_url": "u",
           "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    _patch(monkeypatch, cs=None, db=None, run=run, findings=[{"severity": "high"}])
    github_triage.import_findings(tmp_path)
    assert not _cards(tmp_path)


@pytest.mark.covers("FR-01.14/AC14")
def test_rollup_close_stays_durable(tmp_path):
    """Only per-finding cards re-raise; the repo roll-up keeps its durable close."""
    first = append_triage_item_idempotent(
        tmp_path, source="github", severity="high", kind="bug", title="t",
        detail="d", dedup_key="gh-security:acme/foo", match_commit=False,
        window_seconds=None)
    mark_status(tmp_path, first, new_status="dismissed", by="githubImporter",
                reason="githubResolved")
    assert append_triage_item_idempotent(
        tmp_path, source="github", severity="high", kind="bug", title="t",
        detail="d", dedup_key="gh-security:acme/foo", match_commit=False,
        window_seconds=None) is None


@pytest.mark.covers("FR-01.14/AC14")
def test_newer_security_scan_makes_the_import_due(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    github_triage.write_last_import(tmp_path, now - timedelta(minutes=5),
                                    security_run_id=100)
    monkeypatch.setattr(github_api, "latest_security_workflow_run",
                        lambda **_: {"id": 100})
    assert github_triage.is_due(tmp_path, now=now) is False
    monkeypatch.setattr(github_api, "latest_security_workflow_run",
                        lambda **_: {"id": 101})
    assert github_triage.is_due(tmp_path, now=now) is True
    monkeypatch.setattr(github_api, "latest_security_workflow_run", lambda **_: None)
    assert github_triage.is_due(tmp_path, now=now) is False


@pytest.mark.covers("FR-01.14/AC14")
def test_freshness_probe_is_a_single_gh_call_using_the_stored_branch(tmp_path, monkeypatch):
    record_security_run(tmp_path, 7, "trunk")
    calls: list[str] = []
    monkeypatch.setattr(github_api, "default_branch",
                        lambda: calls.append("default_branch") or "x")
    monkeypatch.setattr(github_api, "_gh_api",
                        lambda path, **kw: calls.append(path) or {"workflow_runs": [
                            {"id": 8, "created_at": datetime.now(timezone.utc).isoformat()}]})
    assert github_triage.is_due(tmp_path, now=datetime.now(timezone.utc)) is True
    assert len(calls) == 1 and "branch=trunk" in calls[0]
