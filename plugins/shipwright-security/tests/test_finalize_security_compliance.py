"""Tests for ``finalize_security_compliance.py`` (iterate-2026-05-23).

After Step 7 persists `shipwright_security_config.json`, Step 7.5 runs
this helper to regenerate compliance MDs and commit them as an explicit
snapshot if anything changed. Contract:

- **Pipeline mode only.** Standalone (no ``shipwright_project_config.json``)
  → no-op.
- **CI / non-interactive skip.** ``CI`` / ``SHIPWRIGHT_NON_INTERACTIVE``
  env vars set → no-op (CI commits would race with the pipeline).
- **Idempotent.** If ``update_compliance.py --phase security`` produces
  no diff, no commit is created.
- **Snapshot-qualifying commit.** When a commit is made, its body
  contains ``Run-ID: security-<scan_id>`` so the audit recognizes it.

Returns structured JSON: ``{committed, reason, commit_sha?}``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))


def _load_finalize_module():
    """Load ``finalize_security_compliance`` via importlib + sentinel name.

    ``tools/`` is a namespace package shared across plugins. Earlier
    tests in the run may pin ``tools`` to a sibling plugin's
    ``scripts/tools/`` (compliance plugin in particular). A naive
    ``from tools.finalize_security_compliance import finalize`` then
    raises ``ModuleNotFoundError`` because the cached ``tools`` namespace
    doesn't include our file. Loading via sentinel name avoids the
    ``tools`` slot entirely (mirrors
    ``audit_adapters.load_shared_lib`` from PR #78).
    """
    import importlib.util
    target = PLUGIN_ROOT / "scripts" / "tools" / "finalize_security_compliance.py"
    sentinel = "_test_security_finalize_under_test"
    spec = importlib.util.spec_from_file_location(sentinel, target)
    mod = importlib.util.module_from_spec(spec)
    # Register BEFORE exec_module so any dataclasses inside the module
    # can resolve their own __module__ via sys.modules — same dance as
    # in audit_adapters.load_shared_lib.
    sys.modules[sentinel] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(sentinel, None)
        raise
    return mod


# ---------------------------------------------------------------------------
# Git fixture helpers (mirror test_audit_snapshot.py)
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


def _baseline_compliance() -> dict[str, str]:
    return {
        ".shipwright/compliance/dashboard.md":
            "# Dashboard\n\nGenerated: 2026-05-23T00:00:00Z\n\nBaseline\n",
        ".shipwright/compliance/test-evidence.md":
            "# Test Evidence\n\nGenerated: 2026-05-23T00:00:00Z\n\nBaseline\n",
        ".shipwright/compliance/change-history.md":
            "# Change History\n\nGenerated: 2026-05-23T00:00:00Z\n\nBaseline\n",
        ".shipwright/compliance/sbom.md":
            "# SBOM\n\nGenerated: 2026-05-23T00:00:00Z\n\nBaseline\n",
    }


@pytest.fixture
def pipeline_project(tmp_path):
    """Synthetic git repo with shipwright_project_config.json (pipeline mode)."""
    _git_init(tmp_path)
    _git_commit(tmp_path, _baseline_compliance(), "chore: seed")
    (tmp_path / "shipwright_project_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8",
    )
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "pipeline": []}), encoding="utf-8",
    )
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "."],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "chore: pipeline-mode setup"],
        check=True, capture_output=True,
    )
    return tmp_path


@pytest.fixture
def standalone_project(tmp_path):
    """Same as pipeline_project but WITHOUT shipwright_project_config.json."""
    _git_init(tmp_path)
    _git_commit(tmp_path, _baseline_compliance(), "chore: seed")
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "pipeline": []}), encoding="utf-8",
    )
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "."],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "chore: standalone-mode setup"],
        check=True, capture_output=True,
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Tests for the helper module
# ---------------------------------------------------------------------------


def test_finalize_skips_in_standalone_mode(standalone_project, monkeypatch):
    """No `shipwright_project_config.json` → helper exits without committing."""
    finalize = _load_finalize_module().finalize

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_NON_INTERACTIVE", raising=False)

    head_before = subprocess.run(
        ["git", "-C", str(standalone_project), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    result = finalize(standalone_project, scan_id="scan-001")
    assert result["committed"] is False
    assert "standalone" in result["reason"].lower() or "pipeline" in result["reason"].lower()

    head_after = subprocess.run(
        ["git", "-C", str(standalone_project), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert head_before == head_after


def test_finalize_skips_in_ci(pipeline_project, monkeypatch):
    """CI env var set → no commit (CI doesn't drive interactive flow)."""
    finalize = _load_finalize_module().finalize

    monkeypatch.setenv("CI", "true")
    monkeypatch.delenv("SHIPWRIGHT_NON_INTERACTIVE", raising=False)

    head_before = subprocess.run(
        ["git", "-C", str(pipeline_project), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    result = finalize(pipeline_project, scan_id="scan-002")
    assert result["committed"] is False
    assert "ci" in result["reason"].lower()

    head_after = subprocess.run(
        ["git", "-C", str(pipeline_project), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert head_before == head_after


def test_finalize_skips_when_compliance_unchanged(pipeline_project, monkeypatch):
    """Mocked update_compliance produces no diff → no commit (idempotent)."""
    fsc = _load_finalize_module()

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_NON_INTERACTIVE", raising=False)

    # Stub the regen to be a no-op (compliance unchanged).
    monkeypatch.setattr(fsc, "_run_update_compliance",
                        lambda project_root: {"updated_reports": []})

    head_before = subprocess.run(
        ["git", "-C", str(pipeline_project), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    result = fsc.finalize(pipeline_project, scan_id="scan-003")
    assert result["committed"] is False
    assert "unchanged" in result["reason"].lower() or "no diff" in result["reason"].lower()

    head_after = subprocess.run(
        ["git", "-C", str(pipeline_project), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert head_before == head_after


def test_finalize_creates_snapshot_commit_when_compliance_changed(
    pipeline_project, monkeypatch,
):
    """Compliance MDs change → helper stages + commits with Run-ID trailer."""
    fsc = _load_finalize_module()

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_NON_INTERACTIVE", raising=False)

    # Stub update_compliance to actually dirty a file.
    def _fake_regen(project_root):
        dashboard = project_root / ".shipwright" / "compliance" / "dashboard.md"
        dashboard.write_text(
            "# Dashboard\n\nGenerated: 2026-05-24T00:00:00Z\n\nPost-security\n",
            encoding="utf-8",
        )
        return {"updated_reports": [".shipwright/compliance/dashboard.md"]}

    monkeypatch.setattr(fsc, "_run_update_compliance", _fake_regen)

    result = fsc.finalize(pipeline_project, scan_id="scan-abc-004")
    assert result["committed"] is True
    assert result.get("commit_sha")

    # Verify the commit's body contains the expected Run-ID trailer.
    commit_msg = subprocess.run(
        ["git", "-C", str(pipeline_project), "log", "-1", "--format=%B"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert "Run-ID: security-scan-abc-004" in commit_msg, (
        f"missing Run-ID trailer; got: {commit_msg!r}"
    )

    # Subject line follows the documented convention.
    subject = subprocess.run(
        ["git", "-C", str(pipeline_project), "log", "-1", "--format=%s"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert subject.startswith("chore(compliance):")


def test_finalize_idempotent_across_two_runs(pipeline_project, monkeypatch):
    """First run commits; second run with no further diff produces no commit."""
    fsc = _load_finalize_module()

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_NON_INTERACTIVE", raising=False)

    # First call dirties the dashboard; subsequent calls are no-ops.
    state = {"first": True}

    def _conditional_regen(project_root):
        dashboard = project_root / ".shipwright" / "compliance" / "dashboard.md"
        if state["first"]:
            dashboard.write_text(
                "# Dashboard\n\nGenerated: 2026-05-24T00:00:00Z\n\nPost-security\n",
                encoding="utf-8",
            )
            state["first"] = False
            return {"updated_reports": [".shipwright/compliance/dashboard.md"]}
        return {"updated_reports": []}

    monkeypatch.setattr(fsc, "_run_update_compliance", _conditional_regen)

    first = fsc.finalize(pipeline_project, scan_id="scan-once-005")
    assert first["committed"] is True

    second = fsc.finalize(pipeline_project, scan_id="scan-twice-005")
    assert second["committed"] is False
    assert "unchanged" in second["reason"].lower() or "no diff" in second["reason"].lower()


def test_finalize_commit_qualifies_as_snapshot(pipeline_project, monkeypatch):
    """The helper-created commit must be picked up by find_snapshot_commit."""
    fsc = _load_finalize_module()

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_NON_INTERACTIVE", raising=False)

    def _fake_regen(project_root):
        (project_root / ".shipwright" / "compliance" / "dashboard.md").write_text(
            "# Dashboard\n\nGenerated: 2026-05-24T00:00:00Z\n\nPost-security\n",
            encoding="utf-8",
        )
        return {"updated_reports": [".shipwright/compliance/dashboard.md"]}

    monkeypatch.setattr(fsc, "_run_update_compliance", _fake_regen)

    result = fsc.finalize(pipeline_project, scan_id="scan-snapshot-006")
    assert result["committed"] is True

    # Load audit_staleness via importlib so we don't fight the security
    # plugin's conftest, which has already pinned the `scripts` namespace
    # to plugins/shipwright-security/scripts/.
    import importlib.util
    compliance_audit_path = (
        Path(__file__).resolve().parents[2]
        / "shipwright-compliance" / "scripts" / "audit" / "audit_staleness.py"
    )
    sentinel = "_compliance_audit_staleness_under_test"
    spec = importlib.util.spec_from_file_location(sentinel, compliance_audit_path)
    audit_mod = importlib.util.module_from_spec(spec)
    # Register BEFORE exec so dataclasses inside the module can resolve
    # their own __module__ via sys.modules — same pattern as
    # audit_adapters.load_shared_lib.
    sys.modules[sentinel] = audit_mod
    try:
        spec.loader.exec_module(audit_mod)
        snapshot_sha = audit_mod.find_snapshot_commit(pipeline_project)
    finally:
        sys.modules.pop(sentinel, None)

    assert snapshot_sha == result["commit_sha"]
