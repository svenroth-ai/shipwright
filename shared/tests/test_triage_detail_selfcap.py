"""A pathologically large finding set truncates instead of vanishing.

iterate-2026-08-13-triage-detail-selfcap. ``append_triage_item`` (and its
idempotent/amend siblings) now enforce a shared 6000-char ``detail`` cap
(iterate-2026-08-13-triage-detail-maxlength). Four producers built ``detail``
via an unbounded loop/join with no self-cap of their own, unlike
``sbom_generator.py``/``test_evidence.py``/``journey_coverage.py``/
``warning_followups.py``/``security_card.py``: a large-enough finding set at
any of them raised ``ValueError`` inside a best-effort ``except Exception``
and the finding was silently DROPPED rather than recorded truncated.

Two of the four sites live under ``shared/scripts`` and share this test root
(ADR-044): ``lib.phase_quality._triage_bundle._build_detail`` and
``artifact_sync._emit_drift_to_triage``. The compliance and security sites
each get their own file in their own plugin's pytest root —
``plugins/shipwright-compliance/tests/test_triage_bundle_detail_cap.py`` and
``plugins/shipwright-security/tests/test_security_triage_emit_detail_cap.py``.

A NEW file rather than an addition to ``test_drift_triage_emit.py`` (422
lines) or ``test_triage_defer_producer_coverage.py``: appending to either
would ratchet the bloat baseline.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

import artifact_sync  # noqa: E402
from lib.phase_quality import _triage_bundle as phase_quality_bundle  # noqa: E402
from triage import read_all_items  # noqa: E402


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")  # F7: marker req'd
    return tmp_path


def _fail(i: int) -> dict:
    return {"phase": "test", "code": f"T{i}", "name": "x" * 60, "remediation": "y" * 60}


# --- lib.phase_quality._triage_bundle._build_detail ------------------------

def test_phase_quality_build_detail_truncates_when_over_cap() -> None:
    detail = phase_quality_bundle._build_detail([_fail(i) for i in range(500)])
    assert len(detail) == phase_quality_bundle._DETAIL_MAX_LEN
    assert detail.endswith("…")


def test_phase_quality_build_detail_untouched_under_cap() -> None:
    detail = phase_quality_bundle._build_detail([_fail(1)])
    assert not detail.endswith("…")
    assert "T1" in detail


def _pad_phase_quality_to(target: int) -> list[dict]:
    """One fail whose rendered detail is exactly ``target`` characters.

    Measured against a 1-char ``name`` rather than an empty one, so the
    arithmetic isn't thrown off by any fallback-on-falsy behavior.
    """
    probe = phase_quality_bundle._build_detail(
        [{"phase": "t", "code": "c", "name": "n", "remediation": ""}])
    pad_len = target - len(probe) + 1
    return [{"phase": "t", "code": "c", "name": "n" * pad_len, "remediation": ""}]


@pytest.mark.parametrize(
    "length,expect_truncated",
    [
        (phase_quality_bundle._DETAIL_MAX_LEN - 1, False),
        (phase_quality_bundle._DETAIL_MAX_LEN, False),
        (phase_quality_bundle._DETAIL_MAX_LEN + 1, True),
    ],
)
def test_phase_quality_build_detail_boundary(length: int, expect_truncated: bool) -> None:
    detail = phase_quality_bundle._build_detail(_pad_phase_quality_to(length))
    assert detail.endswith("…") is expect_truncated
    assert len(detail) == min(length, phase_quality_bundle._DETAIL_MAX_LEN)


def test_phase_quality_build_detail_feeds_a_write_that_no_longer_raises(
    project: Path,
) -> None:
    """The regression itself: a fail set large enough to blow past
    append_triage_item's 6000-char cap used to raise ValueError inside the
    best-effort wrapper and drop the item. It must now append, truncated."""
    from triage import append_triage_item_idempotent

    fails = [_fail(i) for i in range(500)]
    new_id = append_triage_item_idempotent(
        project, source="phaseQuality", severity="medium", kind="improvement",
        title="t", detail=phase_quality_bundle._build_detail(fails),
        dedup_key="phaseQuality:backlog:huge", match_commit=False, window_seconds=None,
    )
    assert new_id is not None
    [item] = read_all_items(project)
    assert len(item["detail"]) <= 6000


# --- artifact_sync._emit_drift_to_triage ------------------------------------
# Plain-slice cap (no ellipsis) here — mirrors journey_coverage.py's/
# warning_followups.py's `[:_DETAIL_CAP]` variant rather than security_card.py's
# truncate+ellipsis, to add the cap in this already-300-line file at net-zero
# LOC (bloat gate: the file had zero headroom).

def test_artifact_sync_detail_is_capped_when_lists_are_huge(project: Path) -> None:
    affected = [{
        "pattern": "src/**",
        "changed_files": [f"src/file_{i}.ts" for i in range(500)],
        "artifacts": [f"docs/artifact_{i}.md" for i in range(500)],
        "frs": [f"FR-{i:03d}" for i in range(500)],
        "category": "auth",
    }]
    appended = artifact_sync._emit_drift_to_triage(project, affected)
    assert appended == 1
    [item] = read_all_items(project)
    assert len(item["detail"]) == artifact_sync._DETAIL_MAX_LEN
    assert len(item["detail"]) <= 6000


def _pad_artifact_sync_to(target: int) -> list[dict]:
    """One mapping whose rendered detail is exactly ``target`` characters."""
    probe_detail = "changed_files: c | affected_artifacts: n/a | affected_FRs: n/a"
    pad_len = target - len(probe_detail) + 1
    return [{
        "pattern": "p", "changed_files": ["c" * pad_len], "artifacts": [],
        "frs": [], "category": "x",
    }]


@pytest.mark.parametrize(
    "length,expect_truncated",
    [
        (artifact_sync._DETAIL_MAX_LEN - 1, False),
        (artifact_sync._DETAIL_MAX_LEN, False),
        (artifact_sync._DETAIL_MAX_LEN + 1, True),
    ],
)
def test_artifact_sync_detail_boundary(
    project: Path, length: int, expect_truncated: bool,
) -> None:
    artifact_sync._emit_drift_to_triage(project, _pad_artifact_sync_to(length))
    [item] = read_all_items(project)
    assert len(item["detail"]) == min(length, artifact_sync._DETAIL_MAX_LEN)


def test_artifact_sync_detail_untouched_for_an_ordinary_mapping(project: Path) -> None:
    affected = [{
        "pattern": "src/auth/*.ts",
        "changed_files": ["src/auth/login.ts"],
        "artifacts": ["docs/auth.md"],
        "frs": ["FR-01.02"],
        "category": "auth",
    }]
    artifact_sync._emit_drift_to_triage(project, affected)
    [item] = read_all_items(project)
    assert item["detail"] == (
        "changed_files: src/auth/login.ts | "
        "affected_artifacts: docs/auth.md | affected_FRs: FR-01.02"
    )
