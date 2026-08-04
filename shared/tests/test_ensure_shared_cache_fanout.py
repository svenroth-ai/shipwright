"""Unit contract for the stdlib-only SessionStart claim/barrier."""

from __future__ import annotations

import importlib.util
import os
import sys
import threading
import time
import types
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_HOOK = _REPO / "shared" / "templates" / "hooks" / "ensure_shared_cache.py"
_SPEC = importlib.util.spec_from_file_location("ensure_shared_cache_fanout", _HOOK)
assert _SPEC and _SPEC.loader
healer = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(healer)
lock_helper = importlib.import_module("cache_repair_lock")


def _claim(root: Path, sid: object, **kwargs):
    return healer._claim_session(root, sid, **kwargs)


def test_reader_acquire_requests_shared_lease(tmp_path: Path, monkeypatch):
    observed: list[tuple[Path, float, bool]] = []

    def acquire(path: Path, wait_seconds: float, *, exclusive: bool):
        observed.append((path, wait_seconds, exclusive))
        return 17

    monkeypatch.setattr(lock_helper, "_acquire_cache_lock", acquire)
    path = tmp_path / "lease"

    assert lock_helper.acquire_cache_read_lock(path, 0.25) == 17
    assert observed == [(path, 0.25, False)]


def test_windows_reader_unlock_uses_its_byte_offset(monkeypatch):
    calls: list[tuple[object, ...]] = []
    fake_msvcrt = types.ModuleType("msvcrt")
    fake_msvcrt.LK_UNLCK = 7
    fake_msvcrt.locking = lambda *args: calls.append(("locking", *args))
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
    monkeypatch.setattr(lock_helper.os, "name", "nt")
    monkeypatch.setattr(
        lock_helper.os, "lseek",
        lambda *args: calls.append(("lseek", *args)),
    )

    lock_helper.unlock_cache_lock((11, 4))

    assert calls == [
        ("lseek", 11, 4, os.SEEK_SET),
        ("locking", 11, 7, 1),
    ]


def test_claim_reader_rejects_missing_oversized_and_non_ascii_tokens(tmp_path: Path):
    missing = tmp_path / "missing.claim"
    oversized = tmp_path / "oversized.claim"
    non_ascii = tmp_path / "non-ascii.claim"
    oversized.write_bytes(b"a" * 65)
    non_ascii.write_bytes(b"\xff")

    assert lock_helper.read_claim_token(missing) is False
    assert lock_helper.read_claim_token(oversized) is None
    assert lock_helper.read_claim_token(non_ascii) is None


def test_opened_regular_rejects_metadata_errors(
    tmp_path: Path, monkeypatch,
):
    path = tmp_path / "claim"
    path.write_bytes(b"token")
    descriptor = os.open(path, os.O_RDONLY)
    try:
        monkeypatch.setattr(
            lock_helper.os, "fstat",
            lambda _descriptor: (_ for _ in ()).throw(OSError("denied")),
        )
        assert lock_helper._opened_regular_at_path(path, descriptor) is False
    finally:
        os.close(descriptor)


def test_completion_observer_reports_duplicate_and_open_failure(
    tmp_path: Path, monkeypatch,
):
    done = tmp_path / "generation.done"
    assert lock_helper.observe_completion(done, "participant") is True
    assert lock_helper.observe_completion(done, "participant") is False

    monkeypatch.setattr(
        lock_helper.os, "open",
        lambda *_args: (_ for _ in ()).throw(PermissionError("denied")),
    )
    assert lock_helper.observe_completion(done, "other-participant") is None


@pytest.mark.parametrize("session_id", [None, "", "unknown"])
def test_repair_state_rejects_invalid_identity(tmp_path: Path, session_id: object):
    assert lock_helper.session_repair_state(tmp_path, session_id) is None


def test_one_owner_and_waiter_returns_only_after_completion(tmp_path: Path):
    owner_done = _claim(tmp_path, "session-1", token="1" * 32)
    assert isinstance(owner_done, Path)

    returned = threading.Event()
    result: list[object] = []

    def wait() -> None:
        result.append(_claim(tmp_path, "session-1", wait_seconds=1.0))
        returned.set()

    thread = threading.Thread(target=wait)
    thread.start()
    time.sleep(0.05)
    assert not returned.is_set(), "a loser returned while the owner was still running"

    assert healer._complete_session(owner_done)
    thread.join(timeout=2)
    assert returned.is_set()
    assert result == [False], "a coordinated loser must skip the healer"


def test_healthy_completed_claim_skips_without_waiting(tmp_path: Path):
    done = _claim(tmp_path, "same-session", token="2" * 32)
    assert isinstance(done, Path) and healer._complete_session(done)
    started = time.monotonic()
    assert _claim(tmp_path, "same-session", wait_seconds=1.0) is False
    assert time.monotonic() - started < 0.2


def test_only_a_completed_expired_claim_can_be_rearmed(tmp_path: Path):
    old_done = _claim(tmp_path, "resume", token="3" * 32)
    assert isinstance(old_done, Path) and healer._complete_session(old_done)
    old = time.time() - healer._CLAIM_TTL_SECONDS - 1
    os.utime(old_done, (old, old))

    new_done = _claim(tmp_path, "resume", token="4" * 32)
    assert isinstance(new_done, Path)
    assert new_done != old_done
    assert "4" * 32 in new_done.name


def test_two_expired_completion_rearmers_elect_only_one_owner(
    tmp_path: Path, monkeypatch,
):
    old_done = _claim(tmp_path, "resume-race", token="a" * 32)
    assert isinstance(old_done, Path) and healer._complete_session(old_done)
    old = time.time() - healer._CLAIM_TTL_SECONDS - 1
    os.utime(old_done, (old, old))

    real_open = os.open
    real_read_claim_token = healer.read_claim_token
    barrier = threading.Barrier(2)
    partial_token_observed = threading.Event()
    synchronized: set[int] = set()
    sync_lock = threading.Lock()

    def synchronized_open(path, flags, mode=0o600):
        if str(path).endswith(".next") and flags & os.O_EXCL:
            ident = threading.get_ident()
            with sync_lock:
                first_attempt = ident not in synchronized
                synchronized.add(ident)
            if first_attempt:
                barrier.wait(timeout=10)
        return real_open(path, flags, mode)

    def partial_successor_token(path):
        if str(path).endswith(".next") and not partial_token_observed.is_set():
            partial_token_observed.set()
            return "b" * 8
        return real_read_claim_token(path)

    monkeypatch.setattr(os, "open", synchronized_open)
    monkeypatch.setattr(healer, "read_claim_token", partial_successor_token)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                _claim,
                tmp_path,
                "resume-race",
                token=token,
                wait_seconds=10.0,
            )
            for token in ("b" * 32, "c" * 32)
        ]
        owners, _ = wait(futures, timeout=5.0, return_when=FIRST_COMPLETED)
        assert len(owners) == 1, "exactly one O_EXCL owner must return first"
        owner_done = next(iter(owners)).result()
        assert isinstance(owner_done, Path)
        assert healer._complete_session(owner_done)
        results = [future.result(timeout=10) for future in futures]

    assert sum(isinstance(result, Path) for result in results) == 1
    assert results.count(False) == 1, "the loser must observe owner completion"
    assert partial_token_observed.is_set()


def test_future_completion_mtime_is_expired_not_fresh(tmp_path: Path):
    sid = "future-done"
    old_done = _claim(tmp_path, sid, token="9" * 32)
    assert isinstance(old_done, Path) and healer._complete_session(old_done)
    future = time.time() + healer._CLAIM_TTL_SECONDS + 60
    os.utime(old_done, (future, future))

    assert not lock_helper.session_repair_complete(tmp_path, sid)
    successor = _claim(tmp_path, sid, token="0" * 32)
    assert isinstance(successor, Path) and successor != old_done


@pytest.mark.parametrize("rounded_age", [-0.001, -1.0])
def test_bounded_future_completion_rounding_stays_fresh(
    tmp_path: Path, monkeypatch, rounded_age: float,
):
    sid = "rounded-future-done"
    done = _claim(tmp_path, sid, token="8" * 32)
    assert isinstance(done, Path) and healer._complete_session(done)
    monkeypatch.setattr(lock_helper, "read_completion_age", lambda _path: rounded_age)
    monkeypatch.setattr(healer, "read_completion_age", lambda _path: rounded_age)

    assert lock_helper.session_repair_state(tmp_path, sid) is True
    assert _claim(tmp_path, sid, wait_seconds=0.1) is False


def test_completion_older_than_clock_skew_boundary_rearms(
    tmp_path: Path, monkeypatch,
):
    sid = "beyond-clock-skew"
    done = _claim(tmp_path, sid, token="7" * 32)
    assert isinstance(done, Path) and healer._complete_session(done)
    beyond_skew = -1.001
    monkeypatch.setattr(lock_helper, "read_completion_age", lambda _path: beyond_skew)
    monkeypatch.setattr(healer, "read_completion_age", lambda _path: beyond_skew)

    assert lock_helper.session_repair_state(tmp_path, sid) is False
    successor = _claim(tmp_path, sid, token="6" * 32, wait_seconds=0.1)
    assert isinstance(successor, Path) and successor != done


def test_done_freshness_never_follows_the_path(
    tmp_path: Path, monkeypatch,
):
    sid = "no-follow-done"
    done = _claim(tmp_path, sid, token="f" * 32)
    assert isinstance(done, Path) and healer._complete_session(done)
    real_stat = Path.stat

    def reject_following_stat(path: Path, *args, **kwargs):
        if path == done and kwargs.get("follow_symlinks", True):
            raise AssertionError("completion freshness followed the done path")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", reject_following_stat)
    assert lock_helper.session_repair_state(tmp_path, sid) is True
    assert _claim(tmp_path, sid, wait_seconds=0.1) is False


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink race coverage")
def test_completion_swapped_to_symlink_before_open_is_rejected(
    tmp_path: Path, monkeypatch,
):
    sid = "swapped-completion"
    done = _claim(tmp_path, sid, token="0" * 32)
    assert isinstance(done, Path) and healer._complete_session(done)
    external = tmp_path / "external-completion"
    external.write_bytes(b"")
    real_open = os.open
    swapped = [False]

    def swap_then_open(path, flags, mode=0o600):
        if Path(path) == done and not swapped[0]:
            swapped[0] = True
            done.unlink()
            done.symlink_to(external)
        return real_open(path, flags, mode)

    monkeypatch.setattr(os, "open", swap_then_open)
    assert lock_helper.session_repair_state(tmp_path, sid) is None
    assert external.read_bytes() == b""


def test_non_regular_claim_is_rejected_without_reading(
    tmp_path: Path, monkeypatch,
):
    sid = "non-regular-claim"
    key = healer.hashlib.sha256(sid.encode("utf-8")).hexdigest()[:32]
    claim = tmp_path / ".sessionstart-claims" / f"ensure-shared-cache-{key}.claim"
    claim.mkdir(parents=True)
    real_read_text = Path.read_text

    def reject_non_regular_read(path: Path, *args, **kwargs):
        if path == claim:
            raise AssertionError("non-regular claim was opened for reading")
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", reject_non_regular_read)
    assert lock_helper.session_repair_state(tmp_path, sid) is None
    assert _claim(tmp_path, sid, wait_seconds=0.1) is None


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink race coverage")
def test_claim_swapped_to_symlink_between_open_and_validation_is_rejected(
    tmp_path: Path, monkeypatch,
):
    sid = "swapped-claim"
    key = healer.hashlib.sha256(sid.encode("utf-8")).hexdigest()[:32]
    claim = tmp_path / ".sessionstart-claims" / f"ensure-shared-cache-{key}.claim"
    claim.parent.mkdir(parents=True)
    claim.write_text("1" * 32, encoding="ascii")
    external = tmp_path / "external-token"
    external.write_text("2" * 32, encoding="ascii")
    real_open = os.open
    swapped = [False]

    def swap_then_open(path, flags, mode=0o600):
        if Path(path) == claim and not swapped[0]:
            swapped[0] = True
            claim.unlink()
            claim.symlink_to(external)
        return real_open(path, flags, mode)

    monkeypatch.setattr(os, "open", swap_then_open)
    assert lock_helper.session_repair_state(tmp_path, sid) is None
    assert external.read_text(encoding="ascii") == "2" * 32


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO unavailable")
def test_fifo_claim_is_rejected_without_blocking(tmp_path: Path):
    sid = "fifo-claim"
    key = healer.hashlib.sha256(sid.encode("utf-8")).hexdigest()[:32]
    claim = tmp_path / ".sessionstart-claims" / f"ensure-shared-cache-{key}.claim"
    claim.parent.mkdir(parents=True)
    os.mkfifo(claim)
    started = time.monotonic()
    assert lock_helper.session_repair_state(tmp_path, sid) is None
    assert time.monotonic() - started < 0.2


def test_lock_path_symlink_never_mutates_its_target(tmp_path: Path):
    target = tmp_path / "external-lock-target"
    target.write_bytes(b"leave-me-alone")
    lock_path = tmp_path / "claims" / "cache-repair.lock"
    lock_path.parent.mkdir()
    try:
        lock_path.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable")

    assert lock_helper.acquire_cache_lock(lock_path, 0.01) is None
    assert target.read_bytes() == b"leave-me-alone"


def test_lock_path_hardlink_never_mutates_its_target(tmp_path: Path):
    target = tmp_path / "external-hardlink-target"
    target.write_bytes(b"leave-me-alone")
    lock_path = tmp_path / "claims" / "cache-repair.lock"
    lock_path.parent.mkdir()
    try:
        os.link(target, lock_path)
    except OSError:
        pytest.skip("hard-link creation unavailable")

    assert lock_helper.acquire_cache_lock(lock_path, 0.01) is None
    assert target.read_bytes() == b"leave-me-alone"


def test_replacing_claim_directory_cannot_split_global_writer_lease(
    tmp_path: Path,
):
    lock_path = tmp_path / lock_helper.CACHE_LOCK_NAME
    claims = tmp_path / ".sessionstart-claims"
    claims.mkdir()
    first = lock_helper.acquire_cache_lock(lock_path, 0.1)
    assert isinstance(first, int)
    claims.rename(tmp_path / "old-claims")
    claims.mkdir()
    try:
        assert lock_helper.acquire_cache_lock(lock_path, 0.02) is None
    finally:
        lock_helper.release_cache_lock(first)
    second = lock_helper.acquire_cache_lock(lock_path, 0.1)
    assert isinstance(second, int)
    lock_helper.release_cache_lock(second)


def test_symlinked_claim_directory_cannot_redirect_global_lock(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    external_lock = outside / lock_helper.CACHE_LOCK_NAME
    external_lock.write_bytes(b"leave-me-alone")
    claims = tmp_path / ".sessionstart-claims"
    try:
        claims.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation unavailable")

    lock = lock_helper.acquire_cache_lock(
        tmp_path / lock_helper.CACHE_LOCK_NAME, 0.1,
    )
    assert isinstance(lock, int)
    lock_helper.release_cache_lock(lock)
    assert external_lock.read_bytes() == b"leave-me-alone"


def test_same_observer_rearms_a_fresh_completed_generation(tmp_path: Path):
    observer = "shipwright-run:consumer"
    done = _claim(tmp_path, "identical-event", token="a" * 32,
                  observer=observer)
    assert isinstance(done, Path)
    assert lock_helper.observe_completion(done, observer) is True
    assert healer._complete_session(done)

    successor = _claim(tmp_path, "identical-event", token="c" * 32,
                       observer=observer)
    assert isinstance(successor, Path) and successor != done


def test_observer_marker_does_not_repeat_long_generation_name(tmp_path: Path):
    done = tmp_path / (
        "ensure-shared-cache-" + "a" * 32 + "-" + "b" * 32 + ".done"
    )

    assert lock_helper.observe_completion(done, "shipwright-run:sessionstart")

    markers = list(tmp_path.glob("observed-*.seen"))
    assert len(markers) == 1
    assert len(markers[0].name) == len("observed-") + 32 + len(".seen")


def test_participant_absent_from_completed_generation_must_rearm(tmp_path: Path):
    done = _claim(tmp_path, "late-participant", token="d" * 32,
                  observer="participant-a")
    assert isinstance(done, Path)
    assert lock_helper.observe_completion(done, "participant-a") is True
    assert healer._complete_session(done)

    successor = _claim(tmp_path, "late-participant", token="e" * 32,
                       observer="participant-b")
    assert isinstance(successor, Path) and successor != done


def test_waiter_follows_successor_token_until_its_done(tmp_path: Path):
    old_done = _claim(tmp_path, "token-snapshot", token="d" * 32)
    assert isinstance(old_done, Path) and healer._complete_session(old_done)
    old = time.time() - healer._CLAIM_TTL_SECONDS - 1
    os.utime(old_done, (old, old))
    new_done = _claim(tmp_path, "token-snapshot", token="e" * 32)
    assert isinstance(new_done, Path)
    returned = threading.Event()
    result: list[object] = []

    def wait() -> None:
        result.append(_claim(tmp_path, "token-snapshot", wait_seconds=1.0))
        returned.set()

    thread = threading.Thread(target=wait)
    thread.start()
    time.sleep(0.05)
    assert not returned.is_set(), "waiter returned while successor owner ran"
    assert healer._complete_session(new_done)
    thread.join(timeout=2)
    assert result == [False]


def test_an_expired_running_owner_is_never_time_reclaimed(tmp_path: Path):
    owner_done = _claim(tmp_path, "slow-owner", token="5" * 32)
    assert isinstance(owner_done, Path)
    claim = next(owner_done.parent.glob("*.claim"))
    old = time.time() - healer._CLAIM_TTL_SECONDS - 10
    os.utime(claim, (old, old))

    # Recovery retains the known token; the global writer lease prevents overlap.
    assert _claim(tmp_path, "slow-owner", wait_seconds=0.02) == owner_done
    assert claim.read_text(encoding="ascii") == "5" * 32


def test_fresh_completion_does_not_inherit_an_old_claim_age(tmp_path: Path):
    done = _claim(tmp_path, "slow-completion", token="9" * 32)
    assert isinstance(done, Path)
    claim = next(done.parent.glob("*.claim"))
    old = time.time() - healer._CLAIM_TTL_SECONDS - 10
    os.utime(claim, (old, old))

    assert healer._complete_session(done)
    assert _claim(tmp_path, "slow-completion", wait_seconds=0.1) is False
    assert not list(done.parent.glob("*.next"))


def test_old_owner_completion_cannot_release_a_new_election(tmp_path: Path):
    old_done = _claim(tmp_path, "fenced", token="6" * 32)
    assert isinstance(old_done, Path) and healer._complete_session(old_done)
    old = time.time() - healer._CLAIM_TTL_SECONDS - 1
    os.utime(old_done, (old, old))
    new_done = _claim(tmp_path, "fenced", token="7" * 32)
    assert isinstance(new_done, Path)

    # Re-publishing the old token cannot satisfy a waiter fenced to the new one.
    healer._complete_session(old_done)
    assert _claim(tmp_path, "fenced", wait_seconds=0.02) == new_done
    assert healer._complete_session(new_done)
    assert _claim(tmp_path, "fenced", wait_seconds=0.2) is False


@pytest.mark.parametrize("sid", ["", "unknown", None, 7, {}, []])
def test_missing_or_malformed_session_identity_fails_open(
    tmp_path: Path, sid: object,
):
    assert _claim(tmp_path, sid) is None
    assert not list(tmp_path.rglob("*.claim"))


def test_session_filename_is_bounded_digest_not_raw_input(tmp_path: Path):
    sid = "../" + "very-long/unsafe:" * 100
    done = _claim(tmp_path, sid, token="8" * 32)
    assert isinstance(done, Path)
    claim = next(done.parent.glob("*.claim"))
    assert sid not in claim.name
    assert len(claim.name) < 100
    assert claim.parent.parent == tmp_path


def test_session_event_key_uses_only_immutable_payload_values(
    tmp_path: Path,
):
    transcript = tmp_path / "transcript.jsonl"
    payload = {
        "session_id": "same", "source": "startup",
        "transcript_path": str(transcript),
    }
    before_create = healer.session_event_key(payload)
    transcript.write_text("first\nsecond\n", encoding="utf-8")
    after_create = healer.session_event_key(payload)
    resumed = healer.session_event_key({
        "session_id": "same", "source": "resume",
        "transcript_path": str(transcript),
    })
    other_transcript = healer.session_event_key({
        **payload, "transcript_path": "bad\0path",
    })

    assert before_create == after_create
    assert len({before_create, resumed, other_transcript}) == 3


def test_session_event_key_rejects_unknown_even_with_generation_fields():
    assert healer.session_event_key({
        "session_id": "unknown",
        "source": "resume",
        "transcript_path": "bad\0path",
    }) == ""


def test_session_event_key_preserves_whitespace_in_valid_identity(tmp_path: Path):
    plain = healer.session_event_key({"session_id": "session"})
    padded = healer.session_event_key({"session_id": " session "})
    padded_sentinel = healer.session_event_key({"session_id": " unknown "})

    assert plain != padded
    assert padded_sentinel
    assert padded_sentinel != healer.session_event_key({"session_id": "unknown"})
    first = _claim(tmp_path, plain, token="1" * 32)
    second = _claim(tmp_path, padded, token="2" * 32)
    assert isinstance(first, Path) and isinstance(second, Path) and first != second


@pytest.mark.parametrize("field", ["session_id", "source", "transcript_path"])
def test_session_event_key_ascii_escapes_lone_surrogates(tmp_path: Path, field: str):
    payload = {
        "session_id": "session", "source": "startup", "transcript_path": "path",
    }
    payload[field] = "\ud800"

    event_key = healer.session_event_key(payload)

    assert event_key.isascii()
    assert isinstance(_claim(tmp_path, event_key, wait_seconds=0.01), Path)


def test_unwritable_coordination_boundary_fails_open(tmp_path: Path, monkeypatch):
    real_mkdir = Path.mkdir

    def deny(path: Path, *args, **kwargs):
        if path.name == healer._CLAIM_DIRNAME:
            raise PermissionError("denied")
        return real_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", deny)
    assert _claim(tmp_path, "session") is None


def test_failed_token_write_keeps_immutable_claim_path(tmp_path: Path, monkeypatch):
    def fail_write(*_args):
        raise OSError("write failed")

    monkeypatch.setattr(os, "write", fail_write)
    assert _claim(tmp_path, "write-failure") is None
    claims = list(tmp_path.rglob("*.claim"))
    assert len(claims) == 1


def test_short_token_writes_are_completed_before_owner_returns(
    tmp_path: Path, monkeypatch,
):
    real_write = os.write

    def write_four_bytes(fd, payload):
        return real_write(fd, payload[:4])

    monkeypatch.setattr(os, "write", write_four_bytes)
    done = _claim(tmp_path, "short-write", token="d" * 32)

    assert isinstance(done, Path)
    claim, = tmp_path.rglob("*.claim")
    assert claim.read_text(encoding="ascii") == "d" * 32
