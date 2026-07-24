"""Core-contract tests for ``finalize_security_compliance.py`` (Step 7.5).

Skip semantics + the snapshot-qualifying commit. The write-set / clean-tree
regression suite (iterate-2026-07-24-finalizer-events-staging) lives in the
sibling ``test_finalize_write_set.py``; shared helpers + fixtures live in
``_finalize_helpers.py`` / ``conftest.py``.

Contract:

- **Pipeline mode only.** Standalone (no ``shipwright_project_config.json``)
  → no-op.
- **CI / non-interactive skip.** ``CI`` / ``SHIPWRIGHT_NON_INTERACTIVE`` set
  → no-op (CI commits would race with the pipeline).
- **Safe to re-run.** Each run records one post-scan snapshot and NEVER leaves
  the tree dirty; a genuinely empty regen (no MD change AND no event) is a
  clean no-op.
- **Snapshot-qualifying commit.** The commit body carries
  ``Run-ID: security-<scan_id>`` so the audit's ``find_snapshot_commit``
  recognizes it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from _finalize_helpers import (
    faithful_regen,
    head,
    load_finalize_module,
    porcelain,
)


def test_finalize_skips_in_standalone_mode(standalone_project, monkeypatch):
    """No `shipwright_project_config.json` → helper exits without committing."""
    finalize = load_finalize_module().finalize
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_NON_INTERACTIVE", raising=False)

    head_before = head(standalone_project)
    result = finalize(standalone_project, scan_id="scan-001")
    assert result["committed"] is False
    assert "standalone" in result["reason"].lower() or "pipeline" in result["reason"].lower()
    assert head(standalone_project) == head_before


def test_finalize_skips_in_ci(pipeline_project, monkeypatch):
    """CI env var set → no commit (CI doesn't drive interactive flow)."""
    finalize = load_finalize_module().finalize
    monkeypatch.setenv("CI", "true")
    monkeypatch.delenv("SHIPWRIGHT_NON_INTERACTIVE", raising=False)

    head_before = head(pipeline_project)
    result = finalize(pipeline_project, scan_id="scan-002")
    assert result["committed"] is False
    assert "ci" in result["reason"].lower()
    assert head(pipeline_project) == head_before


def test_finalize_no_commit_when_nothing_written(pipeline_project, monkeypatch):
    """Genuinely empty regen (no MD, no event, no config) → clean no-op."""
    fsc = load_finalize_module()
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_NON_INTERACTIVE", raising=False)
    monkeypatch.setattr(fsc, "_run_update_compliance",
                        lambda project_root: {"updated_reports": []})

    head_before = head(pipeline_project)
    result = fsc.finalize(pipeline_project, scan_id="scan-noop-003")
    assert result["committed"] is False
    assert "unchanged" in result["reason"].lower() or "no diff" in result["reason"].lower()
    assert head(pipeline_project) == head_before
    assert porcelain(pipeline_project) == ""


def test_finalize_creates_snapshot_commit_with_runid_trailer(
    pipeline_project, monkeypatch,
):
    """Commit subject + Run-ID trailer follow the documented convention."""
    fsc = load_finalize_module()
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_NON_INTERACTIVE", raising=False)
    monkeypatch.setattr(fsc, "_run_update_compliance", faithful_regen())

    result = fsc.finalize(pipeline_project, scan_id="scan-abc-004")
    assert result["committed"] is True
    assert result.get("commit_sha")
    assert porcelain(pipeline_project) == ""

    body = subprocess.run(
        ["git", "-C", str(pipeline_project), "log", "-1", "--format=%B"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert "Run-ID: security-scan-abc-004" in body, (
        f"missing Run-ID trailer; got: {body!r}"
    )
    subject = subprocess.run(
        ["git", "-C", str(pipeline_project), "log", "-1", "--format=%s"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert subject.startswith("chore(compliance):")


def test_finalize_commit_qualifies_as_snapshot(pipeline_project, monkeypatch):
    """The helper-created commit must be picked up by find_snapshot_commit."""
    fsc = load_finalize_module()
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_NON_INTERACTIVE", raising=False)
    monkeypatch.setattr(fsc, "_run_update_compliance", faithful_regen())

    result = fsc.finalize(pipeline_project, scan_id="scan-snapshot-005")
    assert result["committed"] is True

    # Load audit_staleness via importlib so we don't fight the security
    # plugin's conftest, which has already pinned the `scripts` namespace.
    import importlib.util
    compliance_audit_path = (
        Path(__file__).resolve().parents[2]
        / "shipwright-compliance" / "scripts" / "audit" / "audit_staleness.py"
    )
    sentinel = "_compliance_audit_staleness_under_test"
    spec = importlib.util.spec_from_file_location(sentinel, compliance_audit_path)
    audit_mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = audit_mod
    try:
        spec.loader.exec_module(audit_mod)
        snapshot_sha = audit_mod.find_snapshot_commit(pipeline_project)
    finally:
        sys.modules.pop(sentinel, None)

    assert snapshot_sha == result["commit_sha"]
