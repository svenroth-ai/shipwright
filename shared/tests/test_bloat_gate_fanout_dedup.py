"""Fan-out dedup for bloat_gate_on_stop.py.

The bloat gate is registered in every plugin, so a single Stop event fires it
once per enabled plugin (~12×). Without the once-per-(Stop, session) claim
guard, every invocation that finds offenders emits the SAME block, so the user
sees the block N× for one stop (webui session bfd244ca, reported 2026-06-20).

Firing the gate twice for the same (session, dir) deterministically reproduces
the fan-out: the first invocation claims + blocks, the second (claim-loser
within the 30 s TTL) emits the empty pass. Lives in its own module so the
existing ``test_bloat_gate_on_stop.py`` stays at its bloat baseline.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "hooks"


def _lines(n: int) -> str:
    return "x\n" * n


def _run_gate(cwd: Path, session_id: str = "sid-A",
              stdin: str = "{}") -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["SHIPWRIGHT_SESSION_ID"] = session_id
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "bloat_gate_on_stop.py")],
        input=stdin, capture_output=True, text=True,
        encoding="utf-8", errors="replace", cwd=str(cwd), env=env,
    )


def _seed_baseline(cwd: Path, paths: list[str]) -> None:
    entries = [{"path": p, "limit": 300, "current": 410,
                "state": "grandfathered", "adr": None} for p in paths]
    (cwd / "shipwright_bloat_baseline.json").write_text(
        json.dumps({"version": 1, "entries": entries}), encoding="utf-8")


def _seed_marker(cwd: Path, session_id: str, path: str, *, now: int = 320) -> None:
    locks = cwd / ".shipwright" / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    entry = {
        "path": path, "now": now, "limit": 300, "classification": "source",
        "was_in_allowlist": False, "delta": "crossing",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (locks / f"bloat_pending.{session_id}.json").write_text(
        json.dumps({"version": 1, "entries": [entry]}), encoding="utf-8")


def _decision(result: subprocess.CompletedProcess) -> dict | None:
    raw = result.stdout.strip()
    return json.loads(raw) if raw else None


def _claim_path(cwd: Path, session_id: str) -> Path:
    return cwd / ".shipwright" / ".cache" / f"stop-bloat-{session_id}.claim"


def test_fanout_dedup_blocks_once_then_passes(tmp_path):
    """AC-1: the first fan-out invocation blocks; the second (claim-loser) passes."""
    _seed_baseline(tmp_path, [])
    (tmp_path / "offender.py").write_text(_lines(320), encoding="utf-8")
    _seed_marker(tmp_path, "sid-A", "offender.py")
    first = _decision(_run_gate(tmp_path, session_id="sid-A"))
    assert first is not None and first.get("decision") == "block"
    assert "offender.py" in first["reason"]
    second = _run_gate(tmp_path, session_id="sid-A")
    assert second.returncode == 0
    assert second.stdout.strip() == "", "claim-loser must emit the empty pass"


def test_fanout_dedup_is_per_session(tmp_path):
    """AC-2: the claim is per (event, session); a second session still blocks."""
    _seed_baseline(tmp_path, [])
    (tmp_path / "offender.py").write_text(_lines(320), encoding="utf-8")
    _seed_marker(tmp_path, "sid-A", "offender.py")
    _seed_marker(tmp_path, "sid-B", "offender.py")
    a = _decision(_run_gate(tmp_path, session_id="sid-A"))
    b = _decision(_run_gate(tmp_path, session_id="sid-B"))
    assert a is not None and a.get("decision") == "block"
    assert b is not None and b.get("decision") == "block"


def test_pass_path_does_not_create_claim(tmp_path):
    """AC-4: a pass-path invocation (file under limit → no offender) must NOT
    create/consume the claim (PR #250 claim-after-no-op-guards ordering rule),
    else it could starve a genuine block elsewhere in the fan-out."""
    _seed_baseline(tmp_path, [])
    (tmp_path / "fine.py").write_text(_lines(150), encoding="utf-8")
    _seed_marker(tmp_path, "sid-A", "fine.py")
    result = _run_gate(tmp_path, session_id="sid-A")
    assert result.stdout.strip() == ""
    assert not _claim_path(tmp_path, "sid-A").exists(), (
        "pass-path invocation must not create the claim"
    )
