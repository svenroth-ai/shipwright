"""Once-per-SessionStart dedup for ``check_artifact_drift.py``.

The hook is registered in all 12 plugins and fires ~12× per SessionStart with
identical inputs (it scans ``project_root`` and never reads
``CLAUDE_PLUGIN_ROOT``). The once-per-event claim makes the stale-artifact scan
run exactly ONCE per session; the rest skip. Fail-open: a guard error runs the
scan rather than dropping a real drift signal.

These are in-process tests: the real scan (``stale_artifact_detector.hook_main``)
is replaced with a call-counter so "ran once" is directly observable without
constructing a full ARTIFACT_MIGRATIONS drift fixture. The real subprocess
fan-out is exercised by ``integration-tests/test_hook_fanout_consolidation.py``.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import time
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

_HOOK = _SHARED_SCRIPTS / "hooks" / "check_artifact_drift.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location(
        "check_artifact_drift_under_test", _HOOK,
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _shipwright_project(tmp_path: Path) -> Path:
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
    return tmp_path


def _run_main(mod, project: Path, payload: dict, monkeypatch) -> int:
    # The hook lazily `from lib... import hook_main` inside main(), so patching
    # the module attribute is picked up at call time.
    monkeypatch.setattr(mod, "_resolve_root", lambda: project)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    return mod.main()


def test_drift_scan_runs_once_per_session(tmp_path: Path, monkeypatch) -> None:
    project = _shipwright_project(tmp_path)
    mod = _load_hook()
    import lib.stale_artifact_detector as sad

    calls: list[Path] = []
    monkeypatch.setattr(sad, "hook_main", lambda root: calls.append(Path(root)) or 0)
    payload = {"session_id": "drift-sess-1"}

    assert _run_main(mod, project, payload, monkeypatch) == 0
    assert _run_main(mod, project, payload, monkeypatch) == 0
    assert len(calls) == 1  # 2nd invocation skipped by the once-per-event claim


def test_drift_scan_rearms_after_ttl(tmp_path: Path, monkeypatch) -> None:
    project = _shipwright_project(tmp_path)
    mod = _load_hook()
    import lib.stale_artifact_detector as sad

    calls: list[int] = []
    monkeypatch.setattr(sad, "hook_main", lambda root: calls.append(1) or 0)
    payload = {"session_id": "drift-sess-2"}

    assert _run_main(mod, project, payload, monkeypatch) == 0
    claim = (
        project / ".shipwright" / ".cache"
        / "sessionstart-drift-drift-sess-2.claim"
    )
    assert claim.exists()
    old = time.time() - 120  # beyond the 30s TTL
    os.utime(claim, (old, old))

    assert _run_main(mod, project, payload, monkeypatch) == 0
    assert len(calls) == 2  # re-armed after TTL → scan runs again


def test_distinct_sessions_each_scan(tmp_path: Path, monkeypatch) -> None:
    project = _shipwright_project(tmp_path)
    mod = _load_hook()
    import lib.stale_artifact_detector as sad

    calls: list[int] = []
    monkeypatch.setattr(sad, "hook_main", lambda root: calls.append(1) or 0)

    assert _run_main(mod, project, {"session_id": "s-A"}, monkeypatch) == 0
    assert _run_main(mod, project, {"session_id": "s-B"}, monkeypatch) == 0
    assert len(calls) == 2  # independent claims → both scan


def test_drift_scan_fail_open_when_claim_errors(tmp_path: Path, monkeypatch) -> None:
    """A guard error FAILS OPEN — the scan runs rather than being dropped."""
    project = _shipwright_project(tmp_path)
    mod = _load_hook()
    import lib.event_once as eo
    import lib.stale_artifact_detector as sad

    calls: list[int] = []
    monkeypatch.setattr(sad, "hook_main", lambda root: calls.append(1) or 0)

    def _boom(*a, **k):
        raise RuntimeError("simulated claim failure")

    monkeypatch.setattr(eo, "claim_once", _boom)

    assert _run_main(mod, project, {"session_id": "s-err"}, monkeypatch) == 0
    assert len(calls) == 1  # fail-open: scan still ran
