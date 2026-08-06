"""The same-id ``append`` collision rule — audit 2026-07-28 finding 25.

``dedup_triage_lines`` is the one path on the triage write surface that can DROP a
record. These tests pin *when* it is allowed to, and that it can never do so
silently. ADR-163's keep-last collapse is preserved; what is new is that a probable
32-bit id collision between two distinct items keeps both lines instead.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.triage_dedup import IDENTITY_ANCHOR, dedup_triage_lines  # noqa: E402
from lib.triage_validate import validate_triage_text  # noqa: E402

HEADER = '{"v":1,"schema":"triage","created":"2026-06-05T00:00:00Z"}'


def _append(item_id: str, *, anchor: str | None = "2026-08-01T00:00:00.000001Z", **over) -> str:
    rec: dict = {"event": "append", "id": item_id, "ts": "2026-08-02T00:00:00Z",
                 "title": "t", "source": "auditDetector", "kind": "improvement"}
    if anchor is not None:
        rec[IDENTITY_ANCHOR] = anchor
    rec.update(over)
    return json.dumps(rec, separators=(",", ":"))


def _text(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"


# --- supersession: the ADR-163 case, preserved but no longer silent -----------

def test_matching_anchor_collapses_keep_last_and_warns() -> None:
    v1 = _append("trg-aaaa", title="draft")
    v2 = _append("trg-aaaa", title="resolved", ts="2026-08-03T00:00:00Z")
    out, warn = dedup_triage_lines([HEADER, v1, v2])
    assert out == [HEADER, v2]                       # ADR-163 unchanged
    assert len(warn) == 1 and "superseded" in warn[0]
    assert validate_triage_text(_text(out)) == []    # delivery still unblocked


def test_supersession_warning_is_not_an_error() -> None:
    """A warning must never, by itself, stop delivery — the whole point of the
    card is that this surface disables the channel too easily."""
    out, warn = dedup_triage_lines([HEADER, _append("trg-aaaa", title="a"),
                                    _append("trg-aaaa", title="b")])
    assert warn != []
    assert validate_triage_text(_text(out)) == []


# --- collision: the twin's case, now honoured ---------------------------------

def test_disagreeing_anchors_keep_both_and_warn_loudly() -> None:
    a = _append("trg-bbbb", anchor="2026-01-01T00:00:00.000001Z", title="finding A")
    b = _append("trg-bbbb", anchor="2026-07-07T09:09:09.000002Z", title="finding B")
    out, warn = dedup_triage_lines([HEADER, a, b])
    assert out == [HEADER, a, b]                     # NOTHING dropped
    assert len(warn) == 1
    assert "32-bit id collision" in warn[0] and "triage_repair.py" in warn[0]


def test_collision_is_what_blocks_not_the_warning() -> None:
    """The block comes from the retained duplicate reaching the validator, which is
    recoverable — not from the warning, which must stay informational."""
    a = _append("trg-bbbb", anchor="2026-01-01T00:00:00.000001Z")
    b = _append("trg-bbbb", anchor="2026-07-07T09:09:09.000002Z")
    out, _ = dedup_triage_lines([HEADER, a, b])
    assert any("duplicate append" in e for e in validate_triage_text(_text(out)))


def test_mixed_anchor_presence_is_a_collision() -> None:
    """One record carries the anchor and the other does not: not enough evidence to
    call it a refresh, so nothing is dropped."""
    a = _append("trg-cccc", anchor=None, title="legacy")
    b = _append("trg-cccc", title="fresh")
    out, warn = dedup_triage_lines([HEADER, a, b])
    assert out == [HEADER, a, b]
    assert "32-bit id collision" in warn[0]


def test_empty_and_non_str_anchor_count_as_absent() -> None:
    # `" "` is in this list because it was NOT absent: the emptiness test ran before
    # the strip, so a whitespace-only anchor read as present, normalised to "", and two
    # distinct records carrying it compared EQUAL — a silent drop (external code review).
    for bad in ("", " ", "	", 17, None, [], {}):
        a = _append("trg-dddd", anchor=None) if bad is None else _append("trg-dddd", **{IDENTITY_ANCHOR: bad})
        b = _append("trg-dddd", title="fresh")
        out, warn = dedup_triage_lines([HEADER, a, b])
        assert out == [HEADER, a, b], f"anchor {bad!r} must not license a drop"
        assert "32-bit id collision" in warn[0]


# --- three-plus records: grouping, not a pairwise walk ------------------------

def test_three_records_two_anchors_keeps_all() -> None:
    """A pairwise 'compare against the last kept line' walk would chain A~B, B~C and
    drop a record whose anchor nothing agreed with. Grouping cannot."""
    a = _append("trg-eeee", anchor="2026-01-01T00:00:00.000001Z", title="A")
    b = _append("trg-eeee", anchor="2026-01-01T00:00:00.000001Z", title="B")
    c = _append("trg-eeee", anchor="2026-05-05T00:00:00.000009Z", title="C")
    out, warn = dedup_triage_lines([HEADER, a, b, c])
    assert out == [HEADER, a, b, c]
    assert "32-bit id collision" in warn[0] and "3 DISTINCT" in warn[0]


def test_three_records_one_anchor_collapses_to_last() -> None:
    a, b, c = (_append("trg-ffff", title=t, ts=f"2026-08-0{n}T00:00:00Z")
               for n, t in ((1, "A"), (2, "B"), (3, "C")))
    out, warn = dedup_triage_lines([HEADER, a, b, c])
    assert out == [HEADER, c]
    assert "2 earlier append(s)" in warn[0]


# --- a missing anchor is never permission to collapse -------------------------

def test_anchorless_group_keeps_both() -> None:
    """A drop needs POSITIVE evidence. An earlier cut collapsed here and merely
    warned, on the theory that an anchorless log would otherwise wedge — but both
    of ``triage.py``'s append constructors set ``originalTs`` unconditionally, so
    an anchorless record is exactly as rare as a collision and there is no
    asymmetry to trade on."""
    a = _append("trg-9999", anchor=None, title="A")
    b = _append("trg-9999", anchor=None, title="B")
    out, warn = dedup_triage_lines([HEADER, a, b])
    assert out == [HEADER, a, b]
    assert "32-bit id collision" in warn[0]


def test_the_two_spellings_of_one_instant_are_the_same_anchor() -> None:
    """The writer that produces same-id appends emits BOTH forms — the corpus's own
    trg-60ef91fb line carries `ts` as `+00:00` beside `originalTs` as `Z`. On raw byte
    equality a re-serialised refresh would read as a collision, both lines would be
    kept, and the sweep would go `invalid` FOREVER: the terminal state this card
    exists to forbid, produced by the rule meant to forbid it (doubt review)."""
    z = _append("trg-tz", anchor="2026-06-09T06:17:59.661332Z", title="v1")
    offset = _append("trg-tz", anchor="2026-06-09T06:17:59.661332+00:00", title="v2",
                     ts="2026-06-09T06:29:44.597008+00:00")
    out, warn = dedup_triage_lines([HEADER, z, offset])
    assert out == [HEADER, offset], "the two spellings must collapse, not collide"
    assert "superseded" in warn[0]
    assert validate_triage_text(_text(out)) == []      # delivery stays unblocked


def test_a_genuinely_different_instant_still_collides() -> None:
    """Control for the normalisation: it must not make everything equal."""
    a = _append("trg-tz2", anchor="2026-06-09T06:17:59.661332Z")
    b = _append("trg-tz2", anchor="2026-06-09T06:17:59.661333Z")   # 1 microsecond apart
    out, warn = dedup_triage_lines([HEADER, a, b])
    assert out == [HEADER, a, b]
    assert "32-bit id collision" in warn[0]


def test_an_unparseable_anchor_falls_back_to_string_equality() -> None:
    """Not readable as a timestamp, but two records can still agree on it — and
    disagreement only ever costs a refusal to collapse, which is the safe direction."""
    same_a = _append("trg-tz3", anchor="not-a-timestamp", title="v1")
    same_b = _append("trg-tz3", anchor="not-a-timestamp", title="v2")
    out, _ = dedup_triage_lines([HEADER, same_a, same_b])
    assert out == [HEADER, same_b]
    other = _append("trg-tz4", anchor="not-a-timestamp")
    diff = _append("trg-tz4", anchor="also-not-a-timestamp")
    kept, warn = dedup_triage_lines([HEADER, other, diff])
    assert kept == [HEADER, other, diff] and "32-bit id collision" in warn[0]


def test_every_real_append_carries_the_anchor() -> None:
    """The measurement the rule above rests on, pinned so it cannot rot silently:
    if a producer ever stops writing ``originalTs``, this fails and the collapse
    policy has to be revisited rather than quietly wedging that producer."""
    source = (_SHARED_SCRIPTS / "triage.py").read_text(encoding="utf-8")
    append_ctors = source.count('"event": "append"')
    assert append_ctors == 2, f"append constructors changed ({append_ctors}); re-check the anchor"
    assert source.count('"originalTs": ts') == append_ctors


# --- everything the rule must NOT touch ---------------------------------------

def test_byte_identical_collapse_never_warns() -> None:
    """Dropping a byte-identical duplicate deletes no information."""
    a = _append("trg-1111")
    out, warn = dedup_triage_lines([HEADER, a, a])
    assert out == [HEADER, a]
    assert warn == []


def test_status_sharing_an_id_with_its_append_is_untouched() -> None:
    a = _append("trg-2222")
    s = json.dumps({"event": "status", "id": "trg-2222", "newStatus": "dismissed"},
                   separators=(",", ":"))
    out, warn = dedup_triage_lines([HEADER, a, s])
    assert out == [HEADER, a, s]
    assert warn == []


def test_unparseable_and_non_str_id_appends_pass_through() -> None:
    bad_id = json.dumps({"event": "append", "id": 7}, separators=(",", ":"))
    out, warn = dedup_triage_lines([HEADER, _append("trg-3333"), "NOT JSON", bad_id])
    assert "NOT JSON" in out and bad_id in out
    assert warn == []


def test_distinct_ids_are_never_compared() -> None:
    """Two items minted in the same microsecond share an anchor — the corpus has
    such pairs — but they have different ids, so the anchor is never consulted."""
    shared_ts = "2026-06-07T15:05:01.329970Z"
    a = _append("trg-4444", anchor=shared_ts)
    b = _append("trg-5555", anchor=shared_ts)
    out, warn = dedup_triage_lines([HEADER, a, b])
    assert out == [HEADER, a, b]
    assert warn == []
