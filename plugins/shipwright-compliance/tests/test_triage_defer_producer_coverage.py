"""This plugin's three auto-resolvers close a PARKED entry, not just an open one.

AC-26 for iterate-2026-08-01-triage-defer-lifecycle, compliance half. The
shared half is `shared/tests/test_triage_defer_producer_coverage.py`; the two
are split because these producers live in this plugin's own pytest root and
cannot be imported from there (ADR-044).

Why per-producer and not one representative: `expected_status` was widened at
all seven paths but `test_evidence`'s *read filter* was left at the literal
`"triage"`, so it dropped every parked entry before reaching the write. The
integration scenario could not see that — only a test per path can, and
`test_the_test_evidence_producer_closes_a_parked_entry` below is the one that
would have.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

_SHARED_SCRIPTS = Path(__file__).resolve().parents[3] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from scripts.audit import triage_bundle as audit_bundle  # noqa: E402
from scripts.lib import sbom_generator  # noqa: E402
from scripts.lib.test_evidence import emit_test_failure_triage  # noqa: E402

from triage import append_triage_item, read_all_items  # noqa: E402
from tools.triage_promote import defer  # noqa: E402

FUTURE = "2099-01-01"


def _parked(project: Path, *, source: str, dedup_key: str, **over) -> str:
    kw = dict(source=source, severity="medium", kind="compliance", title="t",
              detail="d", dedup_key=dedup_key)
    kw.update(over)
    item_id = append_triage_item(project, **kw)
    defer(project, item_id=item_id, reason="not now", revisit_at=FUTURE)
    assert _status(project, item_id) == "snoozed", "fixture did not park"
    return item_id


def _status(project: Path, item_id: str) -> str:
    return next(i["status"] for i in read_all_items(project)
                if i["id"] == item_id)


def test_the_compliance_backlog_closes_a_parked_entry(tmp_path: Path) -> None:
    item = _parked(tmp_path, source="compliance",
                   dedup_key=audit_bundle.BACKLOG_PREFIX + "abc123")
    # No findings → nothing is failing, so the backlog entry has cleared.
    result = audit_bundle.emit_compliance_backlog(
        tmp_path, SimpleNamespace(findings=[]), run_id=None, commit=None,
    )
    assert result["dismissed"] == 1
    assert _status(tmp_path, item) == "dismissed"


def test_the_sbom_producer_closes_a_parked_entry(tmp_path: Path) -> None:
    item = _parked(tmp_path, source="sbom", severity="low",
                   dedup_key="sbom:undeclared:gone/package.json")
    # No workspaces here → the producer's current key set is empty, so the
    # undeclared dependency this entry describes is gone.
    result = sbom_generator.emit_undeclared_triage(tmp_path)
    assert result["dismissed"] == 1
    assert _status(tmp_path, item) == "dismissed"


def test_the_test_evidence_producer_closes_a_parked_entry(
    tmp_path: Path,
) -> None:
    """THE regression test. This producer's read filter was the one left at
    `"triage"`, so before the fix it returned `dismissed == 0` here while every
    other test in the change stayed green."""
    log = tmp_path / "shipwright_events.jsonl"

    def seed(event_id: str, ts: str, passed: int) -> None:
        with log.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps({
                "v": 1, "id": event_id, "ts": ts, "type": "test_run",
                "trigger": "iterate",
                "layers": {"unit": {"passed": passed, "total": 2}},
            }) + "\n")

    # A red run creates the card; parking it is the operator's decision.
    seed("evt-red01", "2026-05-21T11:00:00Z", 1)
    emit_test_failure_triage(tmp_path)
    [item] = [i for i in read_all_items(tmp_path) if i.get("source") == "test-evidence"]
    defer(tmp_path, item_id=item["id"], reason="flaky, look after the refactor",
          revisit_at=FUTURE)
    assert _status(tmp_path, item["id"]) == "snoozed"

    # A later GREEN run of the same layer — the failure it describes is gone.
    seed("evt-green1", "2026-05-21T15:00:00Z", 2)
    result = emit_test_failure_triage(tmp_path)
    assert result["dismissed"] == 1
    assert _status(tmp_path, item["id"]) == "dismissed"
