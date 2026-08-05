"""Concurrent-writer safety for the iterate-timings sidecar (external review
finding: multiple producers within one run could interleave unlocked appends,
especially on Windows where append-mode alone isn't atomic).
"""

from __future__ import annotations

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from lib import iterate_timings as it  # noqa: E402
from lib import iterate_timings_normalize as itn  # noqa: E402

RUN = "iterate-2026-08-04-iterate-timing-attribution"

_WRITE_ONE_SPAN = (
    "import sys; sys.path.insert(0, {scripts!r}); "
    "from lib import iterate_timings as it; "
    "it.record_producer_span({root!r}, {run!r}, name='external_review', "
    "parent='review', start_utc='2026-08-04T10:00:00+00:00', "
    "end_utc='2026-08-04T10:00:01+00:00', duration_ms=1000, attempt={attempt})"
)


def test_concurrent_producer_writers_never_corrupt_the_sidecar(tmp_path):
    """N threads each append a producer span "simultaneously" — every line
    must still be valid JSON, and every span must survive normalization."""
    n = 40
    it.record_producer_span(
        tmp_path, RUN, name="review", parent=None,
        start_utc="2026-08-04T09:00:00+00:00", end_utc="2026-08-04T11:00:00+00:00",
        duration_ms=2 * 3600 * 1000, source="agent",
    )

    def _write(i: int) -> None:
        it.record_producer_span(
            tmp_path, RUN, name="external_review", parent="review",
            start_utc="2026-08-04T10:00:00+00:00", end_utc="2026-08-04T10:00:01+00:00",
            duration_ms=1000, attempt=i + 1,
        )

    with ThreadPoolExecutor(max_workers=n) as pool:
        list(pool.map(_write, range(n)))

    raw = itn.read_raw_events(tmp_path, RUN)
    assert len(raw) == n + 1  # the "review" span + every concurrent write
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not rejected
    children = [v for v in valid if v["name"] == "external_review"]
    assert len(children) == n  # no interleaved/corrupted line dropped a write
    assert {v["attempt"] for v in children} == set(range(1, n + 1))


def test_concurrent_writers_across_real_OS_processes_never_corrupt_the_sidecar(tmp_path):
    """The thread-based test above proves the lock serializes within one
    process; F0's own units already run as genuinely separate OS processes,
    so real multi-process writers to the SAME sidecar are a real scenario,
    not a hypothetical. This spawns N actual `python -c` subprocesses —
    sharing nothing but the filesystem — each appending one span, and proves
    FileLock (the same primitive record_event.py/triage.py already rely on)
    serializes across process boundaries, not just threads."""
    n = 8
    it.record_producer_span(
        tmp_path, RUN, name="review", parent=None,
        start_utc="2026-08-04T09:00:00+00:00", end_utc="2026-08-04T11:00:00+00:00",
        duration_ms=2 * 3600 * 1000, source="agent",
    )
    procs = [
        subprocess.Popen([sys.executable, "-c", _WRITE_ONE_SPAN.format(
            scripts=str(_SCRIPTS), root=str(tmp_path), run=RUN, attempt=i + 1)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for i in range(n)
    ]
    for p in procs:
        _, stderr = p.communicate(timeout=30)
        assert p.returncode == 0, stderr

    raw = itn.read_raw_events(tmp_path, RUN)
    assert len(raw) == n + 1
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not rejected
    children = [v for v in valid if v["name"] == "external_review"]
    assert len(children) == n
    assert {v["attempt"] for v in children} == set(range(1, n + 1))
