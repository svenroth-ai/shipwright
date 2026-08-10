"""Tests for the compliance detective-audit Stop hook.

The triage emit/dismiss machinery (`mirror_findings_to_triage`) is covered
by `test_compliance_audit_triage_emit.py`. THIS file covers the HOOK's
novel surface:

  * branch-feedback authority — the hook runs full A-I detection on the
    resolved worktree and reports local failures only; it never calls the
    triage mirror or touches the global backlog (that authority moved to
    `audit_compliance_lifecycle.py`, gated on delivered merge or verified
    release — see `test_compliance_lifecycle.py`);
  * idempotency per (HEAD-sha, session_id);
  * opt-out env var;
  * greenfield + non-Shipwright-plugin no-ops;
  * `main()` never blocks (always exits 0);
  * both hooks.json Stop chains wire the hook in the mandated order.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

_HOOK_PATH = _SHARED_SCRIPTS / "hooks" / "audit_compliance_on_stop.py"
_spec = importlib.util.spec_from_file_location("audit_compliance_on_stop_uut", _HOOK_PATH)
assert _spec is not None and _spec.loader is not None
hook = importlib.util.module_from_spec(_spec)
sys.modules["audit_compliance_on_stop_uut"] = hook
_spec.loader.exec_module(hook)


class _FakeReport:
    def __init__(self, groups_run, *, import_gate_error=None, groups_skipped=None):
        self.groups_run = list(groups_run)
        self.import_gate_error = import_gate_error
        self.groups_skipped = groups_skipped or []


def _full_report():
    # Full coverage is A-I (lib.compliance_lifecycle.ALL_GROUPS).
    return _FakeReport(["A", "B", "C", "D", "E", "F", "G", "H", "I"])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    # Minimal Shipwright marker so is_shipwright_project() passes.
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "run_id": "iterate-x"}), encoding="utf-8")
    return tmp_path


def test_already_audited_lifecycle(project: Path):
    assert hook.already_audited(project, "sha1", "sess1") is False
    hook._write_marker(project, "sha1", "sess1", {"ok": True})
    assert hook.already_audited(project, "sha1", "sess1") is True
    # Different sha or session is a different marker.
    assert hook.already_audited(project, "sha2", "sess1") is False
    assert hook.already_audited(project, "sha1", "sess2") is False


def test_corrupt_marker_counts_as_not_audited(project: Path):
    path = hook._marker_path(project, "sha1", "sess1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert hook.already_audited(project, "sha1", "sess1") is False


def test_marker_path_shape(project: Path):
    assert ".shipwright/agent_docs/runtime/compliance_audit" in \
        hook._marker_path(project, "abc", "s").as_posix()  # gitignored runtime tree
    assert hook._marker_path(project, "", "s").name.startswith("nogit-")  # empty-sha token


@pytest.mark.parametrize("val,expected", [
    ("", True), ("1", True), ("true", True), ("on", True),
    ("0", False), ("false", False), ("no", False), ("off", False), ("OFF", False),
])
def test_opt_out_parsing(monkeypatch, val, expected):
    monkeypatch.setenv("SHIPWRIGHT_COMPLIANCE_AUDIT_ON_STOP", val)
    assert hook.audit_on_stop_enabled() is expected


def _run_main(monkeypatch, *, plugin="shipwright-iterate", session="s",
              audit_api=None, project_root=None, cwd=None):
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", f"/x/plugins/{plugin}")
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", session)
    monkeypatch.delenv("SHIPWRIGHT_COMPLIANCE_AUDIT_ON_STOP", raising=False)
    # The hook resolves via `pq.resolve_project_roots(cwd, session_id)` now —
    # `cwd` (below) IS the plain-root input to that resolver; `project_root`
    # is accepted only for callers that want a marker placed there (it is
    # `cwd` at every call site in this file, so the real resolver's own
    # "cwd, if it is itself a Shipwright project" step already finds it).
    if cwd is not None:
        monkeypatch.setattr(hook.Path, "cwd", staticmethod(lambda: cwd))
    monkeypatch.setattr(hook, "_git_head_sha", lambda pr: "deadbeef")
    monkeypatch.setattr(hook.sys, "stdin", _DummyStdin())
    if audit_api is not None:
        monkeypatch.setattr(hook, "_load_audit_api", lambda: audit_api)
    return hook.main()


class _DummyStdin:
    def read(self):  # json.load(sys.stdin) calls .read()
        return "{}"


def test_main_opt_out_returns_0(monkeypatch, project):
    monkeypatch.setenv("SHIPWRIGHT_COMPLIANCE_AUDIT_ON_STOP", "0")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/x/plugins/shipwright-iterate")
    monkeypatch.setattr(hook.sys, "stdin", _DummyStdin())
    assert hook.main() == 0


def test_main_non_shipwright_plugin_noop(monkeypatch, project):
    called = []
    rc = _run_main(monkeypatch, plugin="some-other-plugin",
                   project_root=project, cwd=project,
                   audit_api=(lambda: called.append("reg"), None))
    assert rc == 0
    assert called == []  # never reached the audit


def test_main_greenfield_noop(monkeypatch, tmp_path):
    # tmp_path has no Shipwright markers.
    called = []
    rc = _run_main(monkeypatch, project_root=tmp_path, cwd=tmp_path,
                   audit_api=(lambda: called.append("reg"), None))
    assert rc == 0
    assert called == []


def test_main_full_run_is_local_then_idempotent(monkeypatch, project):
    reg_calls = []

    def fake_run_all(pr, **kw):
        return _full_report()

    api = (lambda: reg_calls.append(1), fake_run_all)

    rc1 = _run_main(monkeypatch, session="s1", project_root=project, cwd=project,
                    audit_api=api)
    assert rc1 == 0
    assert reg_calls == [1]
    assert hook.already_audited(project, "deadbeef", "s1") is True

    # Second invocation, same (sha, session): idempotent skip — audit not re-run.
    rc2 = _run_main(monkeypatch, session="s1", project_root=project, cwd=project,
                    audit_api=api)
    assert rc2 == 0
    assert reg_calls == [1]  # NOT re-run


def test_main_partial_coverage_still_reports_local_diagnostics(monkeypatch, project):
    """Branch feedback never mirrors, coverage complete or not — this proves
    the local-diagnostics path still runs (and records incomplete coverage
    honestly) on a crashed/partial audit, with no mirror to gate."""
    def fake_run_all(pr, **kw):
        return _FakeReport(["A", "B"])  # crashed/partial

    rc = _run_main(monkeypatch, session="sP", project_root=project, cwd=project,
                   audit_api=(lambda: None, fake_run_all))
    assert rc == 0
    marker = json.loads(hook._marker_path(project, "deadbeef", "sP").read_text(encoding="utf-8"))
    assert marker["result"]["coverage"]["complete"] is False
    assert marker["result"]["mirrored"] is False


def test_main_audit_api_unavailable_noop(monkeypatch, project):
    rc = _run_main(monkeypatch, session="sU", project_root=project, cwd=project,
                   audit_api=(None, None))
    assert rc == 0


def test_load_audit_api_refuses_a_stale_run_all_with_emit_to_triage(monkeypatch):
    """Plugin-cache skew guard: a `run_all` still carrying the pre-P2.59
    `emit_to_triage` parameter must never be handed back — a partial cache
    sync could pair this hook's bare call with a detector that still
    mirrors by default."""
    def stale_run_all(project_root, *, run_gate=True, emit_to_triage=True):
        raise AssertionError("must never be called")

    fake_registry = types.ModuleType("scripts.audit._registry")
    fake_registry.register_all = lambda: None
    fake_detector = types.ModuleType("scripts.audit.audit_detector")
    fake_detector.run_all = stale_run_all

    monkeypatch.setitem(sys.modules, "scripts", types.ModuleType("scripts"))
    monkeypatch.setitem(sys.modules, "scripts.audit", types.ModuleType("scripts.audit"))
    monkeypatch.setitem(sys.modules, "scripts.audit._registry", fake_registry)
    monkeypatch.setitem(sys.modules, "scripts.audit.audit_detector", fake_detector)

    assert hook._load_audit_api() == (None, None)


def test_load_audit_api_accepts_a_modern_run_all(monkeypatch):
    """Mirror case: the guard above must not over-match every `run_all` —
    a modern signature (no `emit_to_triage`) has to come back usable."""
    def modern_run_all(project_root, *, run_gate=True):
        return "unused"

    fake_registry = types.ModuleType("scripts.audit._registry")
    fake_registry.register_all = lambda: None
    fake_detector = types.ModuleType("scripts.audit.audit_detector")
    fake_detector.run_all = modern_run_all

    monkeypatch.setitem(sys.modules, "scripts", types.ModuleType("scripts"))
    monkeypatch.setitem(sys.modules, "scripts.audit", types.ModuleType("scripts.audit"))
    monkeypatch.setitem(sys.modules, "scripts.audit._registry", fake_registry)
    monkeypatch.setitem(sys.modules, "scripts.audit.audit_detector", fake_detector)

    register, run_all = hook._load_audit_api()
    assert run_all is modern_run_all


def test_main_never_blocks_on_internal_error(monkeypatch, project):
    def boom(pr, **kw):
        raise RuntimeError("audit exploded")

    rc = _run_main(monkeypatch, session="sE", project_root=project, cwd=project,
                   audit_api=(lambda: None, boom))
    assert rc == 0  # exception swallowed, Stop chain never blocked


def _stop_commands(hooks_json: Path) -> list[str]:
    data = json.loads(hooks_json.read_text(encoding="utf-8"))
    cmds = []
    for group in data["hooks"]["Stop"]:
        for h in group["hooks"]:
            cmds.append(h["command"])
    return cmds


def _idx(cmds, needle):
    for i, c in enumerate(cmds):
        if needle in c:
            return i
    return -1


def test_wired_into_iterate_stop_chain_in_order():
    cmds = _stop_commands(
        _WORKTREE / "plugins" / "shipwright-iterate" / "hooks" / "hooks.json")
    i_self = _idx(cmds, "audit_compliance_on_stop.py")
    i_pq = _idx(cmds, "audit_phase_quality_on_stop.py")
    i_agg = _idx(cmds, "aggregate_triage_on_stop.py")
    i_fin = _idx(cmds, "iterate_stop_finalize.py")
    assert i_self != -1, "compliance audit hook not wired into iterate Stop chain"
    assert i_fin < i_self, "must run AFTER finalize"
    assert i_pq < i_self, "must run AFTER phase_quality"
    assert i_self < i_agg, "must run BEFORE aggregate_triage"


def test_wired_into_changelog_stop_chain_after_phase_quality():
    cmds = _stop_commands(
        _WORKTREE / "plugins" / "shipwright-changelog" / "hooks" / "hooks.json")
    i_self = _idx(cmds, "audit_compliance_on_stop.py")
    i_pq = _idx(cmds, "audit_phase_quality_on_stop.py")
    assert i_self != -1, "compliance audit hook not wired into changelog Stop chain"
    assert i_pq < i_self, "must run AFTER phase_quality"


def test_main_resolves_the_active_worktree_before_running_detection(monkeypatch, tmp_path):
    """`resolve_project_roots` binds `pointer_worktree_root` in ITS OWN module
    globals (`lib.phase_quality._resolution`, via `from ._run_id import ...`) —
    patching the `lib.phase_quality` package attribute cannot reach that
    binding (ADR-045: patch the module object, never a rebound name). And
    `main_root` needs a real marker: it is the `plain_root` the greenfield
    guard now checks (never the redirected root)."""
    main_root = tmp_path / "main"
    active = tmp_path / "active"
    main_root.mkdir()
    active.mkdir()
    (main_root / "shipwright_run_config.json").write_text(json.dumps({"status": "complete"}), encoding="utf-8")
    (active / "shipwright_run_config.json").write_text(json.dumps({"status": "complete"}), encoding="utf-8")
    roots = []

    def fake_run_all(root, **kwargs):
        roots.append(root)
        return _full_report()

    import lib.phase_quality._resolution as _resolution
    monkeypatch.setattr(_resolution, "pointer_worktree_root", lambda cwd, session: active)
    rc = _run_main(monkeypatch, session="active-run", project_root=main_root, cwd=main_root,
                   audit_api=(lambda: None, fake_run_all))
    assert rc == 0
    assert roots == [active]
