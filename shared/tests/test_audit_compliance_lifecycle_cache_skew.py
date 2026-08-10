"""Plugin-cache skew guard for `audit_compliance_lifecycle._audit_api()` (P2.59).

This is the backlog-mutating authority path, so a stale `run_all` still
carrying the pre-P2.59 `emit_to_triage` parameter must be refused here too —
not just on the Stop hook's read-only branch-feedback path
(`test_audit_compliance_on_stop.py`).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "shared" / "scripts" / "tools" / "audit_compliance_lifecycle.py"
_spec = importlib.util.spec_from_file_location("lifecycle_skew_tool", TOOL)
lifecycle_tool = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(lifecycle_tool)


def _fake_plugin_modules(run_all):
    registry = types.ModuleType("scripts.audit._registry")
    registry.register_all = lambda: None
    detector = types.ModuleType("scripts.audit.audit_detector")
    detector.run_all = run_all
    detector.mirror_findings_to_triage = lambda *a, **kw: {}
    return registry, detector


def test_audit_api_refuses_a_stale_run_all_with_emit_to_triage(monkeypatch):
    def stale_run_all(project_root, *, run_gate=True, emit_to_triage=True):
        raise AssertionError("must never be called")

    registry, detector = _fake_plugin_modules(stale_run_all)
    monkeypatch.setitem(sys.modules, "scripts", types.ModuleType("scripts"))
    monkeypatch.setitem(sys.modules, "scripts.audit", types.ModuleType("scripts.audit"))
    monkeypatch.setitem(sys.modules, "scripts.audit._registry", registry)
    monkeypatch.setitem(sys.modules, "scripts.audit.audit_detector", detector)

    with pytest.raises(RuntimeError, match="stale compliance-plugin cache"):
        lifecycle_tool._audit_api()


def test_audit_api_accepts_a_modern_run_all(monkeypatch):
    def modern_run_all(project_root, *, run_gate=True):
        return "unused"

    registry, detector = _fake_plugin_modules(modern_run_all)
    monkeypatch.setitem(sys.modules, "scripts", types.ModuleType("scripts"))
    monkeypatch.setitem(sys.modules, "scripts.audit", types.ModuleType("scripts.audit"))
    monkeypatch.setitem(sys.modules, "scripts.audit._registry", registry)
    monkeypatch.setitem(sys.modules, "scripts.audit.audit_detector", detector)

    register, run_all, mirror = lifecycle_tool._audit_api()
    assert run_all is modern_run_all


def test_release_scope_refuses_to_audit_a_commit_other_than_head(git_origin_repo, monkeypatch):
    """AC4: a wrong-commit target must never reach `_audit_api()`/`run()` — that
    one-line guard (`_head(root) != sha`) is the only thing standing between a
    `--commit <other-sha>` invocation and converging the backlog for the wrong
    tree. `run` is monkeypatched to raise if this guard is ever bypassed."""
    work, _origin = git_origin_repo
    wrong_sha = "b" * 40
    monkeypatch.setattr(lifecycle_tool, "run",
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("must not audit")))
    assert lifecycle_tool.main(["--scope", "release", "--project-root", str(work),
                               "--commit", wrong_sha]) == 1


def test_release_scope_refuses_a_dirty_working_tree(git_origin_repo, monkeypatch):
    """Release has the WIDEST authority (full A-I, may dismiss Group E) — it
    must audit the committed tree, not whatever else is sitting on disk at the
    right HEAD sha (doubt review round 5, MEDIUM)."""
    work, _origin = git_origin_repo
    sha = lifecycle_tool._head(work)
    (work / "uncommitted.txt").write_text("dirty\n", encoding="utf-8")
    monkeypatch.setattr(lifecycle_tool, "_release_commit_verified", lambda root, commit: True)
    monkeypatch.setattr(lifecycle_tool, "run",
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("must not audit")))
    assert lifecycle_tool.main(["--scope", "release", "--project-root", str(work),
                               "--commit", sha]) == 1
