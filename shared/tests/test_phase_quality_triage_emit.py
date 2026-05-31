"""Producer test: Phase-Quality Tier-1 FAILs collapse to ONE backlog action-unit.

Replaces the prior 1-FAIL-1-item contract. Unit-tests
``pq.emit_phase_quality_backlog`` directly (iterate spec
``2026-05-31-phasequality-triage-bundle``, AC-7..AC-11, AC-15, AC-16).
End-to-end hook schema compliance is covered by
``test_hook_output_schema_compliance.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import lib.phase_quality as pq  # noqa: E402
from triage import (  # noqa: E402
    append_triage_item_idempotent,
    mark_status,
    read_all_items,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


def _finding(code: str, status: str = "FAIL", *, tier: int | None = None,
             remediation: str = "do the thing") -> dict:
    f = {"id": code, "name": f"{code} check", "status": status,
         "evidence": "evidence text", "remediation": remediation}
    if tier is not None:
        f["tier"] = tier
    return f


def _engage(project: Path, phases: list[str], *, status: str = "complete") -> None:
    (project / "shipwright_run_config.json").write_text(
        json.dumps({"status": status}), encoding="utf-8")
    (project / "shipwright_events.jsonl").write_text(
        "\n".join(json.dumps({"type": "phase_completed", "source": p}) for p in phases),
        encoding="utf-8")


def _set_finding(project: Path, phase: str, fails: dict[str, list[dict]]) -> None:
    pq.write_finding_json(project, phase, run_id=phase, session_id="s", findings_by_category=fails)


def _open_backlog(project: Path) -> list[dict]:
    return [it for it in read_all_items(project)
            if it.get("source") == "phaseQuality"
            and it.get("status") == "triage"
            and str(it.get("dedupKey") or "").startswith(pq.BACKLOG_PREFIX)]


# --- AC-7: single rolling backlog item ----------------------------------

def test_single_backlog_item_for_many_fails(project: Path) -> None:
    _engage(project, ["design", "build"])
    _set_finding(project, "design", {"canon": [_finding("C1"), _finding("D1")]})
    _set_finding(project, "build", {"canon": [_finding("C4")]})

    stats = pq.emit_phase_quality_backlog(project, run_id="r1", commit="abc")
    assert stats["appended"] == 1
    assert stats["open_fails"] == 3

    items = _open_backlog(project)
    assert len(items) == 1
    it = items[0]
    assert it["dedupKey"].startswith(pq.BACKLOG_PREFIX)
    assert it["source"] == "phaseQuality"
    assert it["severity"] == "high"
    assert it["kind"] == "bug"
    assert it["status"] == "triage"


def test_backlog_body_lists_fails_and_launch_payload(project: Path) -> None:
    _engage(project, ["design"])
    _set_finding(project, "design", {"canon": [_finding("C1"), _finding("D1")]})
    pq.emit_phase_quality_backlog(project, run_id="r1", commit="abc")
    [it] = _open_backlog(project)
    # body lists every in-scope FAIL (AC-16 sig-derivable body)
    assert "design:C1" in it["detail"]
    assert "design:D1" in it["detail"]
    assert pq.DASHBOARD_REL in it["detail"]
    # launch payload = slash-command + dashboard pointer (normalized ids only)
    assert it["launchPayload"].startswith("/shipwright-compliance")
    assert pq.DASHBOARD_REL in it["launchPayload"]


# --- AC-8 / AC-15: idempotency + convergence ----------------------------

def test_idempotent_same_set_one_item(project: Path) -> None:
    _engage(project, ["iterate"])
    _set_finding(project, "iterate", {"canon": [_finding("C1")]})
    first = pq.emit_phase_quality_backlog(project, run_id="r1", commit="abc")
    second = pq.emit_phase_quality_backlog(project, run_id="r1", commit="def")
    assert first["appended"] == 1
    assert second["appended"] == 0  # dedup — open same-sig item suppresses
    assert second["dismissed"] == 0
    assert len(_open_backlog(project)) == 1


# --- AC-9: refresh on changed FAIL set ----------------------------------

def test_refresh_on_changed_set(project: Path) -> None:
    _engage(project, ["iterate"])
    _set_finding(project, "iterate", {"canon": [_finding("C1")]})
    pq.emit_phase_quality_backlog(project, run_id="r1", commit="abc")
    [old] = _open_backlog(project)

    # FAIL set changes → new signature → old dismissed, fresh appended.
    _set_finding(project, "iterate", {"canon": [_finding("C1"), _finding("C5")]})
    stats = pq.emit_phase_quality_backlog(project, run_id="r1", commit="abc")
    assert stats["dismissed"] == 1
    assert stats["appended"] == 1

    items = _open_backlog(project)
    assert len(items) == 1
    assert items[0]["dedupKey"] != old["dedupKey"]


# --- AC-10: auto-dismiss when resolved ----------------------------------

def test_auto_dismiss_when_resolved(project: Path) -> None:
    _engage(project, ["iterate"])
    _set_finding(project, "iterate", {"canon": [_finding("C1")]})
    pq.emit_phase_quality_backlog(project, run_id="r1", commit="abc")
    assert len(_open_backlog(project)) == 1

    # FAIL clears → backlog auto-dismissed, nothing re-appended.
    _set_finding(project, "iterate", {"canon": [_finding("C1", status="PASS")]})
    stats = pq.emit_phase_quality_backlog(project, run_id="r1", commit="abc")
    assert stats["appended"] == 0
    assert stats["dismissed"] == 1
    assert _open_backlog(project) == []


def test_no_fails_no_item_no_error(project: Path) -> None:
    _engage(project, ["iterate"])
    stats = pq.emit_phase_quality_backlog(project, run_id="r1", commit="abc")
    assert stats == {"appended": 0, "dismissed": 0, "open_fails": 0}
    assert read_all_items(project) == []


def test_unengaged_phase_emits_nothing(project: Path) -> None:
    # Layer 1: findings exist but the phase is not engaged → no backlog item.
    (project / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8")
    _set_finding(project, "deploy", {"canon": [_finding("C1")]})
    stats = pq.emit_phase_quality_backlog(project, run_id="r1", commit="abc")
    assert stats["open_fails"] == 0
    assert _open_backlog(project) == []


# --- AC-11: legacy per-code items untouched -----------------------------

def test_legacy_per_code_items_untouched(project: Path) -> None:
    # A pre-existing {phase}:{code} item must NOT be dismissed by the new
    # producer — only phaseQuality:backlog:* shapes are managed here.
    legacy_id = append_triage_item_idempotent(
        project, source="phaseQuality", severity="high", kind="bug",
        title="iterate C1: legacy", detail="d", dedup_key="iterate:C1", commit="x",
    )
    _engage(project, ["iterate"])
    _set_finding(project, "iterate", {"canon": [_finding("C1")]})
    pq.emit_phase_quality_backlog(project, run_id="r1", commit="abc")

    by_id = {it["id"]: it for it in read_all_items(project)}
    assert by_id[legacy_id]["status"] == "triage"  # legacy left alone
    assert len(_open_backlog(project)) == 1  # plus the new backlog item


def test_dismissed_backlog_can_refire(project: Path) -> None:
    _engage(project, ["iterate"])
    _set_finding(project, "iterate", {"canon": [_finding("C1")]})
    pq.emit_phase_quality_backlog(project, run_id="r1", commit="abc")
    [it] = _open_backlog(project)
    mark_status(project, it["id"], new_status="dismissed", by="user", reason="snooze")
    # Same set re-emits a fresh backlog item (dedup only suppresses open items).
    pq.emit_phase_quality_backlog(project, run_id="r2", commit="abc")
    assert len(_open_backlog(project)) == 1
