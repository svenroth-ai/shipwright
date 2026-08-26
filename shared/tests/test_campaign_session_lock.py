"""Unit + CLI tests for lib.campaign_session_lock.

Covers the exact scenario campaign-worktree.md's "No cross-session lock" known
limitation named: two orchestrator sessions on the same campaign slug reach
the same shared worktree. A second, DIFFERENT session must be refused while
the first is live, and must succeed once the first has gone stale (else a
crashed session blocks the campaign permanently).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from lib import campaign_session_lock as csl
from lib.file_lock import LockTimeout

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLI = _REPO_ROOT / "shared" / "scripts" / "checks" / "check_campaign_session_lock.py"

_spec = importlib.util.spec_from_file_location("check_campaign_session_lock_for_test", _CLI)
assert _spec is not None and _spec.loader is not None
check_campaign_session_lock = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_campaign_session_lock)


def test_first_acquire_succeeds(tmp_path):
    status = csl.acquire(tmp_path, session_id="sess-a")
    assert status.owner_session_id == "sess-a"
    assert status.acquired_at == status.last_touch


def test_same_session_reacquire_renews_without_new_acquired_at(tmp_path, monkeypatch):
    monkeypatch.setattr(csl, "_now", lambda: 1000.0)
    first = csl.acquire(tmp_path, session_id="sess-a")

    monkeypatch.setattr(csl, "_now", lambda: 1050.0)
    second = csl.acquire(tmp_path, session_id="sess-a")

    assert second.acquired_at == first.acquired_at == 1000.0
    assert second.last_touch == 1050.0


def test_different_session_rejected_while_lock_is_fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(csl, "_now", lambda: 1000.0)
    csl.acquire(tmp_path, session_id="sess-a")

    monkeypatch.setattr(csl, "_now", lambda: 1010.0)  # 10s later, well inside default
    with pytest.raises(csl.CampaignLockError, match="sess-a"):
        csl.acquire(tmp_path, session_id="sess-b")


def test_different_session_reclaims_a_stale_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(csl, "_now", lambda: 1000.0)
    csl.acquire(tmp_path, session_id="sess-a", stale_after_seconds=100.0)

    monkeypatch.setattr(csl, "_now", lambda: 1200.0)  # 200s later, past the 100s threshold
    status = csl.acquire(tmp_path, session_id="sess-b", stale_after_seconds=100.0)

    assert status.owner_session_id == "sess-b"
    assert status.acquired_at == 1200.0


def test_touch_refreshes_last_touch_for_the_owner(tmp_path, monkeypatch):
    monkeypatch.setattr(csl, "_now", lambda: 1000.0)
    acquired = csl.acquire(tmp_path, session_id="sess-a")

    monkeypatch.setattr(csl, "_now", lambda: 1500.0)
    touched = csl.touch(tmp_path, session_id="sess-a")

    assert touched.acquired_at == acquired.acquired_at
    assert touched.last_touch == 1500.0


def test_touch_by_a_non_owner_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(csl, "_now", lambda: 1000.0)
    csl.acquire(tmp_path, session_id="sess-a")

    monkeypatch.setattr(csl, "_now", lambda: 1010.0)
    with pytest.raises(csl.CampaignLockError, match="sess-a"):
        csl.touch(tmp_path, session_id="sess-b")


def test_touch_with_no_lock_at_all_raises(tmp_path):
    """Distinct message from the wrong-owner case (doubt-reviewer,
    iterate-2026-08-26-campaign-worktree-guard-followups): "reclaimed as
    stale" is false when nothing was ever acquired here, and the operator's
    documented delete-remedy relies on THIS message telling them to
    `acquire`, not on the wrong-owner wording."""
    with pytest.raises(csl.CampaignLockError, match="nothing to renew") as exc_info:
        csl.touch(tmp_path, session_id="sess-a")
    assert "reclaimed as stale" not in str(exc_info.value)


def test_touch_by_a_non_owner_still_says_reclaimed_as_stale(tmp_path, monkeypatch):
    """The genuinely-reclaimed case keeps its own distinct wording."""
    monkeypatch.setattr(csl, "_now", lambda: 1000.0)
    csl.acquire(tmp_path, session_id="sess-a")

    monkeypatch.setattr(csl, "_now", lambda: 1010.0)
    with pytest.raises(csl.CampaignLockError, match="reclaimed as stale"):
        csl.touch(tmp_path, session_id="sess-b")


def test_release_removes_the_lock_the_session_holds(tmp_path):
    csl.acquire(tmp_path, session_id="sess-a")
    csl.release(tmp_path, session_id="sess-a")

    state_path = tmp_path / ".shipwright" / csl.LOCK_STATE_FILENAME
    assert not state_path.exists()
    # released cleanly => a brand-new session_id can acquire immediately,
    # not just the same one:
    status = csl.acquire(tmp_path, session_id="sess-b")
    assert status.owner_session_id == "sess-b"


def test_release_by_a_non_owner_is_a_no_op(tmp_path):
    csl.acquire(tmp_path, session_id="sess-a")
    csl.release(tmp_path, session_id="sess-b")  # does not raise

    state_path = tmp_path / ".shipwright" / csl.LOCK_STATE_FILENAME
    assert state_path.exists()
    assert json.loads(state_path.read_text())["session_id"] == "sess-a"


def test_release_with_no_lock_at_all_is_a_no_op(tmp_path):
    csl.release(tmp_path, session_id="sess-a")  # does not raise


def test_release_requires_a_session_id(tmp_path):
    with pytest.raises(csl.CampaignLockError):
        csl.release(tmp_path, session_id="")


def test_acquire_requires_a_session_id(tmp_path):
    with pytest.raises(csl.CampaignLockError):
        csl.acquire(tmp_path, session_id="")


def test_touch_requires_a_session_id(tmp_path):
    with pytest.raises(csl.CampaignLockError):
        csl.touch(tmp_path, session_id="")


@pytest.mark.parametrize("bad", [float("nan"), float("-inf"), -1.0, "not-a-number", True])
def test_acquire_rejects_a_non_finite_or_negative_stale_after_seconds(tmp_path, bad):
    """NaN would make every `age <= stale_after_seconds` comparison False,
    silently disabling the staleness guard (every acquire would reclaim,
    split-brain, no diagnostic) — mirrors lib.file_lock._validated_timeout."""
    with pytest.raises(csl.CampaignLockError):
        csl.acquire(tmp_path, session_id="sess-a", stale_after_seconds=bad)


def test_state_file_missing_acquired_at_is_treated_as_no_lock_held(tmp_path):
    """A partially-corrupt state file (external tampering, not this module's
    own writer — durable_atomic_write makes a torn write from acquire/touch
    impossible) must fall back to "no lock held", not raise a KeyError.

    Must reacquire under the SAME session_id the corrupted file already
    names: that is the only path that reads `existing["acquired_at"]" (the
    `same_owner` arm) — a different session_id takes the stale-reclaim
    branch and never touches the missing field, so it would pass even
    without the `_load` fix this test exists to pin.
    """
    state_path = tmp_path / ".shipwright" / csl.LOCK_STATE_FILENAME
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"session_id": "sess-a", "last_touch": 1000.0}))

    status = csl.acquire(tmp_path, session_id="sess-a")

    assert status.owner_session_id == "sess-a"
    assert status.acquired_at == status.last_touch  # a FRESH lock, not a resumed one


def test_state_file_missing_acquired_at_touch_is_treated_as_no_lock_held(tmp_path):
    """Same corruption, the `touch` call site (`existing["acquired_at"]` in its
    return) named by the same finding."""
    state_path = tmp_path / ".shipwright" / csl.LOCK_STATE_FILENAME
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"session_id": "sess-a", "last_touch": 1000.0}))

    with pytest.raises(csl.CampaignLockError):
        csl.touch(tmp_path, session_id="sess-a")


# --- CLI (subprocess) -------------------------------------------------------


def _cli(*args):
    return subprocess.run(
        [sys.executable, str(_CLI), *args],
        capture_output=True, text=True,
    )


_RACE_SNIPPET = """
import json, sys, time
from pathlib import Path
sys.path.insert(0, {shared_scripts!r})
from lib import campaign_session_lock as csl

campaign_wt, session_id, ready_file, go_file, out_file = (
    Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5]))
ready_file.write_text("1")
while not go_file.exists():
    time.sleep(0.001)
try:
    status = csl.acquire(campaign_wt, session_id=session_id)
    out_file.write_text(json.dumps({{"ok": True, "session_id": status.owner_session_id}}))
except csl.CampaignLockError as exc:
    out_file.write_text(json.dumps({{"ok": False, "detail": str(exc)}}))
""".format(shared_scripts=str(_REPO_ROOT / "shared" / "scripts"))


def test_concurrent_acquire_by_different_sessions_has_exactly_one_winner(tmp_path):
    """A genuine rendezvous, not merely concurrent process launch: each of 8
    racer processes calls acquire() directly (no CLI layer) only after ALL 8
    have signalled they are parked at the barrier, so every round forces real
    overlap inside the file_lock-guarded critical section rather than relying
    on subprocess-startup jitter to (maybe) produce one. Even so this is a
    PROBABILISTIC detector, not a proof of serialization — repeated across 5
    independent rounds so a broken critical section is very unlikely to win
    every round by luck (doubt-reviewer,
    iterate-2026-08-26-campaign-worktree-guard-followups: the prior version
    had no rendezvous and no repetition, so it could pass identically whether
    or not file_lock actually serialized anything)."""
    session_ids = [f"sess-{i}" for i in range(8)]
    for round_idx in range(5):
        round_dir = tmp_path / f"round-{round_idx}"
        round_dir.mkdir()
        go_file = round_dir / "go"
        ready_files = [round_dir / f"ready-{i}" for i in range(len(session_ids))]
        out_files = [round_dir / f"out-{i}.json" for i in range(len(session_ids))]

        procs = [
            subprocess.Popen([
                sys.executable, "-c", _RACE_SNIPPET, str(round_dir), sid,
                str(ready_files[i]), str(go_file), str(out_files[i]),
            ])
            for i, sid in enumerate(session_ids)
        ]
        deadline = time.time() + 10
        while not all(f.exists() for f in ready_files):
            assert time.time() < deadline, "a racer never reached the rendezvous"
            time.sleep(0.01)
        go_file.write_text("go")  # release all 8 racers at (as close to) once as we can get
        for p in procs:
            assert p.wait(timeout=10) == 0, round_idx

        results = [json.loads(f.read_text()) for f in out_files]
        allowed = [r for r in results if r["ok"]]
        blocked = [r for r in results if not r["ok"]]
        assert len(allowed) == 1, (round_idx, results)
        assert len(blocked) == len(session_ids) - 1
        winner = allowed[0]["session_id"]
        for r in blocked:
            assert winner in r["detail"]


def test_cli_acquire_then_reject_then_stale_reclaim(tmp_path):
    r1 = _cli("acquire", "--campaign-worktree", str(tmp_path),
               "--session-id", "sess-a", "--json")
    assert r1.returncode == 0, r1.stdout + r1.stderr
    assert json.loads(r1.stdout)["decision"] == "allow"

    r2 = _cli("acquire", "--campaign-worktree", str(tmp_path),
               "--session-id", "sess-b", "--stale-after-seconds", "9999", "--json")
    assert r2.returncode == 1
    assert json.loads(r2.stdout)["decision"] == "block"

    r3 = _cli("acquire", "--campaign-worktree", str(tmp_path),
               "--session-id", "sess-b", "--stale-after-seconds", "0", "--json")
    assert r3.returncode == 0, r3.stdout + r3.stderr
    assert json.loads(r3.stdout)["decision"] == "allow"


def test_cli_touch_exit_codes(tmp_path):
    acquired = _cli("acquire", "--campaign-worktree", str(tmp_path),
                     "--session-id", "sess-a", "--json")
    assert acquired.returncode == 0

    ok = _cli("touch", "--campaign-worktree", str(tmp_path),
              "--session-id", "sess-a", "--json")
    assert ok.returncode == 0

    bad = _cli("touch", "--campaign-worktree", str(tmp_path),
               "--session-id", "sess-other", "--json")
    assert bad.returncode == 1
    assert json.loads(bad.stdout)["decision"] == "block"


def test_cli_rejects_an_empty_session_id(tmp_path):
    for command in ("acquire", "touch"):
        result = _cli(command, "--campaign-worktree", str(tmp_path),
                       "--session-id", "", "--json")
        assert result.returncode == 1, result.stdout
        assert json.loads(result.stdout)["decision"] == "block"


def test_cli_rejects_a_nan_stale_after_seconds(tmp_path):
    result = _cli("acquire", "--campaign-worktree", str(tmp_path),
                   "--session-id", "sess-a", "--stale-after-seconds", "nan", "--json")
    assert result.returncode == 1, result.stdout
    assert json.loads(result.stdout)["decision"] == "block"


def test_cli_release_then_a_new_session_id_can_acquire(tmp_path):
    acquired = _cli("acquire", "--campaign-worktree", str(tmp_path),
                     "--session-id", "sess-a", "--json")
    assert acquired.returncode == 0

    released = _cli("release", "--campaign-worktree", str(tmp_path),
                     "--session-id", "sess-a", "--json")
    assert released.returncode == 0, released.stdout
    assert json.loads(released.stdout)["decision"] == "allow"

    reacquired = _cli("acquire", "--campaign-worktree", str(tmp_path),
                       "--session-id", "sess-b", "--json")
    assert reacquired.returncode == 0, reacquired.stdout


def test_cli_plain_invocation_without_json_prints_a_verdict_line(tmp_path):
    """The invocation shape both docs actually prescribe (no --json, verdict
    to stdout/stderr) — every other test passes --json, so this shape was
    otherwise untested (doubt-reviewer, iterate-2026-08-26-campaign-worktree-
    guard-followups)."""
    ok = _cli("acquire", "--campaign-worktree", str(tmp_path), "--session-id", "sess-a")
    assert ok.returncode == 0
    assert "check_campaign_session_lock acquire: ALLOW" in ok.stdout

    blocked = _cli("acquire", "--campaign-worktree", str(tmp_path), "--session-id", "sess-b")
    assert blocked.returncode == 1
    assert "check_campaign_session_lock acquire: BLOCK" in blocked.stdout
    assert "sess-a" in blocked.stderr


def test_cli_reason_field_discriminates_refused_from_io_error(tmp_path, monkeypatch, capsys):
    """A genuine lock-state refusal (CampaignLockError) must never be
    reported the same way as an infrastructure failure (LockTimeout,
    OSError) — the wrong one tells an operator to delete a state file over a
    problem deleting it cannot fix."""
    args = check_campaign_session_lock.argparse.Namespace(
        command="acquire", campaign_worktree=str(tmp_path), session_id="sess-a", json=True,
        stale_after_seconds=csl.DEFAULT_STALE_AFTER_SECONDS,
    )
    monkeypatch.setattr(check_campaign_session_lock.argparse.ArgumentParser, "parse_args",
                         lambda self, argv=None: args)

    monkeypatch.setattr(check_campaign_session_lock, "acquire",
                         lambda *a, **k: (_ for _ in ()).throw(csl.CampaignLockError("x")))
    check_campaign_session_lock.main([])
    assert json.loads(capsys.readouterr().out)["reason"] == "refused"

    monkeypatch.setattr(check_campaign_session_lock, "acquire",
                         lambda *a, **k: (_ for _ in ()).throw(LockTimeout("timed out")))
    check_campaign_session_lock.main([])
    assert json.loads(capsys.readouterr().out)["reason"] == "io_error"

    monkeypatch.setattr(check_campaign_session_lock, "acquire",
                         lambda *a, **k: (_ for _ in ()).throw(OSError("disk trouble")))
    check_campaign_session_lock.main([])
    assert json.loads(capsys.readouterr().out)["reason"] == "io_error"
