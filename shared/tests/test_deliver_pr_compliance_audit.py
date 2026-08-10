"""`lib.deliver_pr_compliance_audit.run_merge_compliance_audit` (P2.59).

Extracted out of `deliver_pr.py` (ADR-122 addendum 2026-08-10) — this file
pins the argv this builds and its result-to-diagnostic mapping. The actual
subprocess/timeout/tree-kill mechanics live in `lib.compliance_audit_spawn`
and are tested there (`test_compliance_audit_spawn.py`, doubt review round 3
HIGH #1 — a `uv run` grandchild is not bounded by a plain `subprocess.run`
timeout).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import lib.deliver_pr_compliance_audit as merge_audit_module  # noqa: E402
from lib.deliver_pr_compliance_audit import run_merge_compliance_audit  # noqa: E402

SCRIPTS_ROOT = REPO_ROOT / "shared" / "scripts"


def test_success_reports_ran_true(monkeypatch, tmp_path):
    monkeypatch.setattr(merge_audit_module, "spawn_compliance_audit",
                        lambda argv, **kw: {"ran": True, "detail": "ok"})
    result = run_merge_compliance_audit(SCRIPTS_ROOT, tmp_path, "r", "7", "o/repo")
    assert result == {"ran": True, "detail": "ok"}


def test_nonzero_exit_reports_ran_false_and_warns(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(merge_audit_module, "spawn_compliance_audit",
                        lambda argv, **kw: {"ran": False, "detail": "boom"})
    result = run_merge_compliance_audit(SCRIPTS_ROOT, tmp_path, "r", "7", "o/repo")
    assert result == {"ran": False, "detail": "boom"}
    assert "merge audit did not complete" in capsys.readouterr().err


def test_builds_the_expected_merge_scope_argv(monkeypatch, tmp_path):
    seen = {}

    def fake_spawn(argv, **kw):
        seen["argv"] = argv
        return {"ran": True, "detail": "ok"}

    monkeypatch.setattr(merge_audit_module, "spawn_compliance_audit", fake_spawn)
    run_merge_compliance_audit(SCRIPTS_ROOT, tmp_path, "run-9", "42", "o/r")
    lifecycle = SCRIPTS_ROOT / "tools" / "audit_compliance_lifecycle.py"
    assert seen["argv"] == [
        "uv", "run", "--with", "pyyaml", str(lifecycle), "--scope", "merge",
        "--project-root", str(tmp_path), "--run-id", "run-9", "--pr", "42", "--repo", "o/r",
    ]
