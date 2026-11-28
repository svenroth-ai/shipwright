"""The Stop hook finds each phase's evidence where the resolver says it lives (campaign
root-files-into-config, R1b).

R1b routed the hook's four evidence reads (build / plan / project config, test results)
through ``shipwright_paths.path()``. This runs the real hook ``main()`` with the real
run config and the real resolver, moves every resolver location into a subfolder (what
R1c does for real), and checks the phase-completion detector fires only on a file at
the resolver's location. The old root location alone must no longer be read.
Integration coverage for the ``cross_component`` flag (``hooks/*.py`` touched).
"""

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "hooks"))
import generate_handoff_on_stop as _ghs  # noqa: E402

_PHASES = [
    ("build", "build_config", {"sections": [{"status": "complete"}]}),
    ("plan", "plan_config", {"status": "complete"}),
    ("project", "project_config", {"status": "complete"}),
    ("test", "test_results", {"status": "pass"}),
]


def _run(root: Path, phase: str, monkeypatch, session: str) -> list:
    """One Stop-hook turn; the hook runs once per session, so each turn gets its own id."""
    _ghs._sp.path("run_config", root).write_text(json.dumps({
        "status": "in_progress",
        "phase_tasks": [{"phase": phase, "status": "in_progress"}],
    }), encoding="utf-8")
    calls: list = []
    monkeypatch.setattr(_ghs, "_run_phase_completion", lambda r, step: calls.append(step))
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(root))
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", session)
    monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    assert _ghs.main() == 0
    return calls


def _moved(monkeypatch, keys: set[str]) -> None:
    """Make ``path()`` answer ``moved/<name>`` for ``keys`` while ``rel()`` stays put: the shape of
    R1c's lookup, which lives in ``path()``. A hand-built ``root / rel(key)`` would miss it."""
    sp = _ghs._sp
    real = sp.path
    monkeypatch.setattr(sp, "path", lambda k, r: (Path(r) / "moved" / sp.name(k)) if k in keys else real(k, r))


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("phase,key,body", _PHASES)
def test_hook_reads_the_phase_evidence_where_the_resolver_points(tmp_path, monkeypatch, phase, key, body):
    root = tmp_path / "proj"
    (root / ".shipwright" / "agent_docs").mkdir(parents=True)
    (root / "moved").mkdir()
    old = _ghs._sp.path(key, root)  # today's location, before the move
    _moved(monkeypatch, {key})
    old.write_text(json.dumps(body), encoding="utf-8")
    assert _run(root, phase, monkeypatch, "r1b-old") == [], "a file only at the old root location was read"
    _ghs._sp.path(key, root).write_text(json.dumps(body), encoding="utf-8")
    assert _ghs._sp.path(key, root).parent.name == "moved"
    assert _run(root, phase, monkeypatch, "r1b-new") == [phase]
