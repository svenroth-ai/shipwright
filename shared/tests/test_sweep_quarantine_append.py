"""Regression tests for ``lib.sweep_quarantine.append_quarantine``.

WHY THIS FILE EXISTS. ``append_quarantine`` read the existing log with
``Path.read_text(encoding="utf-8", newline="")`` — and the ``newline`` keyword only
exists on **Python 3.13+**, while the shared scripts run on the CONSUMING project's
interpreter (pyproject: ``requires-python >= 3.11``). On 3.11/3.12 the call raised
``TypeError: Path.read_text() got an unexpected keyword argument 'newline'`` and took
``setup_iterate_worktree.py`` down with it — *after* the worktree and branch were
already created, so every iterate in such a project died mid-setup.

CI installs 3.11 and would have caught it — except the line is only reached when the
quarantine log ALREADY EXISTS, and no test ever appended to an existing one. That gap
is what these tests close: the first one fails on 3.11/3.12 without the fix.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.sweep_quarantine import append_quarantine  # noqa: E402


def _records(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return [json.loads(ln) for ln in fh.read().splitlines() if ln.strip()]


def test_append_to_an_EXISTING_log_keeps_the_prior_records(tmp_path: Path) -> None:
    """The read-back path — the one that raised TypeError on every Python < 3.13."""
    log = tmp_path / "triage.outbox.quarantine.jsonl"
    append_quarantine(log, ['{"id": "first"}'], reason="orphan-status", now="2026-01-01T00:00:00Z")

    append_quarantine(log, ['{"id": "second"}'], reason="orphan-status", now="2026-01-02T00:00:00Z")

    recs = _records(log)
    assert [r["original"] for r in recs] == ['{"id": "first"}', '{"id": "second"}']
    assert [r["quarantined_at"] for r in recs] == ["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"]
    assert {r["reason"] for r in recs} == {"orphan-status"}


def test_append_creates_the_log_when_absent(tmp_path: Path) -> None:
    log = tmp_path / "nested" / "triage.outbox.quarantine.jsonl"
    append_quarantine(log, ['{"id": "x"}'], reason="orphan-status", now="2026-01-01T00:00:00Z")
    assert _records(log) == [
        {"quarantined_at": "2026-01-01T00:00:00Z", "reason": "orphan-status", "original": '{"id": "x"}'}
    ]


def test_existing_CRLF_content_is_not_rewritten(tmp_path: Path) -> None:
    """``newline=""`` is load-bearing, not decoration: the existing bytes must survive
    the read/append round-trip verbatim. Dropping the keyword (the other way to make
    the call 3.11-compatible) would translate CRLF to LF and rewrite lines nobody
    asked to touch."""
    log = tmp_path / "triage.outbox.quarantine.jsonl"
    with log.open("w", encoding="utf-8", newline="") as fh:
        fh.write('{"quarantined_at": "2026-01-01T00:00:00Z", "reason": "r", "original": "{}"}\r\n')

    append_quarantine(log, ['{"id": "new"}'], reason="orphan-status", now="2026-01-02T00:00:00Z")

    raw = log.read_bytes()
    assert raw.startswith(b'{"quarantined_at": "2026-01-01T00:00:00Z"'), "prior record was rewritten"
    assert b"\r\n" in raw, "the existing CRLF line ending was normalized away"
    assert len(_records(log)) == 2
