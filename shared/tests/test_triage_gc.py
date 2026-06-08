"""Tests for triage_gc.py — machine-churn-only dismissed-pile compaction."""

from __future__ import annotations

import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent / "scripts" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import triage  # noqa: E402
import triage_gc  # noqa: E402


def _add(root: Path, *, title: str, dedup: str) -> str:
    return triage.append_triage_item(
        root, source="sbom", severity="low", kind="compliance",
        title=title, detail="d", dedup_key=dedup,
    )


def _dismiss(root: Path, item_id: str, *, by: str, reason: str) -> None:
    triage.mark_status(root, item_id, new_status="dismissed", by=by, reason=reason)


# --------------------------------------------------------------------------
# Predicate
# --------------------------------------------------------------------------

def test_is_machine_churn_requires_both_conditions():
    base = {"status": "dismissed", "statusBy": "sbomGenerator",
            "statusReason": "sbomResolved"}
    assert triage_gc.is_machine_churn(base)
    # Human dismisser, machine reason → kept.
    assert not triage_gc.is_machine_churn({**base, "statusBy": "user"})
    # Machine dismisser, human reason → kept.
    assert not triage_gc.is_machine_churn({**base, "statusReason": "fixed in PR #9"})
    # Not dismissed → kept.
    assert not triage_gc.is_machine_churn({**base, "status": "promoted"})
    # Reason that merely starts with a token (extra text) → kept (exact match).
    assert not triage_gc.is_machine_churn(
        {**base, "statusReason": "driftResolved (manual confirm)",
         "statusBy": "driftDetector"})


# --------------------------------------------------------------------------
# Plan (dry-run computation)
# --------------------------------------------------------------------------

def test_plan_drops_machine_keeps_human(tmp_path: Path):
    m = _add(tmp_path, title="machine", dedup="k1")
    _dismiss(tmp_path, m, by="auditDetector", reason="auditResolved")
    h = _add(tmp_path, title="human", dedup="k2")
    _dismiss(tmp_path, h, by="user", reason="superseded by P3.1")
    plan = triage_gc.plan_gc(tmp_path)
    assert plan["drop_ids"] == {m}
    assert plan["kept_count"] == 1
    assert plan["total"] == 2


def test_promoted_and_open_never_dropped(tmp_path: Path):
    p = _add(tmp_path, title="promoted", dedup="kp")
    triage.mark_status(tmp_path, p, new_status="promoted", by="auditDetector",
                       reason="auditResolved")
    _add(tmp_path, title="open", dedup="ko")  # stays triage
    plan = triage_gc.plan_gc(tmp_path)
    assert plan["drop_ids"] == set()
    assert plan["kept_count"] == 2


def test_machine_reason_but_human_dismisser_kept(tmp_path: Path):
    h = _add(tmp_path, title="h", dedup="k")
    _dismiss(tmp_path, h, by="cli", reason="sbomResolved")
    assert triage_gc.plan_gc(tmp_path)["drop_ids"] == set()


def test_producer_dismisser_but_human_reason_kept(tmp_path: Path):
    h = _add(tmp_path, title="h", dedup="k")
    _dismiss(tmp_path, h, by="sbomGenerator", reason="actually a real finding, keep")
    assert triage_gc.plan_gc(tmp_path)["drop_ids"] == set()


# --------------------------------------------------------------------------
# Apply (destructive rewrite)
# --------------------------------------------------------------------------

def test_dry_run_writes_nothing(tmp_path: Path):
    m = _add(tmp_path, title="m", dedup="k")
    _dismiss(tmp_path, m, by="sbomGenerator", reason="sbomResolved")
    path = triage._triage_path(tmp_path)
    before = path.read_bytes()
    rc = triage_gc.main(["--project-root", str(tmp_path)])  # no --apply
    assert rc == 0
    assert path.read_bytes() == before


def test_apply_compacts_and_backs_up(tmp_path: Path):
    m = _add(tmp_path, title="m", dedup="k1")
    _dismiss(tmp_path, m, by="sbomGenerator", reason="sbomResolved")
    keep = _add(tmp_path, title="keep", dedup="k2")
    _dismiss(tmp_path, keep, by="user", reason="resolved by PR #1")
    rc = triage_gc.main(["--project-root", str(tmp_path), "--apply"])
    assert rc == 0
    survivors = {i["id"] for i in triage.read_all_items(tmp_path)}
    assert survivors == {keep}
    # Backup exists and still contains the dropped id's data.
    bak = triage._triage_path(tmp_path).with_suffix(".jsonl.bak")
    assert bak.exists() and m in bak.read_text(encoding="utf-8")


def test_apply_drops_all_lines_of_multi_status_item(tmp_path: Path):
    m = _add(tmp_path, title="m", dedup="k")
    triage.mark_status(tmp_path, m, new_status="snoozed", by="user", reason="later")
    _dismiss(tmp_path, m, by="auditDetector", reason="auditResolved")
    triage_gc.main(["--project-root", str(tmp_path), "--apply"])
    raw = triage._iter_raw_lines(tmp_path)
    # Header only — every append/status line for m removed; no orphan status.
    assert [r for r in raw if r.get("id") == m] == []
    assert raw[0].get("schema") == "triage"
    assert triage.read_all_items(tmp_path) == []


def test_apply_idempotent(tmp_path: Path):
    m = _add(tmp_path, title="m", dedup="k")
    _dismiss(tmp_path, m, by="sbomGenerator", reason="sbomResolved")
    triage_gc.main(["--project-root", str(tmp_path), "--apply"])
    after_first = triage._triage_path(tmp_path).read_bytes()
    # Second apply: nothing droppable → no rewrite.
    rc = triage_gc.main(["--project-root", str(tmp_path), "--apply"])
    assert rc == 0
    assert triage._triage_path(tmp_path).read_bytes() == after_first


def test_report_survives_non_cp1252_title(tmp_path: Path, monkeypatch):
    """A title with a char the console encoding can't encode (e.g. →) must
    not crash the dry-run report (regression: live run on Windows cp1252).
    """
    import io

    class _CP1252Buf(io.StringIO):
        encoding = "cp1252"

    m = triage.append_triage_item(
        tmp_path, source="sbom", severity="low", kind="compliance",
        title="Hook fan-out → collapse to dispatchers", detail="d", dedup_key="k",
    )
    _dismiss(tmp_path, m, by="auditDetector", reason="auditResolved")
    buf = _CP1252Buf()
    monkeypatch.setattr(sys, "stdout", buf)
    rc = triage_gc.main(["--project-root", str(tmp_path)])
    monkeypatch.undo()
    assert rc == 0
    assert "?" in buf.getvalue()  # → replaced, no crash


def test_apply_preserves_header_and_validates(tmp_path: Path):
    for n in range(3):
        i = _add(tmp_path, title=f"m{n}", dedup=f"k{n}")
        _dismiss(tmp_path, i, by="auditDetector", reason="auditResolved")
    keep = _add(tmp_path, title="keep", dedup="kk")
    triage_gc.apply_gc(tmp_path, triage_gc.plan_gc(tmp_path)["drop_ids"])
    raw = triage._iter_raw_lines(tmp_path)
    assert raw[0].get("schema") == "triage"
    assert {i["id"] for i in triage.read_all_items(tmp_path)} == {keep}


def test_apply_refuses_on_malformed_line(tmp_path: Path):
    """Codex HIGH: a pre-existing corrupt line must ABORT the rewrite (the
    tolerant reader would otherwise silently compact it away — data loss)."""
    import pytest

    m = _add(tmp_path, title="m", dedup="k")
    _dismiss(tmp_path, m, by="sbomGenerator", reason="sbomResolved")
    path = triage._triage_path(tmp_path)
    with open(path, "a", encoding="utf-8") as fp:
        fp.write("NOT JSON\n")
    with pytest.raises(RuntimeError, match="malformed JSON"):
        triage_gc.apply_gc(tmp_path, triage_gc.plan_gc(tmp_path)["drop_ids"])
    # Live log untouched: corrupt line still present, nothing dropped.
    assert "NOT JSON" in path.read_text(encoding="utf-8")
    assert m in path.read_text(encoding="utf-8")


def test_apply_does_not_fold_outbox_into_tracked(tmp_path: Path):
    """D1 boundary guard: GC compacts the TRACKED store only — it must NOT
    fold OUTBOX lines into the tracked log.

    Regression risk: making ``_iter_raw_lines`` union-aware would otherwise
    make ``apply_gc`` rewrite the tracked log from the union, materializing the
    gitignored outbox buffer into the tracked log — re-introducing the exact
    main-tree drift D1 exists to prevent. GC operates on the durable store;
    the outbox is the D2 sweep's concern.
    """
    # One droppable tracked item + one OUTBOX-resident background item.
    m = _add(tmp_path, title="m", dedup="k1")
    _dismiss(tmp_path, m, by="sbomGenerator", reason="sbomResolved")
    keep = _add(tmp_path, title="keep", dedup="k2")  # tracked, open
    triage.append_triage_item(
        tmp_path, source="plugin-sync", severity="low", kind="maintenance",
        title="bg", detail="d", to_outbox=True,
    )
    outbox_before = triage._outbox_path(tmp_path).read_bytes()

    triage_gc.apply_gc(tmp_path, triage_gc.plan_gc(tmp_path)["drop_ids"])

    # Tracked log keeps only the open tracked item — the outbox item was NOT
    # folded in.
    tracked_text = triage._triage_path(tmp_path).read_text(encoding="utf-8")
    assert "plugin-sync" not in tracked_text, "outbox folded into tracked log"
    assert keep in tracked_text
    # Outbox is byte-unchanged by the tracked-log GC.
    assert triage._outbox_path(tmp_path).read_bytes() == outbox_before


def test_phasequality_and_testevidence_machine_churn_dropped(tmp_path: Path):
    """Codex MEDIUM: phaseQuality + testEvidence producer auto-resolves are
    machine-churn too (were missing from the dismisser/reason sets)."""
    pq = _add(tmp_path, title="pq", dedup="kpq")
    _dismiss(tmp_path, pq, by="phaseQualityBacklog", reason="phaseQualityResolved")
    te = _add(tmp_path, title="te", dedup="kte")
    _dismiss(tmp_path, te, by="testEvidence", reason="testEvidenceResolved")
    human = _add(tmp_path, title="h", dedup="kh")
    _dismiss(tmp_path, human, by="user", reason="phaseQualityResolved")  # human → kept
    assert triage_gc.plan_gc(tmp_path)["drop_ids"] == {pq, te}


def test_compliance_refreshed_machine_churn_dropped(tmp_path: Path):
    """``complianceBacklog`` emits BOTH ``complianceResolved`` (all findings
    cleared) AND ``complianceRefreshed`` (stale-signature rollup superseded by a
    fresh one — ``triage_bundle.emit_compliance_backlog``). The refresh token is
    pure machine-churn regenerated every compliance run, so it must be GC-able
    too (regression: it was missing from MACHINE_REASONS and accumulated as kept
    noise — found via webui trg-68bc2f62, by=complianceBacklog)."""
    resolved = _add(tmp_path, title="resolved", dedup="kr")
    _dismiss(tmp_path, resolved, by="complianceBacklog", reason="complianceResolved")
    refreshed = _add(tmp_path, title="refreshed", dedup="kf")
    _dismiss(tmp_path, refreshed, by="complianceBacklog", reason="complianceRefreshed")
    human = _add(tmp_path, title="h", dedup="khc")
    _dismiss(tmp_path, human, by="user", reason="complianceRefreshed")  # human → kept
    assert triage_gc.plan_gc(tmp_path)["drop_ids"] == {resolved, refreshed}
