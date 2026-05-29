"""Anti-ratchet must clear when a baselined file is trimmed back.

Bug (2026-05-29): ``bloat_gate_on_stop.py::_re_measure_oversize`` checked the
live file size only against the 300 ``limit``, never against the baseline
``current``. The canonical anti-ratchet definition (constitution + the
pre-commit ``anti_ratchet.py``) is "an existing baseline entry growing PAST its
``current``". So a grandfathered file that was transiently over its baseline and
then correctly trimmed back to <= ``current`` (but still over 300) kept blocking
the Stop as a false-positive — the record_event.py 799->792 case.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "hooks"
_GATE = HOOKS_DIR / "bloat_gate_on_stop.py"


def _lines(n: int) -> str:
    return "x\n" * n


def _run_gate(cwd: Path, session_id: str = "sid-A") -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["SHIPWRIGHT_SESSION_ID"] = session_id
    return subprocess.run(
        [sys.executable, str(_GATE)], input="{}", capture_output=True, text=True,
        encoding="utf-8", errors="replace", cwd=str(cwd), env=env,
    )


def _seed_baseline(cwd: Path, path: str, current: int) -> None:
    (cwd / "shipwright_bloat_baseline.json").write_text(
        json.dumps({"version": 1, "entries": [
            {"path": path, "limit": 300, "current": current,
             "state": "grandfathered", "adr": None},
        ]}), encoding="utf-8")


def _seed_marker(cwd: Path, sid: str, path: str, now: int) -> None:
    locks = cwd / ".shipwright" / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    import time
    (locks / f"bloat_pending.{sid}.json").write_text(json.dumps({"version": 1, "entries": [{
        "path": path, "now": now, "limit": 300, "classification": "source",
        "was_in_allowlist": True, "delta": "anti-ratchet",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }]}), encoding="utf-8")


def _decision(result) -> dict | None:
    raw = result.stdout.strip()
    return json.loads(raw) if raw else None


def test_anti_ratchet_clears_when_trimmed_to_baseline(tmp_path):
    """Trimmed back to <= baseline current (still >300) → must NOT block."""
    _seed_baseline(tmp_path, "legacy.py", 799)
    (tmp_path / "legacy.py").write_text(_lines(792), encoding="utf-8")
    _seed_marker(tmp_path, "sid-A", "legacy.py", now=792)
    decision = _decision(_run_gate(tmp_path))
    assert decision is None or decision.get("decision") != "block"


def test_anti_ratchet_clears_at_exactly_baseline(tmp_path):
    """Boundary: live == baseline current → cleared (not a ratchet)."""
    _seed_baseline(tmp_path, "legacy.py", 799)
    (tmp_path / "legacy.py").write_text(_lines(799), encoding="utf-8")
    _seed_marker(tmp_path, "sid-A", "legacy.py", now=799)
    decision = _decision(_run_gate(tmp_path))
    assert decision is None or decision.get("decision") != "block"


def test_anti_ratchet_blocks_when_above_baseline(tmp_path):
    """Grown PAST baseline current → still blocks (regression guard)."""
    _seed_baseline(tmp_path, "legacy.py", 799)
    (tmp_path / "legacy.py").write_text(_lines(810), encoding="utf-8")
    _seed_marker(tmp_path, "sid-A", "legacy.py", now=810)
    decision = _decision(_run_gate(tmp_path))
    assert decision is not None and decision.get("decision") == "block"
