"""Worktree-aware end-to-end tests for the track_context_cost.py Stop hook.

Split out of test_track_context_cost.py, which had reached the 300-line
size guideline (context-cost-meter, adding external-review regression
coverage pushed it over). These two tests share the main_and_worktree
fixture and nothing else from the rest of that file.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from hooks import track_context_cost  # noqa: E402
from lib import iterate_phase_groups as ipg  # noqa: E402
from lib.worktree_isolation import write_run_pointer  # noqa: E402

_T0 = datetime(2026, 8, 7, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def main_and_worktree(tmp_path, monkeypatch):
    """A real MAIN repo + one linked worktree, mirroring an active iterate.

    Doubt-review finding: neither seam (writer's project root, writer's
    run id) that decides whether phase attribution and the F5b fold actually
    work was exercised by any existing test -- each ran the writer against a
    bare ``tmp_path`` with no git repo and no active-run pointer, which
    degrades to exactly the same "unphased, unknown run" output whether the
    resolution logic is right or wrong. This fixture gives a test something
    that can actually tell the difference.
    """
    main = tmp_path / "main"
    main.mkdir()
    env = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@test.invalid",
           "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@test.invalid"}
    subprocess.run(["git", "init", "--quiet", "-b", "main", str(main)],
                    check=True, env=env)
    (main / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(main), "add", "-A"], check=True, env=env)
    subprocess.run(["git", "-C", str(main), "commit", "-m", "init", "--quiet"],
                    check=True, env=env)
    worktree = main / ".worktrees" / "ctx-cost"
    subprocess.run(
        ["git", "-C", str(main), "worktree", "add", str(worktree),
         "-b", "iterate/ctx-cost", "main"],
        check=True, env=env, capture_output=True,
    )
    (worktree / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8"
    )
    monkeypatch.chdir(main)  # a Stop subprocess's cwd is the MAIN repo
    return main, worktree


def _out_path(project_root: Path, session_id: str) -> Path:
    return project_root / ".shipwright" / "compliance" / "context-cost" / f"{session_id}.json"


def test_hook_writes_to_the_active_worktree_and_attributes_a_phase(
    main_and_worktree, monkeypatch
):
    # Doubt-review HIGH 1 + HIGH 2, exercised together end to end: cwd is the
    # MAIN repo (main_and_worktree fixture chdir's there, matching a real Stop
    # subprocess), SHIPWRIGHT_PROJECT_ROOT is unset (matching that this
    # process class never receives it), yet with a real active-run pointer
    # and a real phase mark the hook must still land its write in the
    # WORKTREE (where finalize_iterate's F5b fold reads from) and attribute
    # the call to the "build" phase rather than "unphased".
    main, worktree = main_and_worktree
    monkeypatch.delenv("SHIPWRIGHT_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)
    run_id = "iterate-2026-08-07-ctx-cost-e2e"
    session_id = "sess-e2e"
    write_run_pointer(
        main, run_id=run_id, slug="ctx-cost", branch="iterate/ctx-cost",
        worktree_path=worktree, session_id=session_id,
    )
    ipg.append_mark(worktree, run_id, "build", ts=_T0.isoformat())

    transcript = worktree / "transcript.jsonl"
    record = {
        "type": "assistant",
        "requestId": "req-e2e",
        "timestamp": (_T0 + timedelta(minutes=5)).isoformat(),
        "message": {"model": "claude-sonnet-5", "usage": {"input_tokens": 1000}},
    }
    transcript.write_text(json.dumps(record) + "\n", encoding="utf-8")
    payload = {"session_id": session_id, "transcript_path": str(transcript)}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    rc = track_context_cost.main()

    assert rc == 0
    out = _out_path(worktree, session_id)
    assert out.exists(), "hook wrote to main instead of the active worktree"
    assert not _out_path(main, session_id).exists()
    summary = json.loads(out.read_text(encoding="utf-8"))
    assert summary["calls"] == 1
    assert "build" in summary["by_phase"], (
        f"call was not attributed to the build phase: {summary['by_phase']!r}"
    )
    assert "unphased" not in summary["by_phase"]


def test_hook_never_misattributes_to_a_stale_finished_runs_marks(
    main_and_worktree, monkeypatch
):
    # Doubt-review residual on the HIGH 1 fix: resolve_run_id's OTHER
    # fallbacks (shipwright_run_config.json::run_id, latest run_started
    # event) are project-global and can outlive the run that minted them --
    # unlike the per-session pointer, nothing prunes them when that run
    # finishes. If the hook used one of those, a LATER unrelated session in
    # the same tree (marks sidecars are gitignored, not deleted; a worktree
    # retained after its PR merges still looks live) would see every call as
    # later than every one of the finished run's marks and misattribute it
    # to that run's LAST phase -- AC-5 violated verbatim. This is the
    # realistic shape: an operator (or a resumed session) working directly
    # in a leftover iterate worktree, with no active pointer for THIS
    # session, but a stale run_id + real marks left behind by a PRIOR
    # session that once worked there.
    main, worktree = main_and_worktree
    monkeypatch.chdir(worktree)  # cwd is the leftover worktree itself, not main
    monkeypatch.delenv("SHIPWRIGHT_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)
    stale_run_id = "iterate-2026-07-01-a-finished-run"
    (worktree / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "run_id": stale_run_id}), encoding="utf-8"
    )
    ipg.append_mark(worktree, stale_run_id, "scope", ts=_T0.isoformat())
    ipg.append_mark(
        worktree, stale_run_id, "finalize", ts=(_T0 + timedelta(minutes=1)).isoformat()
    )

    session_id = "sess-unrelated-later"
    transcript = worktree / "transcript.jsonl"
    record = {
        "type": "assistant",
        "requestId": "req-unrelated",
        # Long after the stale run's last mark -- the exact shape a later,
        # unrelated session's calls would have.
        "timestamp": (_T0 + timedelta(days=7)).isoformat(),
        "message": {"model": "claude-sonnet-5", "usage": {"input_tokens": 1000}},
    }
    transcript.write_text(json.dumps(record) + "\n", encoding="utf-8")
    payload = {"session_id": session_id, "transcript_path": str(transcript)}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    rc = track_context_cost.main()

    assert rc == 0
    summary = json.loads(_out_path(worktree, session_id).read_text(encoding="utf-8"))
    assert summary["calls"] == 1
    assert "finalize" not in summary["by_phase"], (
        f"call was misattributed to the stale run's last phase: {summary['by_phase']!r}"
    )
    assert "unphased" in summary["by_phase"]
