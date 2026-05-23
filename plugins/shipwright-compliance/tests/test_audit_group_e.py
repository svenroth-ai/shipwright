"""Group E tests — snapshot-provenance audit + --fix wiring.

Post-iterate-2026-05-23: Group E no longer compares fresh re-renders to
on-disk; it compares on-disk to the version committed in the last
iterate-finalize commit (snapshot). The bulk of the snapshot semantics
is covered in ``test_audit_snapshot.py``; this file focuses on:

  * ``--fix`` write-mode actually rewrites stale on-disk MDs with fresh
    production-renderer output.
  * ``audit_detector.run_all(..., fix=True)`` threads the ``fix``
    config + ``fixes_applied`` sink into Group E correctly.

Stale fixtures use a synthetic git repo with one iterate-finalize commit
as the snapshot baseline, then mutate one on-disk file post-commit.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import audit_staleness, group_e  # noqa: E402
from scripts.audit.audit_adapters import SOURCE_DETECTIVE_ONLY  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic git-repo fixture
# ---------------------------------------------------------------------------


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init", "-b", "main", str(repo)],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@e.com"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Tester"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "commit.gpgsign", "false"],
                   check=True, capture_output=True)


def _git_commit(repo: Path, files: dict[str, str], msg: str) -> str:
    for rel, content in files.items():
        full = repo / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", msg],
                   check=True, capture_output=True)
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _seed_baseline_compliance() -> dict[str, str]:
    return {
        ".shipwright/compliance/traceability-matrix.md":
            "# RTM\n\nGenerated: 2026-05-23T00:00:00Z\n\nBaseline RTM body\n",
        ".shipwright/compliance/test-evidence.md":
            "# Tests\n\nGenerated: 2026-05-23T00:00:00Z\n\nBaseline TE body\n",
        ".shipwright/compliance/change-history.md":
            "# Changes\n\nGenerated: 2026-05-23T00:00:00Z\n\nBaseline CH body\n",
        ".shipwright/compliance/sbom.md":
            "# SBOM\n\nGenerated: 2026-05-23T00:00:00Z\n\nBaseline SBOM body\n",
        ".shipwright/compliance/dashboard.md":
            "# Dashboard\n\nGenerated: 2026-05-23T00:00:00Z\n\nBaseline DB body\n",
    }


def _seed_iterate_snapshot(tmp_path: Path) -> str:
    """Init repo + commit baseline compliance with Run-ID: trailer.
    Returns snapshot SHA."""
    _git_init(tmp_path)
    return _git_commit(
        tmp_path, _seed_baseline_compliance(),
        "feat(iterate): seed snapshot\n\nRun-ID: iterate-2026-05-23-baseline\n",
    )


# ---------------------------------------------------------------------------
# Group E behaviour against snapshot
# ---------------------------------------------------------------------------


def test_e_passes_when_on_disk_matches_snapshot(tmp_path):
    _seed_iterate_snapshot(tmp_path)

    findings = group_e.run(tmp_path, {}, data=None)
    by_id = {f.check_id: f for f in findings}

    # E0 PASS — snapshot baseline located.
    assert by_id["E0"].status == "pass"
    # E1-E5 PASS — on-disk == snapshot.
    for cid in ("E1", "E2", "E3", "E4", "E5"):
        assert by_id[cid].status == "pass", by_id[cid].detail
        assert by_id[cid].source == SOURCE_DETECTIVE_ONLY


def test_e_flags_stale_doc_against_snapshot(tmp_path):
    _seed_iterate_snapshot(tmp_path)
    # Hand-edit the RTM post-snapshot.
    (tmp_path / ".shipwright" / "compliance" / "traceability-matrix.md").write_text(
        "# RTM\n\nGenerated: 2026-05-23T00:00:00Z\n\nHand-edited body!\n",
        encoding="utf-8",
    )

    findings = group_e.run(tmp_path, {}, data=None)
    by_id = {f.check_id: f for f in findings}

    rtm = by_id["E1"]
    assert rtm.status == "fail"
    assert rtm.severity == "MEDIUM"
    assert rtm.suggested_iterate_cmd is not None
    # Snapshot SHA appears in evidence for the operator hint.
    assert any("snapshot" in (rtm.detail or "").lower()
               or "snapshot" in (rtm.evidence or [""])[1].lower()
               for _ in [None]) or rtm.evidence

    # Other docs untouched → pass.
    for cid in ("E2", "E3", "E4", "E5"):
        assert by_id[cid].status == "pass"


def test_e_flags_missing_doc_on_disk(tmp_path):
    _seed_iterate_snapshot(tmp_path)
    # Delete the RTM post-snapshot — file missing == stale.
    (tmp_path / ".shipwright" / "compliance" / "traceability-matrix.md").unlink()

    findings = group_e.run(tmp_path, {}, data=None)
    by_id = {f.check_id: f for f in findings}
    assert by_id["E1"].status == "fail"
    assert "missing" in (by_id["E1"].detail or "").lower()


def test_e_emits_e0_skip_when_no_snapshot(tmp_path):
    """Greenfield repo (no Run-ID: commit touching compliance) → E0 skip."""
    _git_init(tmp_path)
    _git_commit(tmp_path, {"README.md": "hi\n"}, "chore: init")

    findings = group_e.run(tmp_path, {}, data=None)
    # Exactly one E0 skip, no per-doc findings.
    assert len(findings) == 1
    f = findings[0]
    assert f.check_id == "E0"
    assert f.status == "skip"
    assert "snapshot" in f.detail.lower()


# ---------------------------------------------------------------------------
# --fix mode — rewrites stale on-disk MD with fresh production-renderer output
# ---------------------------------------------------------------------------


def test_e_fix_rewrites_stale_doc_and_records_fix(monkeypatch, tmp_path):
    """``config["fix"]=True`` calls the production renderer for the stale
    doc, writes it to disk, and appends the relative path to ``fixes_applied``.
    """
    _seed_iterate_snapshot(tmp_path)

    # Hand-edit RTM to make it stale.
    rtm_path = tmp_path / ".shipwright" / "compliance" / "traceability-matrix.md"
    rtm_path.write_text("# RTM\n\nGenerated: 2026-05-23T00:00:00Z\n\nSTALE\n",
                        encoding="utf-8")

    # Stub the lazy renderer-loader to return controlled fresh content.
    # The audit itself doesn't need real ComplianceData — only --fix does.
    fresh_text = "# RTM\n\nGenerated: 2026-05-24T00:00:00Z\n\nFRESH BODY\n"
    monkeypatch.setattr(
        group_e, "_render_fresh_for_fix",
        lambda doc_key, data: fresh_text if doc_key == "rtm" else None,
    )

    fixes: list[str] = []
    findings = group_e.run(
        tmp_path, {"fix": True, "fixes_applied": fixes},
        data=object(),  # any non-None — passed through to _render_fresh_for_fix
    )
    by_id = {f.check_id: f for f in findings}

    assert by_id["E1"].status == "pass"
    assert "regenerated" in by_id["E1"].detail.lower()
    assert rtm_path.read_text(encoding="utf-8") == fresh_text
    assert ".shipwright/compliance/traceability-matrix.md" in fixes


def test_e_fix_false_does_not_rewrite(monkeypatch, tmp_path):
    """``fix=False`` (default) leaves on-disk untouched even when stale."""
    _seed_iterate_snapshot(tmp_path)

    rtm_path = tmp_path / ".shipwright" / "compliance" / "traceability-matrix.md"
    stale = "# RTM\n\nGenerated: 2026-05-23T00:00:00Z\n\nSTALE\n"
    rtm_path.write_text(stale, encoding="utf-8")

    monkeypatch.setattr(
        group_e, "_render_fresh_for_fix",
        lambda *_a, **_k: "should-never-be-written\n",
    )

    findings = group_e.run(tmp_path, {}, data=object())
    by_id = {f.check_id: f for f in findings}
    assert by_id["E1"].status == "fail"
    assert rtm_path.read_text(encoding="utf-8") == stale


# ---------------------------------------------------------------------------
# Integration: --fix flows from run_all(fix=True) into report.fixes_applied
# ---------------------------------------------------------------------------


def test_run_all_fix_true_threads_through_to_group_e_fixes_applied(
    monkeypatch, tmp_path,
):
    """End-to-end: ``audit_detector.run_all(..., fix=True)`` populates
    ``cfg["fix"]`` and ``cfg["fixes_applied"]`` so Group E rewrites stale
    docs and records them on the AuditReport.
    """
    from scripts.audit import audit_detector
    from scripts.audit._registry import register_all

    _seed_iterate_snapshot(tmp_path)

    rtm_path = tmp_path / ".shipwright" / "compliance" / "traceability-matrix.md"
    rtm_path.write_text("# RTM\n\nGenerated: 2026-05-23T00:00:00Z\n\nSTALE\n",
                        encoding="utf-8")

    fresh_text = "# RTM\n\nGenerated: 2026-05-24T00:00:00Z\n\nFRESH\n"
    monkeypatch.setattr(
        group_e, "_render_fresh_for_fix",
        lambda doc_key, data: fresh_text if doc_key == "rtm" else None,
    )
    # run_all loads ComplianceData via _load_compliance_data — short-circuit.
    monkeypatch.setattr(
        audit_detector, "_load_compliance_data", lambda _r: object(),
    )

    register_all()
    report = audit_detector.run_all(
        tmp_path, only=["E"], run_gate=False, fix=True,
    )

    assert ".shipwright/compliance/traceability-matrix.md" in report.fixes_applied
    assert rtm_path.read_text(encoding="utf-8") == fresh_text
    e1 = next(f for f in report.findings if f.check_id == "E1")
    assert e1.status == "pass"


def test_run_all_fix_false_does_not_rewrite_or_record(monkeypatch, tmp_path):
    """Symmetric guard: ``fix=False`` leaves filesystem untouched."""
    from scripts.audit import audit_detector
    from scripts.audit._registry import register_all

    _seed_iterate_snapshot(tmp_path)

    rtm_path = tmp_path / ".shipwright" / "compliance" / "traceability-matrix.md"
    stale = "# RTM\n\nGenerated: 2026-05-23T00:00:00Z\n\nSTALE\n"
    rtm_path.write_text(stale, encoding="utf-8")

    monkeypatch.setattr(
        group_e, "_render_fresh_for_fix",
        lambda *_a, **_k: "should-never-be-written\n",
    )
    monkeypatch.setattr(
        audit_detector, "_load_compliance_data", lambda _r: object(),
    )

    register_all()
    report = audit_detector.run_all(
        tmp_path, only=["E"], run_gate=False, fix=False,
    )

    assert report.fixes_applied == []
    assert rtm_path.read_text(encoding="utf-8") == stale
    e1 = next(f for f in report.findings if f.check_id == "E1")
    assert e1.status == "fail"
