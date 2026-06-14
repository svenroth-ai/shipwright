"""Phase-quality rollups exclude degenerate sentinel-run snapshots.

Iterate ``2026-06-14-phasequality-sentinel-rollup-filter``. A finding JSON whose
``run_id`` is a sentinel (``""`` / ``"unknown"``) comes from an audit that ran
with NO resolvable run/session context (``resolve_run_id`` only yields
``"unknown"`` when session_id is empty AND there is no run-config run_id /
run_started event / loop var). By the project's own audit-time canon
(``unresolvable_run_id_skip`` / ``_skip_unengaged_fails``) such findings are "not
applicable" — so the rollup VIEWS (triage backlog, SessionStart digest,
dashboard, report) must exclude them, while raw ``load_findings`` + GC keep them.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import lib.phase_quality as pq  # noqa: E402
from lib.phase_quality._aggregates import LoadedFinding  # noqa: E402
from triage import read_all_items  # noqa: E402


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


def _finding(code: str, status: str = "FAIL") -> dict:
    return {"id": code, "name": f"{code} check", "status": status,
            "evidence": "evidence text", "remediation": "do the thing"}


def _set_finding(project: Path, phase: str, run_id: str, fails: dict[str, list[dict]],
                 *, session_id: str = "s") -> None:
    pq.write_finding_json(project, phase, run_id=run_id, session_id=session_id,
                          findings_by_category=fails)


def _engage(project: Path, phases: list[str]) -> None:
    (project / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8")
    (project / "shipwright_events.jsonl").write_text(
        "\n".join(json.dumps({"type": "phase_completed", "source": p}) for p in phases),
        encoding="utf-8")


def _open_backlog(project: Path) -> list[dict]:
    return [it for it in read_all_items(project)
            if it.get("source") == "phaseQuality"
            and it.get("status") == "triage"
            and str(it.get("dedupKey") or "").startswith(pq.BACKLOG_PREFIX)]


# --- AC-1: predicate + LoadedFinding.is_sentinel ------------------------

@pytest.mark.parametrize("run_id,expected", [
    ("", True), ("unknown", True), ("UNKNOWN", True), ("  unknown  ", True),
    (None, True),
    ("iterate-2026-06-14-x", False), ("sess-abc", False), ("run-1", False),
])
def test_is_sentinel_run_truth_table(run_id, expected) -> None:
    assert pq.is_sentinel_run(run_id) is expected


def test_sentinel_set_matches_iterate_run_id_guard() -> None:
    # Drift-pin (external-review #1): the rollup-layer sentinel set must stay
    # equivalent to the audit-time guard's set in tools/verifiers/_iterate_run_id,
    # so write-time SKIP and read-time exclusion never disagree.
    from lib.phase_quality._constants import RUN_ID_SENTINELS
    from tools.verifiers._iterate_run_id import _RUN_ID_SENTINELS
    assert RUN_ID_SENTINELS == _RUN_ID_SENTINELS


def test_loaded_finding_is_sentinel_property() -> None:
    sentinel = LoadedFinding(path=Path("x"), phase="iterate", run_id="unknown",
                             session_id="unknown", audited_at="t", source="iterate")
    real = LoadedFinding(path=Path("y"), phase="iterate", run_id="run-1",
                         session_id="s", audited_at="t", source="iterate")
    assert sentinel.is_sentinel is True
    assert real.is_sentinel is False


# --- AC-2 / AC-6: load_actionable_findings vs raw load_findings ---------

def test_load_actionable_filters_sentinel_preserves_raw(project: Path) -> None:
    _set_finding(project, "iterate", "unknown", {"canon": [_finding("S2")]},
                 session_id="unknown")
    _set_finding(project, "build", "run-1", {"canon": [_finding("C1")]})

    raw = pq.load_findings(project)
    actionable = pq.load_actionable_findings(project)

    assert {f.run_id for f in raw} == {"unknown", "run-1"}   # raw untouched (AC-6)
    assert {f.run_id for f in actionable} == {"run-1"}        # sentinel dropped (AC-2)


def test_load_actionable_preserves_newest_first_order(project: Path) -> None:
    _set_finding(project, "build", "run-old", {"canon": [_finding("C1", "PASS")]})
    time.sleep(0.01)
    _set_finding(project, "plan", "run-new", {"canon": [_finding("C1", "PASS")]})
    order = [f.run_id for f in pq.load_actionable_findings(project)]
    assert order == ["run-new", "run-old"]


def test_gc_still_archives_sentinel_by_mtime(project: Path) -> None:
    # AC-6: GC is mtime-based and sentinel-agnostic — an old sentinel snapshot
    # is still archived (raw lifecycle unchanged).
    p = pq.write_finding_json(project, "iterate", "unknown", "unknown",
                              {"canon": [_finding("S2")]})
    old = time.time() - (pq.GC_AGE_DAYS + 1) * 86400
    import os
    os.utime(p, (old, old))
    moved = pq.gc_old_findings(project)
    assert moved == 1
    assert not p.exists()


# --- AC-3 / AC-5: collect_in_scope_fails --------------------------------

def test_collect_drops_sentinel_only_fail(project: Path) -> None:
    _engage(project, ["iterate"])
    _set_finding(project, "iterate", "unknown", {"canon": [_finding("S2")]},
                 session_id="unknown")
    assert pq.collect_in_scope_fails(project) == []


def test_collect_keeps_non_sentinel_engaged_fail(project: Path) -> None:
    _engage(project, ["iterate"])
    _set_finding(project, "iterate", "run-1", {"canon": [_finding("C1")]})
    fails = pq.collect_in_scope_fails(project)
    assert [f["code"] for f in fails] == ["C1"]


def test_collect_sentinel_does_not_mask_older_real_fail(project: Path) -> None:
    # AC-5: a sentinel snapshot must not become the latest-per-phase and hide a
    # real engaged FAIL — once sentinels are filtered, the real one surfaces.
    _engage(project, ["iterate"])
    _set_finding(project, "iterate", "run-real", {"canon": [_finding("C1")]})
    time.sleep(0.01)
    _set_finding(project, "iterate", "unknown", {"canon": [_finding("C1", "PASS")]},
                 session_id="unknown")
    fails = pq.collect_in_scope_fails(project)
    assert [f["code"] for f in fails] == ["C1"]


# --- AC-7: end-to-end backlog emit --------------------------------------

def test_emit_backlog_ignores_sentinel_only(project: Path) -> None:
    _engage(project, ["iterate"])
    _set_finding(project, "iterate", "unknown", {"canon": [_finding("S2")]},
                 session_id="unknown")
    stats = pq.emit_phase_quality_backlog(project, run_id="r1", commit="abc")
    assert stats["open_fails"] == 0
    assert _open_backlog(project) == []


def test_emit_backlog_appends_for_non_sentinel(project: Path) -> None:
    _engage(project, ["iterate"])
    _set_finding(project, "iterate", "run-1", {"canon": [_finding("C1")]})
    stats = pq.emit_phase_quality_backlog(project, run_id="r1", commit="abc")
    assert stats["appended"] == 1
    assert len(_open_backlog(project)) == 1


# --- AC-4: renderers omit sentinel snapshots ----------------------------

def test_dashboard_omits_sentinel_only_phase(project: Path) -> None:
    (project / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    _set_finding(project, "adopt", "unknown", {"canon": [_finding("C1")]},
                 session_id="unknown")
    _set_finding(project, "build", "run-1", {"canon": [_finding("C1", "PASS")]})
    text = pq.write_quality_dashboard_file(project).read_text(encoding="utf-8")
    assert "build" in text
    assert "| adopt |" not in text  # sentinel-only phase → no row


def test_session_summary_omits_sentinel_fail(project: Path) -> None:
    (project / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    _set_finding(project, "iterate", "unknown", {"canon": [_finding("S2")]},
                 session_id="unknown")
    text = pq.rewrite_session_findings_summary(project).read_text(encoding="utf-8")
    assert "S2" not in text
    assert "open FAILs" not in text


def test_report_omits_sentinel_run(project: Path) -> None:
    (project / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    _set_finding(project, "iterate", "unknown", {"canon": [_finding("S2")]},
                 session_id="unknown")
    _set_finding(project, "build", "run-1", {"canon": [_finding("C1", "PASS")]})
    text = pq.rewrite_aggregated_report(project).read_text(encoding="utf-8")
    assert "run-1" in text
    assert "unknown" not in text  # sentinel run excluded from the report
