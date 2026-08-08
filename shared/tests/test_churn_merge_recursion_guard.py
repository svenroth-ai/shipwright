"""RecursionError guard for ``churn_merge.dedup_event_lines`` — card
trg-57d0d6d3 / P2.19g, TEIL 2.

Sibling of the triage-side fix pinned in ``test_triage_dedup.py``. Found by
the internal Opus plan review during iterate-2026-08-07-triage-dedup-recursion-guard,
not by the originating card, which only named the triage-log call site. Split
into its own module (rather than added to ``test_churn_merge.py``) to keep
that file under the 300-LOC guideline.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.churn_merge import dedup_event_lines  # noqa: E402


def _deep_event(iid: str) -> str:
    """An event line nested deep enough to defeat json.loads' RecursionError
    guard — same idiom as the triage-side test, never sys.setrecursionlimit."""
    nested = '{"a":' * 20000 + "1" + "}" * 20000
    return f'{{"id":"{iid}","val":{nested}}}'


def test_deeply_nested_event_line_does_not_raise_and_survives() -> None:
    """AC-1 sibling. Pre-fix this raises RecursionError out of
    dedup_event_lines; post-fix the id extraction degrades to None (matching
    the existing AttributeError/JSONDecodeError degradation) and the line
    itself is neither dropped nor mutated — dedup_event_lines' own contract is
    'never drops a distinct line'."""
    deep = _deep_event("trg-deepevt")
    out, warn = dedup_event_lines([deep])
    assert out == [deep]
    assert warn == []


def test_deeply_nested_event_line_beside_a_valid_same_id_twin() -> None:
    """AC-2 matrix cell (deepseek round-2b finding, accepted): a deep line
    sharing an id with an otherwise-valid, correctly-parsed line must leave
    BOTH in the output — the deep line's id extraction degrades to None, so it
    is invisible to the id-collision warning path, not deduplicated away."""
    valid = '{"id":"trg-evttwin","ts":1}'
    deep = _deep_event("trg-evttwin")
    out, warn = dedup_event_lines([valid, deep])
    assert out == [valid, deep], "ordered-subsequence preservation (external review, openai)"
    assert warn == [], "the deep line's id never registers, so no collision warning fires"


def test_deeply_nested_event_line_matrix_placement_first_and_last() -> None:
    """AC-2 matrix cell, mirroring the triage-side placement cell (spec-reviewer
    Stage 1 finding: this module's matrix must be the 'identical shape')."""
    valid = '{"id":"trg-evtorder","ts":1}'
    deep_first = _deep_event("trg-evtdeepfirst")
    out_first, _ = dedup_event_lines([deep_first, valid])
    assert out_first == [deep_first, valid]
    deep_last = _deep_event("trg-evtdeeplast")
    out_last, _ = dedup_event_lines([valid, deep_last])
    assert out_last == [valid, deep_last]


def test_deeply_nested_event_line_beside_a_malformed_line() -> None:
    """AC-2 matrix cell, mirroring the triage-side malformed-line cell: two
    different failure modes of the id extraction (RecursionError vs
    AttributeError/ValueError) must both degrade the same way, side by side."""
    deep = _deep_event("trg-evtmixed")
    malformed = "NOT JSON"
    out, warn = dedup_event_lines([deep, malformed])
    assert out == [deep, malformed], "ordered-subsequence preservation (external review, openai)"
    assert warn == []


def test_non_str_id_does_not_raise_typeerror() -> None:
    """Doubt-reviewer finding 1 (Stage 3): a decoded id that is a JSON array or
    object is truthy but unhashable — pre-fix, ``ev_id in id_to_line`` raised
    ``TypeError: unhashable type`` for exactly the same 'damaged/foreign
    writer' input class the RecursionError guard exists to protect against.
    Reproduced directly pre-fix (uv run python probe); the fix mirrors the
    isinstance-first idiom already established in ``sweep_quarantine.py``'s
    orphan-id check and ``triage_dedup._parsed_append``."""
    non_str_id = '{"id":["x"],"ts":1}'
    out, warn = dedup_event_lines([non_str_id])
    assert out == [non_str_id]
    assert warn == []
