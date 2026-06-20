"""Integration: bloat-gate Stop hook fan-out emits exactly one block.

`cross_component` integration coverage (category:"integration") for
iterate-2026-06-20-bloat-gate-stop-fanout-dedup. Claude Code fires every
enabled plugin's Stop hooks with no active-plugin filter, so the bloat gate —
registered in all 12 plugins — runs 12× per Stop. Before the
`claim_once_for_event` guard, each invocation that found offenders emitted the
same block, so a single stop showed 12 identical "Stop hook feedback" blocks
(webui session bfd244ca, 2026-06-20). This suite drives the ACTUAL hook script
across a simulated 12-plugin fan-out in a real git project and proves the
register-everywhere hook + the once-per-(event, session) claim COMPOSE:

- exactly one block across the fan-out (sequential AND parallel: claim atomicity)
- the claim is per (event, session): a second session still blocks once.

Lives in integration-tests/ (a CI-run root) per ADR-044, in its own module so
test_hook_fanout_consolidation.py stays at its bloat baseline.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
BLOAT_HOOK = _REPO_ROOT / "shared" / "scripts" / "hooks" / "bloat_gate_on_stop.py"

import pytest  # noqa: E402

# All 12 hooks-bearing plugins — the Stop fan-out width.
ALL_PLUGINS = [
    "shipwright-project", "shipwright-design", "shipwright-plan",
    "shipwright-build", "shipwright-test", "shipwright-security",
    "shipwright-deploy", "shipwright-changelog", "shipwright-compliance",
    "shipwright-iterate", "shipwright-adopt", "shipwright-run",
]


@pytest.fixture
def git_project(tmp_path: Path) -> Path:
    project = tmp_path / "app"
    project.mkdir()
    for cmd in (["git", "init", "-b", "main"],
                ["git", "-c", "user.email=t@t", "-c", "user.name=t",
                 "commit", "--allow-empty", "-m", "init"]):
        r = subprocess.run(cmd, cwd=str(project), capture_output=True,
                           encoding="utf-8")
        # Fail loudly on a broken git setup so AC-5 stays a real git-backed
        # scenario rather than silently degrading to a cwd-fallback run.
        assert r.returncode == 0, f"git setup failed ({cmd}): {r.stderr}"
    return project


def _seed_block(project: Path, session_id: str) -> None:
    """Seed a baseline + marker + oversize file so the gate BLOCKS (new crossing)."""
    (project / "offender.py").write_text("x\n" * 320, encoding="utf-8")  # > 300
    (project / "shipwright_bloat_baseline.json").write_text(  # parses, offender absent
        json.dumps({"version": 1, "entries": []}), encoding="utf-8")
    locks = project / ".shipwright" / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    (locks / f"bloat_pending.{session_id}.json").write_text(json.dumps({
        "version": 1,
        "entries": [{
            "path": "offender.py", "now": 320, "limit": 300,
            "classification": "source", "was_in_allowlist": False,
            "delta": "crossing",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }],
    }), encoding="utf-8")


def _fire(project: Path, *, plugin: str, session_id: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["SHIPWRIGHT_SESSION_ID"] = session_id
    env["CLAUDE_PLUGIN_ROOT"] = str(Path("/fake/plugins") / plugin)
    return subprocess.run(
        [sys.executable, str(BLOAT_HOOK)],
        input="{}", capture_output=True, text=True,
        encoding="utf-8", errors="replace", cwd=str(project), env=env,
    )


def _fanout(project, session_id, *, parallel=False):
    if not parallel:
        return [_fire(project, plugin=p, session_id=session_id) for p in ALL_PLUGINS]
    with ThreadPoolExecutor(max_workers=len(ALL_PLUGINS)) as ex:
        return list(ex.map(
            lambda p: _fire(project, plugin=p, session_id=session_id), ALL_PLUGINS))


def _blocks(results) -> list:
    out = []
    for r in results:
        raw = r.stdout.strip()
        if raw and json.loads(raw).get("decision") == "block":
            out.append(r)
    return out


def _assert_one_block_rest_empty(results) -> subprocess.CompletedProcess:
    """Exactly one invocation blocks; every other (claim-loser) emits the empty
    pass — a broken dedup emitting 1 block + N non-empty passes must fail here."""
    blocked = _blocks(results)
    assert len(blocked) == 1, [r.stdout for r in results]
    losers = [r for r in results if r not in blocked]
    assert all(r.stdout.strip() == "" for r in losers), [r.stdout for r in losers]
    return blocked[0]


def test_bloat_gate_fanout_blocks_once(git_project: Path):
    _seed_block(git_project, "sess-bloat")
    results = _fanout(git_project, "sess-bloat")
    assert all(r.returncode == 0 for r in results), [r.stderr for r in results]
    winner = _assert_one_block_rest_empty(results)
    reason = json.loads(winner.stdout)["reason"]
    assert "offender.py" in reason and "IRON LAW" in reason.upper()


def test_bloat_gate_fanout_concurrent_one_blocker(git_project: Path):
    """Claim atomicity under PARALLEL fan-out — exactly one blocker, rest empty."""
    _seed_block(git_project, "sess-par")
    results = _fanout(git_project, "sess-par", parallel=True)
    assert all(r.returncode == 0 for r in results), [r.stderr for r in results]
    _assert_one_block_rest_empty(results)


def test_bloat_gate_fanout_per_session_independent(git_project: Path):
    """The claim is per (event, session): a second session still blocks once."""
    _seed_block(git_project, "sess-one")
    _seed_block(git_project, "sess-two")
    assert len(_blocks(_fanout(git_project, "sess-one"))) == 1
    assert len(_blocks(_fanout(git_project, "sess-two"))) == 1
