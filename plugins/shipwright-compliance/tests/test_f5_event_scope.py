"""Group-F ``F5`` arch-drift detective: event-ownership scoping.

Pins that ``_check_f5`` reconciles only decision-drops OWNED by this tree's
lineage — run_id present in this tree's committed ``shipwright_events.jsonl`` —
so cross-branch campaign sibling drops bleeding through the shared main-rooted
``decision-drops`` dir don't false-flag drift. Fail-open when no event log
exists (ownership unknowable) so a clean checkout keeps whole-set behavior.

Companion to ``TestF5ArchDrift`` in ``test_audit_groups_c_f.py`` (matching
oracle) and ``shared/tests/test_arch_drift_event_scope.py`` (shared helpers).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_f  # noqa: E402

_EVENT_FILE = "shipwright_events.jsonl"


def _seed_drop(root: Path, run_id: str, *, impact: str = "component") -> None:
    drops = root / ".shipwright" / "agent_docs" / "decision-drops"
    drops.mkdir(parents=True, exist_ok=True)
    (drops / f"{run_id}_001.json").write_text(
        json.dumps({"run_id": f"{run_id}_001", "architecture_impact": impact}),
        encoding="utf-8",
    )


def _seed_arch_md(root: Path, text: str = "## Architecture Updates\n") -> None:
    doc = root / ".shipwright" / "agent_docs"
    doc.mkdir(parents=True, exist_ok=True)
    (doc / "architecture.md").write_text(text, encoding="utf-8")


def _seed_events(root: Path, *adr_ids: str) -> None:
    lines = [
        json.dumps({"type": "work_completed", "source": "iterate", "adr_id": a})
        for a in adr_ids
    ]
    (root / _EVENT_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _f5(tmp_path: Path):
    findings = group_f.run(tmp_path, None, None)
    return next(f for f in findings if f.check_id == "F5")


def test_owned_undocumented_drop_fails(tmp_path: Path):
    # run_id IS in this tree's events.jsonl → owned → drift protection fires.
    _seed_drop(tmp_path, "iter-owned", impact="component")
    _seed_arch_md(tmp_path)  # undocumented
    _seed_events(tmp_path, "iter-owned_001")
    f5 = _f5(tmp_path)
    assert f5.status == "fail"
    assert "iter-owned_001" in str(f5.evidence)


def test_unowned_undocumented_drop_excluded_passes(tmp_path: Path):
    # run_id NOT in events.jsonl (a different run is recorded) → sibling bleed →
    # excluded from reconciliation → no false drift.
    _seed_drop(tmp_path, "iter-sibling", impact="component")
    _seed_arch_md(tmp_path)  # undocumented
    _seed_events(tmp_path, "iter-some-other-run_001")
    f5 = _f5(tmp_path)
    assert f5.status == "pass"
    assert "iter-sibling" not in str(f5.evidence)


def test_owned_documented_drop_passes(tmp_path: Path):
    _seed_drop(tmp_path, "iter-owned", impact="component")
    _seed_arch_md(tmp_path, "## Architecture Updates\n- iter-owned_001 (component)\n")
    _seed_events(tmp_path, "iter-owned_001")
    assert _f5(tmp_path).status == "pass"


def test_no_event_log_fails_open(tmp_path: Path):
    # No events.jsonl → ownership unknowable → whole-set fallback → an
    # undocumented drop still fails (never weaker than pre-scoping behavior).
    _seed_drop(tmp_path, "iter-x", impact="component")
    _seed_arch_md(tmp_path)  # undocumented
    f5 = _f5(tmp_path)
    assert f5.status == "fail"
    assert "iter-x_001" in str(f5.evidence)


def test_present_empty_event_log_excludes_all(tmp_path: Path):
    # events.jsonl exists but records no runs → strict scoping → the unowned
    # drop is excluded (an empty log is a real, if unusual, owned-set of none).
    _seed_drop(tmp_path, "iter-x", impact="component")
    _seed_arch_md(tmp_path)  # undocumented
    (tmp_path / _EVENT_FILE).write_text("", encoding="utf-8")
    assert _f5(tmp_path).status == "pass"
