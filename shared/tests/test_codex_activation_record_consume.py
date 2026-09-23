"""``consume()`` tests for shared/scripts/lib/codex_activation_record.py
(R2 — AC1a). Split out of ``test_codex_activation_record.py`` (bloat gate,
2026-09-22) — that file covers ``mint()``/``read()``; this one covers the
exclusive-consume half of the state machine. See that module's own docstring
for the storage layout and field semantics, and the fail-open contract
(R0's ADR): absent, corrupt, cwd-mismatched, or expired records are all
unconditionally "no record" — never an exception, never a denial by default.
"""

from __future__ import annotations

import threading


def test_consume_succeeds_once_and_returns_record(tmp_path):
    from lib.codex_activation_record import mint, consume

    mint(tmp_path, session_id="s1", turn_id="t1", cwd="/proj", armed=True, skill_id="x", args={})

    record = consume(tmp_path, "s1", cwd="/proj")

    assert record is not None
    assert record.skill_id == "x"


def test_consume_second_call_returns_none(tmp_path):
    from lib.codex_activation_record import mint, consume

    mint(tmp_path, session_id="s1", turn_id="t1", cwd="/proj", armed=True, skill_id="x", args={})

    first = consume(tmp_path, "s1", cwd="/proj")
    second = consume(tmp_path, "s1", cwd="/proj")

    assert first is not None
    assert second is None


def test_consume_returns_none_when_record_absent(tmp_path):
    from lib.codex_activation_record import consume

    assert consume(tmp_path, "never-minted", cwd="/proj") is None


def test_consume_returns_none_when_expired(tmp_path):
    from lib.codex_activation_record import mint, consume

    mint(tmp_path, session_id="s1", turn_id="t1", cwd="/proj", armed=True, skill_id="x",
         ttl_seconds=10.0, now=1000.0)

    assert consume(tmp_path, "s1", cwd="/proj", now=1011.0) is None


def test_consume_returns_none_on_cwd_mismatch(tmp_path):
    from lib.codex_activation_record import mint, consume

    mint(tmp_path, session_id="s1", turn_id="t1", cwd="/proj-a", armed=True, skill_id="x")

    assert consume(tmp_path, "s1", cwd="/proj-b") is None


def test_concurrent_consume_exactly_one_wins(tmp_path):
    from lib.codex_activation_record import mint, consume

    mint(tmp_path, session_id="s1", turn_id="t1", cwd="/proj", armed=True, skill_id="x", args={})

    results: list = []
    results_lock = threading.Lock()
    n_threads = 8
    barrier = threading.Barrier(n_threads)

    def worker():
        barrier.wait()
        outcome = consume(tmp_path, "s1", cwd="/proj")
        with results_lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    winners = [r for r in results if r is not None]
    assert len(winners) == 1


def test_session_id_sanitized_against_path_traversal(tmp_path):
    from lib.codex_activation_record import mint, read, _record_dir

    malicious = "../../etc/passwd"
    record = mint(tmp_path, session_id=malicious, turn_id="t1", cwd="/proj", armed=True, skill_id="x")

    assert record is not None
    # The record file must land inside the intended runtime directory, never
    # escape it via the raw session_id.
    written = list(_record_dir(tmp_path).glob("*.json"))
    assert len(written) == 1
    assert written[0].parent == _record_dir(tmp_path)
    assert read(tmp_path, malicious, cwd="/proj") is not None
