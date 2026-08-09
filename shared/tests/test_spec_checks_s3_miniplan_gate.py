"""S3's small+feature Mini-Plan gate (iterate-2026-08-09-compaction-state-audit).

Split out of test_spec_checks.py rather than appended there: that file
already carries a grandfathered bloat-baseline entry, so growing it further
would ratchet past its `current` ceiling.

iteration-planning.md's Mini-Plan Protocol triggers at FEATURE + small/medium
but CHANGE/BUG + medium only — so S3 (which gated purely on
`complexity >= medium`) silently skipped the one case where a `small`
iterate is now required to persist a mini-plan to disk (AC-1 of the same
iterate). See spec_checks.py's `_miniplan_required`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib import phase_quality as pq  # noqa: E402
from tools.verifiers import spec_checks as sc  # noqa: E402


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_iterate_history(proj: Path, entries: list[dict]) -> None:
    (proj / "shipwright_run_config.json").write_text(
        json.dumps({"iterate_history": entries}), encoding="utf-8",
    )


def test_s3_small_feature_warns_then_passes_with_miniplan(proj: Path):
    """FEATURE+small triggers the Mini-Plan Protocol; S3 must gate it too —
    WARN without a mini-plan on disk, PASS once one is written."""
    _write_iterate_history(proj, [{"run_id": "r1", "complexity": "small", "type": "feature"}])
    f = sc.check_s3_iterate_miniplan(proj, "r1")
    assert f["status"] == pq.STATUS_WARN and f.get("tier") == 2

    iter_dir = proj / ".shipwright" / "planning" / "iterate"
    iter_dir.mkdir(parents=True)
    (iter_dir / "2026-04-18-r1-miniplan.md").write_text("plan", encoding="utf-8")
    assert sc.check_s3_iterate_miniplan(proj, "r1")["status"] == pq.STATUS_PASS


def test_s3_still_skips_small_change_and_small_bug(proj: Path):
    """Only FEATURE runs the protocol at small; CHANGE/BUG stay medium-only."""
    for category in ("change", "bug"):
        _write_iterate_history(proj, [{"run_id": "r1", "complexity": "small", "type": category}])
        assert sc.check_s3_iterate_miniplan(proj, "r1")["status"] == pq.STATUS_SKIP
