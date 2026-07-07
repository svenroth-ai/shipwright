"""Guard: phase_session_start degrades to standalone (never crashes) when the
cross-plugin phase_task_lifecycle import is unavailable.

A marketplace install that delivers ``shared/`` but not ``cache/shipwright/plugins/``
makes ``from phase_task_lifecycle import ...`` fail, so the module's import-time
``except ImportError`` sets ``find_phase_task_by_session_uuid`` (and siblings) to
``None``. Before this guard, ``run()`` called the None at discovery and crashed
SessionStart (reported on macOS). The sibling ``phase_session_stop`` /
``phase_user_prompt_validate`` hooks already carry the same guard; this pins it
for ``phase_session_start`` too.

Kept in its own file (not ``test_phase_session_hooks.py``, which sits at its bloat
baseline) so this addition doesn't ratchet that file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "shipwright-run" / "scripts" / "lib"))
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts" / "hooks"))

import phase_session_start  # noqa: E402


def test_degraded_cross_plugin_import_returns_standalone(tmp_path, monkeypatch, capsys):
    project = tmp_path / "proj"
    project.mkdir()
    # A valid v2 run config so run() reaches the discovery guard (not an earlier bail).
    (project / phase_session_start.CONFIG_NAME).write_text(
        json.dumps({"schemaVersion": 2, "runId": "r"}), encoding="utf-8",
    )
    # Simulate the degraded install: the import-time fallback set these to None.
    monkeypatch.setattr(phase_session_start, "find_phase_task_by_session_uuid", None)
    monkeypatch.setattr(phase_session_start, "validate_prerequisites", None)
    monkeypatch.setattr(phase_session_start, "claim_phase_task", None)

    rc = phase_session_start.run(project, session_uuid="any-uuid", plugin_root="shipwright-build")

    assert rc == 0  # standalone, never a NoneType-not-callable crash
    assert capsys.readouterr().out == ""  # no pipeline-context emitted in degraded mode
