"""Fan-out dedup for aggregate_triage_on_stop.py.

The hook is registered in every plugin, so one Stop event fires it ~12×. Each
invocation unconditionally regenerates the gitignored ``triage_inbox.md`` derived
cache (a non-atomic ``write_text``), so a single stop did ~11 redundant
regenerations. The once-per-(Stop, session) claim collapses that to one.

Deterministic reproduction of the fan-out without true concurrency: run the hook,
delete the output, run it again in the same (session, dir). With the guard the
second invocation is a claim-loser and does NOT recreate the file; without it the
file reappears. Own module so test_stop_hooks_write_runtime.py stays at baseline.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / "shared" / "scripts" / "hooks" / "aggregate_triage_on_stop.py"


def _seed_project(root: Path) -> None:
    (root / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete",
                    "completed_steps": ["project", "plan", "build"]}),
        encoding="utf-8")
    sw = root / ".shipwright"
    sw.mkdir(parents=True, exist_ok=True)
    (sw / "triage.jsonl").write_text("", encoding="utf-8")
    (root / "shipwright_events.jsonl").write_text("", encoding="utf-8")


def _run(root: Path, session_id: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["SHIPWRIGHT_PROJECT_ROOT"] = str(root)
    env["SHIPWRIGHT_SESSION_ID"] = session_id
    return subprocess.run(
        [sys.executable, str(HOOK)], input="{}", cwd=str(root), env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def _inbox(root: Path) -> Path:
    return root / ".shipwright" / "agent_docs" / "runtime" / "triage_inbox.md"


def _claim(root: Path, session_id: str) -> Path:
    return root / ".shipwright" / ".cache" / f"stop-triage-inbox-{session_id}.claim"


def test_fanout_dedup_regenerates_once(tmp_path):
    """AC-1: first invocation regenerates; the second (claim-loser within TTL)
    does NOT — proving one regen per (Stop, session) instead of one-per-plugin.
    Also pins the regen/skip stderr diagnostics (the test + observability hook)."""
    _seed_project(tmp_path)
    r1 = _run(tmp_path, "sid-A")
    assert r1.returncode == 0, r1.stderr
    assert "[aggregate_triage_on_stop] regenerated" in r1.stderr
    assert _inbox(tmp_path).is_file(), f"first run did not regenerate: {r1.stderr}"
    _inbox(tmp_path).unlink()
    r2 = _run(tmp_path, "sid-A")
    assert r2.returncode == 0, r2.stderr
    assert "fan-out dedup" in r2.stderr and "skipped" in r2.stderr
    assert not _inbox(tmp_path).exists(), (
        "claim-loser regenerated the cache (no fan-out dedup)"
    )


def test_failed_regen_releases_claim(tmp_path):
    """A winner whose regen FAILS must release the claim so a sibling fan-out
    invocation (or a later stop) can retry — else triage_inbox.md is starved for
    the whole event/TTL window (external review gpt#1)."""
    _seed_project(tmp_path)
    # Force the regen to fail: create runtime/ as a FILE so ``rt.mkdir`` raises.
    agent_docs = tmp_path / ".shipwright" / "agent_docs"
    agent_docs.mkdir(parents=True, exist_ok=True)
    blocker = agent_docs / "runtime"
    blocker.write_text("x", encoding="utf-8")
    r1 = _run(tmp_path, "sid-A")
    assert r1.returncode == 0  # observability hook never blocks
    assert not _inbox(tmp_path).exists()  # regen failed
    assert not _claim(tmp_path, "sid-A").exists(), (
        "a failed regen must RELEASE the claim, not starve siblings"
    )
    # Unblock + retry the SAME session → regenerates (the claim was released).
    blocker.unlink()
    assert _run(tmp_path, "sid-A").returncode == 0
    assert _inbox(tmp_path).is_file(), "retry after a failed winner must regenerate"


def test_fanout_dedup_is_per_session(tmp_path):
    """AC-2: the claim is per (event, session); a second session regenerates."""
    _seed_project(tmp_path)
    assert _run(tmp_path, "sid-A").returncode == 0
    assert _inbox(tmp_path).is_file()
    _inbox(tmp_path).unlink()
    r = _run(tmp_path, "sid-B")
    assert r.returncode == 0
    claims = sorted(p.name for p in (tmp_path / ".shipwright" / ".cache").glob("*")) \
        if (tmp_path / ".shipwright" / ".cache").exists() else []
    assert _inbox(tmp_path).is_file(), (
        f"a distinct session must regenerate; sid-B stderr={r.stderr!r} claims={claims}"
    )


def test_non_shipwright_project_no_claim(tmp_path):
    """AC-4: a non-Shipwright (pass-path) invocation no-ops and never claims."""
    # No run_config -> not a Shipwright project -> hook returns before the claim.
    r = _run(tmp_path, "sid-A")
    assert r.returncode == 0
    assert not _inbox(tmp_path).exists()
    assert not _claim(tmp_path, "sid-A").exists(), (
        "pass-path invocation must not create the claim"
    )
