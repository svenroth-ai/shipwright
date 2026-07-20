"""Record-boundary recovery for grade routing's staleness oracle.

``routing._newest_work_commit`` keys the authoritative-vs-heuristic staleness
decision on the NEWEST ``work_completed`` event. Pre-fix it parsed one physical
line at a time, so a newest event sitting second on a concatenated line (the
artefact a ``merge=union`` merge propagates) was skipped — an OLDER commit then
won and the target was false-flagged STALE, or the check declined to judge.

Part 2 of iterate-2026-07-19-events-record-boundary-readers (filed as
``trg-360e494f``). ``routing`` ships inside grade's own ``scripts/lib``, so the
shared SSoT is loaded by file location under a sentinel (the ADR-045 barrier).
"""
from __future__ import annotations

import json

from routing import _newest_work_commit, decide_routing


def test_newest_work_commit_recovers_the_newest_from_a_concatenated_line() -> None:
    """The newest ``work_completed`` is the SECOND record on a concatenated line.
    Pre-fix that line was skipped whole, so the OLDER record's commit won."""
    old = {"type": "work_completed", "commit": "aaaaaaaaaaaa", "id": "old"}
    mid = {"type": "work_completed", "commit": "cccccccccccc", "id": "mid"}
    new = {"type": "work_completed", "commit": "bbbbbbbbbbbb", "id": "new"}
    text = json.dumps(old) + "\n" + json.dumps(mid) + json.dumps(new) + "\n"
    saw, commit = _newest_work_commit(text)
    assert saw is True
    assert commit == "bbbbbbbbbbbb", "the newest record was second on the concatenated line"


def test_newest_work_commit_partial_recovery_ignores_a_trailing_fragment() -> None:
    """A valid newest record followed by an unrecoverable fragment still resolves
    (partial recovery, never all-or-nothing)."""
    new = {"type": "work_completed", "commit": "bbbbbbbbbbbb", "id": "new"}
    text = json.dumps(new) + "{truncated\n"
    saw, commit = _newest_work_commit(text)
    assert saw is True and commit == "bbbbbbbbbbbb"


def test_newest_work_commit_declines_when_no_work_event() -> None:
    """Anti-vacuity: no ``work_completed`` at all still declines to judge."""
    text = json.dumps({"type": "phase_completed"}) + "\n"
    assert _newest_work_commit(text) == (False, "")


def test_newest_work_commit_skips_a_leading_partial_tail_fragment() -> None:
    """The bounded TAIL read can begin mid-line (a partial fragment). That leading
    fragment must never be mistaken for a record and become the newest event
    (external review, OpenAI #1 / Gemini #3). The pre-fix code skipped it because
    ``json.loads`` failed; recovery must keep skipping it — a fragment that does
    NOT decode is not a record."""
    new = {"type": "work_completed", "commit": "abcdef012345", "id": "new"}
    # ``...eadbeef"}`` is the tail of a truncated object — the seek landed mid-line.
    text = 'eadbeef", "id": "old"}\n' + json.dumps(new) + "\n"
    saw, commit = _newest_work_commit(text)
    assert saw is True and commit == "abcdef012345", "the leading partial must not win"


def test_decide_routing_not_stale_when_head_matches_recovered_newest(tmp_path) -> None:
    """End-to-end through the public API: HEAD matches the newest recorded commit,
    which is second on a concatenated line. Pre-fix the older non-matching commit
    won and the target was flagged STALE; post-fix it grades authoritative."""
    head = "abcdef0123456789abcdef0123456789abcdef01"
    old = {"type": "work_completed", "commit": "deadbeefdead", "id": "old"}
    new = {"type": "work_completed", "commit": "abcdef0123456", "id": "new"}
    sw = tmp_path / ".shipwright"
    (sw / "compliance").mkdir(parents=True)  # artifact-path-canon: legacy — graded target's RTM
    (sw / "compliance" / "traceability-matrix.md").write_text("# RTM\n", encoding="utf-8")  # artifact-path-canon: legacy
    (tmp_path / "shipwright_events.jsonl").write_text(
        json.dumps(old) + "\n" + json.dumps(new) + json.dumps({"type": "phase_completed"}) + "\n",
        encoding="utf-8",
    )
    d = decide_routing(tmp_path, head_sha=head)
    assert d.state == "valid"
    assert d.detected_mode == "authoritative"
