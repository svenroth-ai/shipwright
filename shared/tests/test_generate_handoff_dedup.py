"""Once-per-(Stop, session) dedup for ``generate_handoff_on_stop.py``.

The ~11× Stop fan-out regenerates the SAME handoff + dashboard; the
``claim_once_for_event`` guard makes the work run once. The hook writes
"[shipwright:handoff] generated at ..." to stderr only when it actually does the
work, so that string is the deterministic did-work signal.

(Split from ``test_generate_handoff_on_stop.py`` so that file stays at its bloat
baseline — these are NEW behavior, not changes to the existing tests.)
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

HOOK = (
    Path(__file__).resolve().parent.parent
    / "scripts" / "hooks" / "generate_handoff_on_stop.py"
)


def _project(tmp_path: Path) -> Path:
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True)
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
    return tmp_path


def _run(project: Path, session_id: str | None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if session_id is None:
        env.pop("SHIPWRIGHT_SESSION_ID", None)
    else:
        env["SHIPWRIGHT_SESSION_ID"] = session_id
    return subprocess.run(
        [sys.executable, str(HOOK)], input="{}",
        capture_output=True, text=True, cwd=str(project), env=env,
    )


def test_claim_dedups_within_session(tmp_path: Path):
    p = _project(tmp_path)
    r1 = _run(p, "handoff-dedup-A")
    assert r1.returncode == 0 and "generated" in r1.stderr  # first wins
    r2 = _run(p, "handoff-dedup-A")
    assert r2.returncode == 0 and "generated" not in r2.stderr  # claim fresh → skip


def test_claim_rearms_after_ttl(tmp_path: Path):
    p = _project(tmp_path)
    sid = "handoff-dedup-B"
    r1 = _run(p, sid)
    assert "generated" in r1.stderr
    claim = p / ".shipwright" / ".cache" / f"stop-handoff-{sid}.claim"
    assert claim.exists()
    os.utime(claim, (time.time() - 120, time.time() - 120))  # beyond 30s TTL
    r2 = _run(p, sid)
    assert r2.returncode == 0 and "generated" in r2.stderr  # re-armed → regen


def test_distinct_sessions_each_regenerate(tmp_path: Path):
    p = _project(tmp_path)
    assert "generated" in _run(p, "sess-X").stderr
    assert "generated" in _run(p, "sess-Y").stderr  # independent claim


def test_unknown_session_does_not_dedup(tmp_path: Path):
    """No real session id → fail-open: both invocations regenerate (no shared
    'unknown' claim key suppressing the 2nd — external-review code gpt#1)."""
    p = _project(tmp_path)
    assert "generated" in _run(p, None).stderr
    assert "generated" in _run(p, None).stderr
