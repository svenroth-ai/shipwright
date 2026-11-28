"""The real Stop hook against the real new-then-old lookup (campaign root-files-into-config, R1c-1).

No patching of the resolver: each phase's evidence file sits physically in ``.shipwright/config/``
(the post-move layout) and the hook's real ``main()`` must find it there. With two divergent copies
the hook must neither read one of them nor stay silent: the both-copies ``LayoutError`` reaches
stderr. Integration coverage for the ``cross_component`` flag (``hooks/*.py`` touched).
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


def _project(tmp_path: Path, phase: str) -> Path:
    root = tmp_path / "proj"
    (root / ".shipwright" / "agent_docs").mkdir(parents=True)
    # run_config stays at the root: its frozen readers move with R1c-2
    (root / _ghs._sp.legacy_rel("run_config")).write_text(json.dumps({
        "status": "in_progress", "phase_tasks": [{"phase": phase, "status": "in_progress"}]}), encoding="utf-8")
    return root


def _stop(root: Path, monkeypatch, session: str) -> list:
    calls: list = []
    monkeypatch.setattr(_ghs, "_run_phase_completion", lambda r, step: calls.append(step))
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(root))
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", session)  # the hook runs once per session
    monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    assert _ghs.main() == 0
    return calls


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("phase,key,body", _PHASES)
def test_the_hook_reads_phase_evidence_from_the_new_place(tmp_path, monkeypatch, phase, key, body):
    root = _project(tmp_path, phase)
    new = root / _ghs._sp.new_rel(key)
    new.parent.mkdir(parents=True, exist_ok=True)
    new.write_text(json.dumps(body), encoding="utf-8")
    assert not (root / _ghs._sp.legacy_rel(key)).exists()
    assert _stop(root, monkeypatch, f"r1c1-new-{phase}") == [phase]


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("phase,key,body", _PHASES)
def test_two_copies_stop_the_detector_and_are_reported(tmp_path, monkeypatch, capsys, phase, key, body):
    root = _project(tmp_path, phase)
    new = root / _ghs._sp.new_rel(key)
    new.parent.mkdir(parents=True, exist_ok=True)
    new.write_text(json.dumps(body), encoding="utf-8")
    (root / _ghs._sp.legacy_rel(key)).write_text(json.dumps({"status": "stale"}), encoding="utf-8")
    assert _stop(root, monkeypatch, f"r1c1-both-{phase}") == [], "one of two divergent copies was read"
    err = capsys.readouterr().err
    assert "both_copies" in err and str(new) in err, err
    # reported by the phase-completion block itself, not by the outer "generation skipped" handler
    assert "generated at" in err and "generation skipped" not in err, err
