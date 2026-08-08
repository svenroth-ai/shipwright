"""Legacy-drop quarantine integration tests for aggregate_decisions.aggregate().

Split out of test_aggregate_decisions.py (bloat-gate crossing) rather than
folded into test_decision_drop_legacy.py, which covers the LIB module's pure
functions — these exercise the wiring into ``aggregate()`` itself (doubt-
reviewer HIGH #3, iterate-2026-08-08-track-decision-drops).
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from tools.aggregate_decisions import aggregate
from tools.write_decision_drop import write_decision_drop


def _drop(tmp_path, run_id, **over):
    fields = dict(
        run_id=run_id,
        section=f"Iterate — change: {run_id}",
        title=f"Title {run_id}",
        context="ctx",
        decision="dec",
        consequences="cons",
    )
    fields.update(over)
    return write_decision_drop(tmp_path, **fields)


def _log(tmp_path):
    return tmp_path / ".shipwright" / "agent_docs" / "decision_log.md"


def _seed_log(tmp_path, content):
    log = _log(tmp_path)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(content, encoding="utf-8")


def _legacy_drop(tmp_path, run_id):
    """A drop whose FILE mtime predates the tracking cutoff — freshness is
    read from the filesystem, not the JSON `date` field (see
    lib/decision_drop_legacy.py's module docstring)."""
    drop = _drop(tmp_path, run_id)
    old_ts = datetime(2026, 1, 1).timestamp()
    os.utime(drop, (old_ts, old_ts))
    return drop


def test_legacy_drop_quarantined_not_aggregated(tmp_path):
    _seed_log(tmp_path, "# Decision Log\n")
    legacy = _legacy_drop(tmp_path, "iterate-20260101-old")
    result = aggregate(tmp_path)
    assert result["aggregated"] == 0
    assert result["adr_numbers"] == []
    assert result["legacy_quarantined"] == ["iterate-20260101-old_001.json"]
    assert not legacy.exists()  # moved out of decision-drops/
    quarantined = (
        tmp_path / ".shipwright" / "agent_docs"
        / "decision-drops-legacy-pending-scan" / "iterate-20260101-old_001.json"
    )
    assert quarantined.exists()
    assert "iterate-20260101-old" not in _log(tmp_path).read_text(encoding="utf-8")


def test_legacy_drop_dry_run_reports_without_moving(tmp_path):
    _seed_log(tmp_path, "# Decision Log\n")
    legacy = _legacy_drop(tmp_path, "iterate-20260101-old")
    result = aggregate(tmp_path, dry_run=True)
    assert result["legacy_quarantined"] == ["iterate-20260101-old_001.json"]
    assert legacy.exists()  # NOT moved under dry-run
    quarantine_dir = (
        tmp_path / ".shipwright" / "agent_docs" / "decision-drops-legacy-pending-scan"
    )
    assert not quarantine_dir.exists()


def test_mixed_fresh_and_legacy_batch(tmp_path):
    _seed_log(tmp_path, "# Decision Log\n")
    _legacy_drop(tmp_path, "iterate-20260101-old")
    _drop(tmp_path, "iterate-20260515-new")  # fresh (today's date)
    result = aggregate(tmp_path)
    assert result["aggregated"] == 1
    assert result["adr_numbers"] == [1]
    assert result["legacy_quarantined"] == ["iterate-20260101-old_001.json"]
    log_text = _log(tmp_path).read_text(encoding="utf-8")
    assert "iterate-20260515-new" in log_text
    assert "iterate-20260101-old" not in log_text


def test_malformed_drop_is_not_treated_as_legacy(tmp_path):
    """partition_by_freshness leaves a corrupt-JSON file in `fresh` (its
    filename still fails to parse for content, but mtime alone doesn't route
    it into quarantine) — the pre-existing malformed-drop error path in
    aggregate() still reports it, unaffected by the legacy split."""
    _seed_log(tmp_path, "# Decision Log\n")
    bad = (
        tmp_path / ".shipwright" / "agent_docs" / "decision-drops" / "bad_001.json"
    )
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("{not json", encoding="utf-8")
    result = aggregate(tmp_path)
    assert result["legacy_quarantined"] == []
    assert any("bad_001" in e for e in result["errors"])
    assert bad.exists()


def test_authoring_date_field_does_not_trigger_quarantine(tmp_path):
    """Regression pin for the design bug caught while building this fix: a
    drop written TODAY (fresh mtime) with a backdated narrative `date` field
    (write_decision_drop --date) must aggregate normally, not be quarantined."""
    _seed_log(tmp_path, "# Decision Log\n")
    drop = _drop(tmp_path, "iterate-20260515-backdated")
    data = json.loads(drop.read_text(encoding="utf-8"))
    data["date"] = "2020-01-01"
    drop.write_text(json.dumps(data), encoding="utf-8")
    result = aggregate(tmp_path)
    assert result["legacy_quarantined"] == []
    assert result["aggregated"] == 1
