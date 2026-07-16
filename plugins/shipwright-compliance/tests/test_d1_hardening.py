"""D1 hardening (traceability campaign TT2 AC4) — a covering event must be *tested*.

RED before TT2 (old D1 counted any ``affected_frs`` mention as coverage 'independent of
whether a test ran', §2 false-green); green after. Kept out of the baseline-capped
``test_audit_groups_a_d.py``. The test-link proof is intentionally SEPARATE (D-layer,
provenance-gated) — see ``test_group_d_traceability.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from scripts.audit import group_d  # noqa: E402


def _events_file(tmp_path, rows):
    (tmp_path / "shipwright_events.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _spec_file(tmp_path, fr_id, priority="Must"):
    p = tmp_path / ".shipwright" / "planning" / "01-foo" / "spec.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "# Spec\n\n| FR | Description | Priority |\n| --- | --- | --- |\n"
        f"| {fr_id} | x | {priority} |\n", encoding="utf-8")


def test_d1_hardened_untested_event_no_longer_covers(tmp_path):
    """AC4 regression — an FR whose ONLY covering event recorded ``tests_total:0``
    (a docs/refactor 0/0 commit) is NO LONGER covered."""
    _spec_file(tmp_path, "FR-01.01")
    _events_file(tmp_path, [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "affected_frs": ["FR-01.01"], "tests": {"passed": 0, "total": 0}},
    ])
    d1 = next(f for f in group_d.run(tmp_path, {}, None) if f.check_id == "D1")
    assert d1.status == "fail", d1.detail
    assert d1.severity == "HIGH"  # Must-priority uncovered
    assert "FR-01.01" in d1.detail


def test_d1_legacy_fr_no_manifest_covers_on_event_proof_alone(tmp_path):
    """Complement — with NO manifest (pre-rollout / legacy), a genuine tested event
    still covers on the event proof alone; the link proof bites only explicit FRs, so
    the pre-TT8 monorepo does not avalanche (no false-red)."""
    _spec_file(tmp_path, "FR-01.01")
    _events_file(tmp_path, [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "affected_frs": ["FR-01.01"], "tests": {"passed": 5, "total": 5}},
    ])
    d1 = next(f for f in group_d.run(tmp_path, {}, None) if f.check_id == "D1")
    assert d1.status == "pass", d1.detail


# ---------------------------------------------------------------------------
# D1 link-proof (Spec §5) — an explicit FR needs a tested event AND a real link
# ---------------------------------------------------------------------------


def _node(fr_id, *, source, tests):
    return {
        "id": fr_id, "spec_path": "s", "title": fr_id, "priority": "Must",
        "status": "active", "required_layers": ["unit"],
        "required_layers_source": source, "tests": tests, "coverage": {"unit": "MISSING"},
    }


def _write_manifest(tmp_path, nodes):
    p = tmp_path / ".shipwright" / "compliance" / "test-traceability.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "schema_version": 2, "collector_version": "t", "generated_at": "t",
        "source_commit": "x", "spec_hash": "h",
        "requirements": {f"01-foo::{n['id']}": n for n in nodes},
        "orphans": [], "invalid_tags": [], "invalid_layers": [], "untagged_tests": [],
    }), encoding="utf-8")


def _link():
    return {"unit": [{"id": "t", "path": "tests/t.py::t", "layer": "unit",
                      "status": "enabled", "executed": "pass", "tag_source": "pytest_marker"}]}


def _tested_event(fr):
    return [{"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
             "affected_frs": [fr], "tests": {"passed": 5, "total": 5}}]


def test_d1_explicit_fr_tested_event_but_no_link_is_uncovered(tmp_path):
    """The two-proof requirement — an EXPLICIT (post-rollout) FR with a tested event but
    NO manifest test link is NOT covered (the former false-green a bare mention gave)."""
    _spec_file(tmp_path, "FR-01.01")
    _events_file(tmp_path, _tested_event("FR-01.01"))
    _write_manifest(tmp_path, [_node("FR-01.01", source="explicit", tests={})])
    d1 = next(f for f in group_d.run(tmp_path, {}, None) if f.check_id == "D1")
    assert d1.status == "fail", d1.detail
    assert "FR-01.01" in d1.detail


def test_d1_explicit_fr_with_tested_event_and_link_is_covered(tmp_path):
    _spec_file(tmp_path, "FR-01.01")
    _events_file(tmp_path, _tested_event("FR-01.01"))
    _write_manifest(tmp_path, [_node("FR-01.01", source="explicit", tests=_link())])
    d1 = next(f for f in group_d.run(tmp_path, {}, None) if f.check_id == "D1")
    assert d1.status == "pass", d1.detail


def test_d1_link_for_a_different_fr_does_not_cover_this_fr(tmp_path):
    """The proofs never collapse — a real link for FR-02.01 cannot satisfy FR-01.01's
    link proof (each FR is keyed to its OWN links)."""
    _spec_file(tmp_path, "FR-01.01")
    _events_file(tmp_path, _tested_event("FR-01.01"))
    _write_manifest(tmp_path, [
        _node("FR-01.01", source="explicit", tests={}),      # explicit, no link
        _node("FR-02.01", source="explicit", tests=_link()),  # link belongs to a DIFFERENT FR
    ])
    d1 = next(f for f in group_d.run(tmp_path, {}, None) if f.check_id == "D1")
    assert d1.status == "fail", d1.detail
    assert "FR-01.01" in d1.detail
