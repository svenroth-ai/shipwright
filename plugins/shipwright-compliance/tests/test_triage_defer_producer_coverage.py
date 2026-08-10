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

Also covers `emit_compliance_backlog`'s `preserve_groups` merge-authority path
(P2.59, branch-feedback authority): a release-owned rolling card is amended in
place rather than dismissed as stale, and the AC4 coverage guarantee depends
on exactly one survivor card existing when more than one is open.
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


def _detail(project: Path, item_id: str) -> str:
    return next(i["detail"] for i in read_all_items(project)
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


def test_merge_preserves_open_release_owned_group_e_backlog(tmp_path: Path) -> None:
    item = audit_bundle.emit_compliance_backlog(
        tmp_path,
        SimpleNamespace(findings=[SimpleNamespace(
            status="fail", group="E", check_id="E1", name="release drift",
            severity="HIGH", detail="release-owned", suggested_iterate_cmd="",
        )]),
        run_id=None, commit=None,
    )
    assert item["appended"] == 1
    result = audit_bundle.emit_compliance_backlog(
        tmp_path,
        SimpleNamespace(findings=[SimpleNamespace(
            status="fail", group="D", check_id="D1", name="merge issue",
            severity="HIGH", detail="real non-E", suggested_iterate_cmd="",
        )]),
        run_id="delivery", commit="a" * 40, preserve_groups=frozenset({"E"}),
    )
    assert result["amended"] == 1
    assert result["appended"] == result["dismissed"] == 0
    [open_item] = [i for i in read_all_items(tmp_path) if i["status"] == "triage"]
    assert "E/E1" in open_item["detail"]
    assert "D/D1" in open_item["detail"]

def test_merge_amend_escalates_but_never_downgrades_release_card(tmp_path: Path) -> None:
    audit_bundle.emit_compliance_backlog(
        tmp_path, SimpleNamespace(findings=[SimpleNamespace(
            status="fail", group="E", check_id="E1", name="release drift",
            severity="HIGH", detail="release-owned", suggested_iterate_cmd="",
        )]), run_id=None, commit=None,
    )
    audit_bundle.emit_compliance_backlog(
        tmp_path, SimpleNamespace(findings=[SimpleNamespace(
            status="fail", group="D", check_id="D1", name="critical merge issue",
            severity="CRITICAL", detail="real non-E", suggested_iterate_cmd="",
        )]), run_id="delivery", commit="b" * 40, preserve_groups=frozenset({"E"}),
    )
    [item] = [i for i in read_all_items(tmp_path) if i["status"] == "triage"]
    assert item["severity"] == "critical"

def test_merge_never_dismisses_a_legacy_release_owned_group_e_item(tmp_path: Path) -> None:
    legacy_id = append_triage_item(
        tmp_path, source="compliance", severity="high", kind="compliance",
        title="E/E1: release drift", detail="historical free-text detail", dedup_key="E1",
    )
    result = audit_bundle.emit_compliance_backlog(
        tmp_path, SimpleNamespace(findings=[SimpleNamespace(
            status="fail", group="D", check_id="D1", name="merge issue",
            severity="HIGH", detail="real non-E", suggested_iterate_cmd="",
        )]), run_id="delivery", commit="c" * 40, preserve_groups=frozenset({"E"}),
    )
    assert result["dismissed"] == 0
    assert _status(tmp_path, legacy_id) == "triage"

def test_merge_preserving_group_e_retires_other_stale_backlog_cards(tmp_path: Path) -> None:
    protected = append_triage_item(
        tmp_path, source="compliance", severity="high", kind="compliance",
        title="Compliance: 1 open finding(s)", detail="- E/E1: release drift",
        dedup_key=audit_bundle.BACKLOG_PREFIX + "protected",
    )
    stale = append_triage_item(
        tmp_path, source="compliance", severity="high", kind="compliance",
        title="Compliance: 1 open finding(s)", detail="- D/D0: stale merge issue",
        dedup_key=audit_bundle.BACKLOG_PREFIX + "stale",
    )
    result = audit_bundle.emit_compliance_backlog(
        tmp_path, SimpleNamespace(findings=[SimpleNamespace(
            status="fail", group="D", check_id="D1", name="current merge issue",
            severity="HIGH", detail="current", suggested_iterate_cmd="",
        )]), run_id="delivery", commit="d" * 40, preserve_groups=frozenset({"E"}),
    )
    assert result["amended"] == 1 and result["dismissed"] == 1
    assert _status(tmp_path, protected) == "triage"
    assert _status(tmp_path, stale) == "dismissed"

def test_merge_with_two_protected_cards_amends_one_and_retires_the_other(tmp_path: Path) -> None:
    """Two open backlog cards both name a preserve_groups group (e.g. a prior
    run appended a second one before a fix). Exactly one must survive as the
    live rolling card — the other cannot be left open forever with no path
    back to `may_mirror` ever converging it."""
    first = append_triage_item(
        tmp_path, source="compliance", severity="high", kind="compliance",
        title="Compliance: 1 open finding(s)", detail="- E/E1: release drift",
        dedup_key=audit_bundle.BACKLOG_PREFIX + "aaa",
    )
    second = append_triage_item(
        tmp_path, source="compliance", severity="medium", kind="compliance",
        title="Compliance: 1 open finding(s)", detail="- E/E2: another release drift",
        dedup_key=audit_bundle.BACKLOG_PREFIX + "zzz",
    )
    survivor_id, duplicate_id = sorted([first, second])
    result = audit_bundle.emit_compliance_backlog(
        tmp_path, SimpleNamespace(findings=[SimpleNamespace(
            status="fail", group="D", check_id="D1", name="merge issue",
            severity="HIGH", detail="real non-E", suggested_iterate_cmd="",
        )]), run_id="delivery", commit="e" * 40, preserve_groups=frozenset({"E"}),
    )
    assert result["amended"] == 1 and result["dismissed"] == 1
    assert _status(tmp_path, survivor_id) == "triage"
    assert _status(tmp_path, duplicate_id) == "dismissed"
    [open_item] = [i for i in read_all_items(tmp_path) if i["status"] == "triage"]
    # Both preserved findings survive on the ONE remaining card — neither is lost.
    assert "E/E1" in open_item["detail"] and "E/E2" in open_item["detail"]

def test_regression_of_an_amended_signature_reopens_with_current_content(tmp_path: Path) -> None:
    """The exact scenario doubt review rounds 3 and 4 both turned on: a card
    is amended in place (merge, preserve_groups), later dismissed, then the
    SAME signature it was originally appended under regresses. It must both
    (a) actually reopen — not silently vanish, because `append_idempotent`
    no-ops on any matching dedupKey regardless of status, so exclusion from
    the reopen match with no re-append is a silent drop — and (b) show the
    CURRENT fails, not the stale amended detail from its amend history."""
    e1 = SimpleNamespace(status="fail", group="E", check_id="E1", name="release drift",
                         severity="HIGH", detail="release-owned", suggested_iterate_cmd="")
    d1 = SimpleNamespace(status="fail", group="D", check_id="D1", name="merge issue",
                         severity="HIGH", detail="real non-E", suggested_iterate_cmd="")

    # 1: first append, under signature(E/E1) — no card exists yet.
    first = audit_bundle.emit_compliance_backlog(
        tmp_path, SimpleNamespace(findings=[e1]), run_id=None, commit=None,
        preserve_groups=frozenset({"E"}),
    )
    assert first["appended"] == 1
    [card] = [i for i in read_all_items(tmp_path) if i["status"] == "triage"]

    # 2: amended in place — a real non-E finding joins the card; dedupKey
    # stays signature(E/E1), detail now covers both.
    amended = audit_bundle.emit_compliance_backlog(
        tmp_path, SimpleNamespace(findings=[d1]), run_id="delivery", commit="f" * 40,
        preserve_groups=frozenset({"E"}),
    )
    assert amended["amended"] == 1
    assert "D/D1" in _detail(tmp_path, card["id"])

    # 3: release — everything clears; the amended card is dismissed
    # (`complianceResolved`), carrying its amend history (`amendedBy` set).
    cleared = audit_bundle.emit_compliance_backlog(
        tmp_path, SimpleNamespace(findings=[]), run_id="release", commit="g" * 40,
    )
    assert cleared["dismissed"] == 1
    assert _status(tmp_path, card["id"]) == "dismissed"

    # 4: E/E1 regresses ALONE — same signature as step 1. Must reopen the
    # SAME card (not silently drop it), and its content must match what's
    # failing NOW, not the stale "D/D1 + E/E1" from step 2's amend.
    regressed = audit_bundle.emit_compliance_backlog(
        tmp_path, SimpleNamespace(findings=[e1]), run_id="delivery-2", commit="h" * 40,
        preserve_groups=frozenset({"E"}),
    )
    assert regressed["appended"] == 0  # reopened the existing card, not a fresh one
    assert _status(tmp_path, card["id"]) == "triage"
    detail = _detail(tmp_path, card["id"])
    assert "E/E1" in detail
    assert "D/D1" not in detail
