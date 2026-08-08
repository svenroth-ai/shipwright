"""Tests for shared/scripts/lib/event_once.py — the once-per-event claim.

A SessionStart event fires every plugin's hook (no active-plugin filter),
so a shared hook runs N times for one event. ``claim_once`` lets exactly
ONE of those concurrent invocations win the right to do an expensive
once-per-event action; the rest skip. TTL re-arms for a later event
(e.g. a resume/compact SessionStart that reuses the session id). Any
unexpected error fails OPEN (returns True) so a real signal is never
silently dropped.
"""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# event_once lives in shared/scripts/lib/; make that importable.
_LIB = Path(__file__).resolve().parent.parent / "scripts"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from lib.event_once import claim_once, event_claim_path  # noqa: E402


def test_event_claim_path_shape(tmp_path):
    p = event_claim_path(tmp_path, "stop-handoff", "sess-123")
    assert p == tmp_path / ".shipwright" / ".cache" / "stop-handoff-sess-123.claim"


def test_create_claim_is_owner_only(tmp_path):
    """Hardening: claim/marker files are created 0o600 (not world-readable).

    The exact permission bit is only observable on POSIX (Windows ignores the
    ``os.open`` mode), so the strict assertion runs there — including Linux CI,
    where the security property actually matters.
    """
    from lib.event_once import _create

    p = tmp_path / "owner-only.claim"
    assert _create(p) is True
    assert p.exists()
    if sys.platform != "win32":
        import stat

        assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_event_claim_path_sanitises_traversal(tmp_path):
    # A malformed event/session token must never escape .cache (path traversal).
    # Containment is what matters: stripping separators keeps the value a single
    # filename component, so the claim file stays directly under .cache. (A ``..``
    # SUBSTRING inside one filename component cannot traverse — only a standalone
    # ``..`` path SEGMENT can, which the separator-strip makes impossible.)
    p = event_claim_path(tmp_path, "../../evil", "a/b\\c")
    cache = (tmp_path / ".shipwright" / ".cache").resolve()
    assert p.resolve().parent == cache
    assert "/" not in p.name and "\\" not in p.name


def test_event_claim_path_empty_tokens_fall_back(tmp_path):
    p = event_claim_path(tmp_path, "", "")
    assert p.name == "event-unknown.claim"


def test_event_claim_path_usable_with_claim_once(tmp_path):
    p = event_claim_path(tmp_path, "stop-x", "sid")
    assert claim_once(p, ttl_seconds=30) is True   # parent auto-created
    assert claim_once(p, ttl_seconds=30) is False  # same event → skip


def test_first_claim_wins(tmp_path):
    p = tmp_path / ".cache" / "x.claim"
    assert claim_once(p) is True
    assert p.exists()


def test_second_claim_same_event_skips(tmp_path):
    p = tmp_path / ".cache" / "x.claim"
    assert claim_once(p, ttl_seconds=30) is True
    assert claim_once(p, ttl_seconds=30) is False


def test_stale_claim_re_arms_then_fresh_skips(tmp_path):
    p = tmp_path / ".cache" / "x.claim"
    assert claim_once(p, ttl_seconds=30) is True
    # Age the claim well beyond the TTL → it belongs to a previous event.
    old = time.time() - 100
    os.utime(p, (old, old))
    assert claim_once(p, ttl_seconds=30) is True  # stale → re-arm (re-emit)
    assert claim_once(p, ttl_seconds=30) is False  # fresh again → skip




def test_claim_once_purges_expired_sibling_claims(tmp_path):
    stale = tmp_path / ".cache" / "old-session.claim"
    stale.parent.mkdir()
    stale.touch()
    os.utime(stale, (0, 0))

    assert claim_once(
        tmp_path / ".cache" / "current-session.claim",
        ttl_seconds=30,
        now=100.0,
    )
    assert not stale.exists()
def test_now_param_makes_ttl_deterministic(tmp_path):
    p = tmp_path / ".cache" / "x.claim"
    assert claim_once(p, ttl_seconds=30, now=1000.0) is True
    os.utime(p, (1000.0, 1000.0))
    # now just inside the window → still owned → skip
    assert claim_once(p, ttl_seconds=30, now=1020.0) is False
    # now past the window → stale → re-arm
    assert claim_once(p, ttl_seconds=30, now=1040.0) is True


def test_unwritable_parent_fails_open(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file", encoding="utf-8")
    # Parent (blocker/sub) cannot be created because blocker is a file.
    p = blocker / "sub" / "x.claim"
    assert claim_once(p) is True  # fail-open: emit rather than drop


def test_concurrent_invocations_exactly_one_winner(tmp_path):
    p = tmp_path / ".cache" / "c.claim"
    with ThreadPoolExecutor(max_workers=12) as ex:
        results = list(ex.map(lambda _: claim_once(p, ttl_seconds=30), range(12)))
    assert sum(1 for r in results if r) == 1


def test_distinct_keys_are_independent(tmp_path):
    a = tmp_path / ".cache" / "a.claim"
    b = tmp_path / ".cache" / "b.claim"
    assert claim_once(a) is True
    assert claim_once(b) is True  # different event → independent winner
    assert claim_once(a) is False


def test_purge_respects_each_claims_own_ttl(tmp_path):
    long_lived = tmp_path / ".cache" / "long-lived.claim"
    assert claim_once(long_lived, ttl_seconds=300, now=0.0)
    os.utime(long_lived, (0, 0))

    assert claim_once(
        tmp_path / ".cache" / "short-lived.claim",
        ttl_seconds=30,
        now=100.0,
    )
    assert long_lived.exists()


def test_stale_claim_rearm_executes_second_create(tmp_path, monkeypatch):
    from lib import event_once

    claim = tmp_path / ".cache" / "stale.claim"
    assert claim_once(claim, ttl_seconds=30, now=0.0)
    os.utime(claim, (0, 0))
    monkeypatch.setattr(event_once, "_purge_expired_claims", lambda *_args, **_kwargs: None)
    calls = 0
    original = event_once._create

    def counting_create(path, ttl_seconds=30.0):
        nonlocal calls
        calls += 1
        return original(path, ttl_seconds)

    monkeypatch.setattr(event_once, "_create", counting_create)
    assert claim_once(claim, ttl_seconds=30, now=100.0)
    assert calls == 2


def test_create_write_error_fails_open_and_removes_claim(tmp_path, monkeypatch):
    from lib import event_once

    claim = tmp_path / "write-error.claim"

    class FailingClaim:
        def __init__(self, fd):
            self.fd = fd

        def __enter__(self):
            return self

        def __exit__(self, *_):
            os.close(self.fd)

        def write(self, _text):
            raise OSError("simulated write error")

    monkeypatch.setattr(event_once.os, "fdopen", lambda fd, *_args, **_kwargs: FailingClaim(fd))
    assert event_once._create(claim) is None
    assert not claim.exists()


def test_purge_keeps_claim_replaced_during_cleanup(tmp_path, monkeypatch):
    from lib import event_once

    claim = tmp_path / "replaced.claim"
    assert claim_once(claim, ttl_seconds=30, now=0.0)
    os.utime(claim, (0, 0))
    identities = iter(((1, 1, 1, 1), (2, 2, 2, 2)))
    monkeypatch.setattr(event_once, "_claim_identity", lambda _path: next(identities))

    event_once._purge_expired_claims(tmp_path, now=100.0)

    assert claim.exists()


def test_purge_ignores_unreadable_cache_directory(tmp_path, monkeypatch):
    from lib import event_once

    def failing_glob(_self, _pattern):
        raise OSError("simulated glob error")

    monkeypatch.setattr(event_once.Path, "glob", failing_glob)
    event_once._purge_expired_claims(tmp_path, now=100.0)
