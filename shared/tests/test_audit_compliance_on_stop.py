"""Tests for the compliance detective-audit Stop hook.

The triage emit/dismiss machinery (`mirror_findings_to_triage`) is covered
by `test_compliance_audit_triage_emit.py`. THIS file covers the HOOK's
novel surface:

  * the full-coverage SAFETY GATE (`coverage_ok` / `emit_if_full_coverage`)
    — the load-bearing defence against false auto-dismiss when a group
    crashed / was skipped;
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
    # Full coverage is A-I (run_all runs H+I by default; gate expects them).
    return _FakeReport(["A", "B", "C", "D", "E", "F", "G", "H", "I"])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    # Minimal Shipwright marker so is_shipwright_project() passes.
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "run_id": "iterate-x"}), encoding="utf-8")
    return tmp_path


def test_coverage_ok_full_set():
    ok, reason = hook.coverage_ok(_full_report())  # canonical A-I set
    assert ok is True
    assert "full coverage" in reason.lower()


def test_coverage_blocked_on_missing_group():
    # No G, H or I — all three surface as missing; the gate blocks.
    ok, reason = hook.coverage_ok(_FakeReport(["A", "B", "C", "D", "E", "F"]))
    assert ok is False
    assert "missing=['G', 'H', 'I']" in reason


def test_coverage_blocked_on_import_gate_error():
    ok, reason = hook.coverage_ok(_FakeReport([], import_gate_error="drift!"))
    assert ok is False
    assert "import_gate_error" in reason


def test_coverage_blocked_when_only_group_F():
    # GAP hazard: only-F would dismiss B7/B2/etc. F20: H is now expected too.
    ok, reason = hook.coverage_ok(_FakeReport(["F"]))
    assert ok is False
    assert set("ABCDEGH").issubset(set(reason.replace("'", "")))


def test_emit_mirrors_only_on_full_coverage(project: Path):
    calls = []

    def spy(pr, rep, *, run_id, commit):
        calls.append((pr, run_id, commit))
        return {"appended": 3, "dismissed": 1}

    out = hook.emit_if_full_coverage(
        project, _full_report(), run_id="r1", commit="sha", mirror_fn=spy)
    assert out["mirrored"] is True
    assert out["appended"] == 3 and out["dismissed"] == 1
    assert calls == [(project, "r1", "sha")]


def test_emit_does_NOT_mirror_on_partial_coverage(project: Path):
    """The whole point: a partial audit must never call the mirror (which
    would auto-dismiss the missing groups' triage items)."""
    calls = []

    def spy(*a, **k):
        calls.append((a, k))
        return {"appended": 0, "dismissed": 99}

    out = hook.emit_if_full_coverage(
        project, _FakeReport(["A", "B"]), run_id="r1", commit="s", mirror_fn=spy)
    assert out["mirrored"] is False
    assert "missing=" in out["reason"]
    assert calls == []  # mirror NEVER invoked


def test_emit_swallows_mirror_exception(project: Path):
    def boom(*a, **k):
        raise RuntimeError("triage write failed")

    out = hook.emit_if_full_coverage(
        project, _full_report(), run_id="r", commit="s", mirror_fn=boom)
    assert out["mirrored"] is False
    assert "mirror error" in out["reason"]


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
    if project_root is not None:
        monkeypatch.setattr(hook, "_resolve_project_root", lambda: project_root)
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
                   audit_api=(lambda: called.append("reg"), None, None))
    assert rc == 0
    assert called == []  # never reached the audit


def test_main_greenfield_noop(monkeypatch, tmp_path):
    # tmp_path has no Shipwright markers.
    called = []
    rc = _run_main(monkeypatch, project_root=tmp_path, cwd=tmp_path,
                   audit_api=(lambda: called.append("reg"), None, None))
    assert rc == 0
    assert called == []


def test_main_full_run_emits_then_idempotent(monkeypatch, project):
    reg_calls, mirror_calls = [], []

    def fake_run_all(pr, **kw):
        return _full_report()

    def fake_mirror(pr, rep, *, run_id, commit):
        mirror_calls.append(run_id)
        return {"appended": 2, "dismissed": 1}

    api = (lambda: reg_calls.append(1), fake_run_all, fake_mirror)

    rc1 = _run_main(monkeypatch, session="s1", project_root=project, cwd=project,
                    audit_api=api)
    assert rc1 == 0
    assert reg_calls == [1] and mirror_calls == ["iterate-x"]
    assert hook.already_audited(project, "deadbeef", "s1") is True

    # Second invocation, same (sha, session): idempotent skip — audit not re-run.
    rc2 = _run_main(monkeypatch, session="s1", project_root=project, cwd=project,
                    audit_api=api)
    assert rc2 == 0
    assert reg_calls == [1]  # NOT re-run
    assert mirror_calls == ["iterate-x"]


def test_main_partial_coverage_does_not_mirror(monkeypatch, project):
    mirror_calls = []

    def fake_run_all(pr, **kw):
        return _FakeReport(["A", "B"])  # crashed/partial

    def fake_mirror(pr, rep, *, run_id, commit):
        mirror_calls.append(1)
        return {"appended": 0, "dismissed": 5}

    rc = _run_main(monkeypatch, session="sP", project_root=project, cwd=project,
                   audit_api=(lambda: None, fake_run_all, fake_mirror))
    assert rc == 0
    assert mirror_calls == []  # gate blocked the mirror — no false dismiss


def test_main_audit_api_unavailable_noop(monkeypatch, project):
    rc = _run_main(monkeypatch, session="sU", project_root=project, cwd=project,
                   audit_api=(None, None, None))
    assert rc == 0


def test_main_never_blocks_on_internal_error(monkeypatch, project):
    def boom(pr, **kw):
        raise RuntimeError("audit exploded")

    rc = _run_main(monkeypatch, session="sE", project_root=project, cwd=project,
                   audit_api=(lambda: None, boom, lambda *a, **k: {}))
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
