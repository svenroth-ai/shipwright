"""Group E tests (plan v7 Option Z, Step 7) — Sub-Iterate C.

Group E — compliance-doc content staleness. Renders each tracked
compliance doc in memory, strips the volatile ``Generated:`` header,
and byte-compares against on-disk. Stale → fail (or auto-fix when
``--fix`` is on, threaded through ``config["fix"]``).

These tests are hermetic: every fixture is a tmp_path with stub
renderers; no real ``ComplianceData`` collection, no real renderers.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import audit_staleness, group_e  # noqa: E402
from scripts.audit.audit_adapters import SOURCE_DETECTIVE_ONLY  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture renderers — each returns a fixed string for the given doc key
# ---------------------------------------------------------------------------


def _stub_renderers(content_by_key: dict[str, str]) -> dict[str, callable]:
    """Build a renderer map that returns a fixed string per doc key."""
    return {key: (lambda _data, c=content: c)
            for key, content in content_by_key.items()}


def _seed_doc(project_root: Path, rel_path: str, body: str) -> None:
    """Write ``body`` to ``project_root / rel_path``, creating parent dirs."""
    target = project_root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# Pass: every doc on disk matches its fresh regeneration
# ---------------------------------------------------------------------------


def test_e_passes_when_every_doc_matches_fresh(monkeypatch, tmp_path):
    fresh = {
        "rtm": "Generated: 2026-04-01\n# RTM\nbody-1\n",
        "test_evidence": "Generated: 2026-04-01\n# Tests\nbody-2\n",
        "change_history": "Generated: 2026-04-01\n# Changes\nbody-3\n",
        "sbom": "Generated: 2026-04-01\n# SBOM\nbody-4\n",
        "dashboard": "Generated: 2026-04-01\n# Dashboard\nbody-5\n",
    }
    monkeypatch.setattr(
        audit_staleness, "default_renderers",
        lambda: _stub_renderers(fresh),
    )

    # Seed identical content but with a different Generated header — the
    # normalize() pass should strip both and treat them as equal.
    on_disk = {k: v.replace("Generated: 2026-04-01", "Generated: 2026-04-30")
               for k, v in fresh.items()}
    for doc in audit_staleness.DOC_REGISTRY:
        _seed_doc(tmp_path, doc.rel_path, on_disk[doc.key])

    findings = group_e.run(tmp_path, {}, data=object())

    assert all(f.source == SOURCE_DETECTIVE_ONLY for f in findings)
    assert {f.check_id for f in findings} == {"E1", "E2", "E3", "E4", "E5"}
    assert all(f.status == "pass" for f in findings), \
        [f"{f.check_id}={f.status}: {f.detail}" for f in findings]


# ---------------------------------------------------------------------------
# Fail: stale doc surfaces with first-diff line + line delta
# ---------------------------------------------------------------------------


def test_e_flags_stale_doc(monkeypatch, tmp_path):
    fresh = {
        "rtm": "# RTM\nrow A\nrow B\nrow C\n",
        "test_evidence": "# Tests\n",
        "change_history": "# CH\n",
        "sbom": "# SBOM\n",
        "dashboard": "# DB\n",
    }
    monkeypatch.setattr(
        audit_staleness, "default_renderers",
        lambda: _stub_renderers(fresh),
    )

    # Seed RTM as stale (missing row C).
    for doc in audit_staleness.DOC_REGISTRY:
        body = fresh[doc.key]
        if doc.key == "rtm":
            body = "# RTM\nrow A\nrow B\n"
        _seed_doc(tmp_path, doc.rel_path, body)

    findings = group_e.run(tmp_path, {}, data=object())
    by_id = {f.check_id: f for f in findings}

    rtm = by_id["E1"]
    assert rtm.status == "fail"
    assert rtm.severity == "MEDIUM"
    assert rtm.suggested_iterate_cmd is not None
    # The other docs match — they should still pass.
    for cid in ("E2", "E3", "E4", "E5"):
        assert by_id[cid].status == "pass"


# ---------------------------------------------------------------------------
# --fix: stale doc gets regenerated and recorded as fixes_applied
# ---------------------------------------------------------------------------


def test_e_fix_rewrites_stale_doc_and_records_fix(monkeypatch, tmp_path):
    fresh = {
        "rtm": "# RTM\nrow A\nrow B\nrow C\n",
        "test_evidence": "# Tests\n",
        "change_history": "# CH\n",
        "sbom": "# SBOM\n",
        "dashboard": "# DB\n",
    }
    monkeypatch.setattr(
        audit_staleness, "default_renderers",
        lambda: _stub_renderers(fresh),
    )

    # Seed RTM stale.
    for doc in audit_staleness.DOC_REGISTRY:
        body = fresh[doc.key]
        if doc.key == "rtm":
            body = "# RTM\nrow A\n"
        _seed_doc(tmp_path, doc.rel_path, body)

    fixes: list[str] = []
    findings = group_e.run(
        tmp_path, {"fix": True, "fixes_applied": fixes}, data=object(),
    )
    by_id = {f.check_id: f for f in findings}

    # RTM transitioned to pass after auto-regeneration.
    assert by_id["E1"].status == "pass"
    assert "regenerated" in by_id["E1"].detail
    # File was actually rewritten.
    rtm_path = tmp_path / ".shipwright" / "compliance" / "traceability-matrix.md"
    assert rtm_path.read_text(encoding="utf-8") == fresh["rtm"]
    # And the relative path appears in the fixes_applied sink.
    assert ".shipwright/compliance/traceability-matrix.md" in fixes


# ---------------------------------------------------------------------------
# Missing on-disk file is itself "stale" (severity MEDIUM)
# ---------------------------------------------------------------------------


def test_e_flags_missing_doc_on_disk(monkeypatch, tmp_path):
    fresh = {k: f"# stub {k}\n" for k in (
        "rtm", "test_evidence", "change_history", "sbom", "dashboard",
    )}
    monkeypatch.setattr(
        audit_staleness, "default_renderers",
        lambda: _stub_renderers(fresh),
    )

    findings = group_e.run(tmp_path, {}, data=object())
    by_id = {f.check_id: f for f in findings}
    # All five docs are absent → all flagged stale.
    for cid in ("E1", "E2", "E3", "E4", "E5"):
        assert by_id[cid].status == "fail", by_id[cid].detail
        assert "missing" in by_id[cid].detail


# ---------------------------------------------------------------------------
# Render error is converted to a fail finding, not a crash
# ---------------------------------------------------------------------------


def test_e_render_failure_is_isolated(monkeypatch, tmp_path):
    def boom(_data):
        raise RuntimeError("renderer exploded")

    renderers = _stub_renderers({k: "x\n" for k in (
        "test_evidence", "change_history", "sbom", "dashboard",
    )})
    renderers["rtm"] = boom
    monkeypatch.setattr(
        audit_staleness, "default_renderers", lambda: renderers,
    )

    # Seed the four non-broken docs so they pass.
    for doc in audit_staleness.DOC_REGISTRY:
        if doc.key == "rtm":
            continue
        _seed_doc(tmp_path, doc.rel_path, "x\n")

    findings = group_e.run(tmp_path, {}, data=object())
    by_id = {f.check_id: f for f in findings}
    assert by_id["E1"].status == "fail"
    assert "RuntimeError" in by_id["E1"].detail
    # Other docs still ran.
    for cid in ("E2", "E3", "E4", "E5"):
        assert by_id[cid].status == "pass"


# ---------------------------------------------------------------------------
# data=None → single skip finding (cannot render without ComplianceData)
# ---------------------------------------------------------------------------


def test_e_skips_when_no_compliance_data(tmp_path):
    findings = group_e.run(tmp_path, {}, data=None)
    assert len(findings) == 1
    assert findings[0].status == "skip"
    assert findings[0].source == SOURCE_DETECTIVE_ONLY
    assert "ComplianceData" in findings[0].detail


# ---------------------------------------------------------------------------
# Integration: --fix flows from run_all(fix=True) into report.fixes_applied
# ---------------------------------------------------------------------------


def test_run_all_fix_true_threads_through_to_group_e_fixes_applied(
    monkeypatch, tmp_path,
):
    """End-to-end: ``audit_detector.run_all(..., fix=True)`` must
    populate ``cfg["fix"]`` and ``cfg["fixes_applied"]`` so Group E
    actually rewrites stale docs and records them on the AuditReport.

    Direct test of the wiring change in audit_detector.run_all (cfg copy
    + key injection). Without this test a regression in run_all could
    silently drop --fix while group_e tests stay green.
    """
    from scripts.audit import audit_detector
    from scripts.audit._registry import register_all

    fresh = {
        "rtm": "# RTM\nrow A\nrow B\nrow C\n",
        "test_evidence": "# Tests\n",
        "change_history": "# CH\n",
        "sbom": "# SBOM\n",
        "dashboard": "# DB\n",
    }
    monkeypatch.setattr(
        audit_staleness, "default_renderers",
        lambda: _stub_renderers(fresh),
    )
    # Force run_all to use our object as ComplianceData (skip the live
    # collector entirely).
    monkeypatch.setattr(
        audit_detector, "_load_compliance_data", lambda _r: object(),
    )

    # Seed RTM stale; everything else fresh-equal.
    for doc in audit_staleness.DOC_REGISTRY:
        body = fresh[doc.key]
        if doc.key == "rtm":
            body = "# RTM\nrow A\n"
        _seed_doc(tmp_path, doc.rel_path, body)

    register_all()
    report = audit_detector.run_all(
        tmp_path, only=["E"], run_gate=False, fix=True,
    )

    # The wiring populated fixes_applied.
    assert ".shipwright/compliance/traceability-matrix.md" in report.fixes_applied
    # And the file on disk now matches the fresh render.
    rtm_path = tmp_path / ".shipwright" / "compliance" / "traceability-matrix.md"
    assert rtm_path.read_text(encoding="utf-8") == fresh["rtm"]
    # E1 transitioned to pass after auto-regeneration.
    e1 = next(f for f in report.findings if f.check_id == "E1")
    assert e1.status == "pass"


def test_run_all_fix_false_does_not_rewrite_or_record(monkeypatch, tmp_path):
    """Symmetric guard: ``fix=False`` (the default) must NOT touch the
    file system and must leave fixes_applied empty even when docs are
    stale."""
    from scripts.audit import audit_detector
    from scripts.audit._registry import register_all

    fresh = {
        "rtm": "# RTM\nrow A\nrow B\n",
        "test_evidence": "# Tests\n",
        "change_history": "# CH\n",
        "sbom": "# SBOM\n",
        "dashboard": "# DB\n",
    }
    monkeypatch.setattr(
        audit_staleness, "default_renderers",
        lambda: _stub_renderers(fresh),
    )
    monkeypatch.setattr(
        audit_detector, "_load_compliance_data", lambda _r: object(),
    )

    for doc in audit_staleness.DOC_REGISTRY:
        body = fresh[doc.key]
        if doc.key == "rtm":
            body = "# RTM\n"  # stale
        _seed_doc(tmp_path, doc.rel_path, body)

    rtm_path = tmp_path / ".shipwright" / "compliance" / "traceability-matrix.md"
    before = rtm_path.read_text(encoding="utf-8")

    register_all()
    report = audit_detector.run_all(
        tmp_path, only=["E"], run_gate=False, fix=False,
    )

    assert report.fixes_applied == []
    assert rtm_path.read_text(encoding="utf-8") == before
    # E1 still shows the staleness as a fail.
    e1 = next(f for f in report.findings if f.check_id == "E1")
    assert e1.status == "fail"
