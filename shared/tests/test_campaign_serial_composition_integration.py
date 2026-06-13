"""END-TO-END composition test for the interleaved-serial campaign loop
(iterate-2026-06-13-campaign-serial-default).

The whole point of interleaved-serial is that sibling sub-iterates COMPOSE
through prior merges: sub-iterate N+1 must start from a tree that already
contains sub-iterate N's merged change — NOT from a possibly-stale local main
(build-all-then-drain, by contrast, never let siblings see each other). This
proves it on REAL git: S1 changes a shared file and its PR lands on origin/main,
while the orchestrator's LOCAL main stays at the old commit; S2's serial base
(resolved by autonomous_loop.cmd_next) then SEES S1's change anyway, because the
serial strategy branches off the FRESH remote default ref.

This is the cross_component integration coverage (category:"integration") for the
serial-strategy change to the shared autonomous_loop state machine. Real-git via
the `git_origin_repo` conftest fixture; NOT marked slow so it gates in CI
(mirrors test_parallel_merge_cascade_integration).
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from autonomous_loop import cmd_init, cmd_next, cmd_record

SHARED = "shared.txt"


class _Args:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, check=True,
    )


def _next(state_path: Path) -> dict:
    """Run cmd_next and return its parsed stdout JSON."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cmd_next(_Args(state=str(state_path)))
    assert rc == 0, buf.getvalue()
    return json.loads(buf.getvalue())


def test_serial_subiterate_composes_on_prior_merge(git_origin_repo, monkeypatch):
    work, _origin = git_origin_repo
    monkeypatch.chdir(work)
    _git(work, "config", "user.email", "t@test.invalid")
    _git(work, "config", "user.name", "T")

    # Shared file on main = v0, pushed to origin. Capture the stale-main sha.
    (work / SHARED).write_text("v0\n", encoding="utf-8")
    _git(work, "add", SHARED)
    _git(work, "commit", "-m", "shared v0")
    _git(work, "push", "origin", "main")
    v0_sha = _git(work, "rev-parse", "main").stdout.strip()

    # Init a serial campaign loop with two sub-iterates.
    units = work / "units.json"
    units.write_text(json.dumps({"sub_iterates": [
        {"id": "S1", "slug": "alpha", "spec_path": "s1.md"},
        {"id": "S2", "slug": "bravo", "spec_path": "s2.md"},
    ]}), encoding="utf-8")
    state = work / ".shipwright" / "loop_state.json"
    assert cmd_init(_Args(
        state=str(state), units_from=str(units), kind="sub_iterate",
        branch_strategy="serial", root_session_id="root",
    )) == 0

    # --- S1: next hands back the FRESH remote default ref as the base ---
    out1 = _next(state)
    assert out1["id"] == "S1"
    assert out1["base_branch"] == "origin/main", out1

    # Runner simulation: branch off the serial base, change the shared file, and
    # land the PR on origin/main — WITHOUT advancing the orchestrator's LOCAL main.
    _git(work, "checkout", "-b", "iterate/s1", out1["base_branch"])
    (work / SHARED).write_text("v1-from-S1\n", encoding="utf-8")
    _git(work, "add", SHARED)
    _git(work, "commit", "-m", "S1: shared v1")
    sha1 = _git(work, "rev-parse", "HEAD").stdout.strip()
    _git(work, "push", "origin", "iterate/s1:main")   # PR lands on origin/main

    assert cmd_record(_Args(state=str(state), unit="S1", result=json.dumps({
        "status": "complete", "commit": sha1, "tests_passed": 1, "tests_total": 1,
        "branch": "iterate/s1",
    }))) == 0

    # Local main is deliberately STALE (still v0) — interleaved-serial must NOT
    # depend on it. The serial base is the fresh remote ref instead.
    assert _git(work, "rev-parse", "main").stdout.strip() == v0_sha

    # --- S2: next re-fetches; the serial base now contains S1's merged change ---
    out2 = _next(state)
    assert out2["id"] == "S2"
    assert out2["base_branch"] == "origin/main", out2

    # COMPOSITION: branch S2 off the serial base and assert it SEES S1's change,
    # even though local main never moved.
    _git(work, "checkout", "-b", "iterate/s2", out2["base_branch"])
    composed = (work / SHARED).read_text(encoding="utf-8")
    assert composed == "v1-from-S1\n", (
        f"S2 must start from a tree containing S1's merged change (composition); "
        f"got {composed!r}. Local main stayed at v0, so this proves the serial "
        f"base used the FRESH origin/main, not a stale local main."
    )
