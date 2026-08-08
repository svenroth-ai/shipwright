"""A glued (but recognisable) drift line is refused honestly, not as unexplained corruption.

P2.19h — residual of iterate-2026-08-06-triage-validate-deadends (AC14), found by that
run's own Stage-3 doubt review and deliberately left out of its scope. AC14 fixed the
PROTECTION parser (``append_ids_of``) to recover record boundaries; the ADOPTION gate
(``_is_producer_event``, called from ``plan_main_tracked_drift``) still parsed one
``json.loads`` per physical line, so an UNCOMMITTED drift line glued by an unterminated
predecessor write was judged "not a triage producer event" and the whole sweep refused
with an unescapable ``main_tracked_unparseable`` — naming no remedy.

Split from ``test_sweep_drift_guards.py`` so both modules stay under the 300-LOC
guideline; that module owns the pre-existing refusal guards, this one owns the new
glued-line distinction and its escape hatch.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _sweep_helpers

import pytest  # noqa: E402

import _sweep_helpers as h  # noqa: E402
from _sweep_helpers import seeded  # noqa: E402,F401 (bare name required for fixture resolution)
from lib.sweep_drift import (  # noqa: E402
    _is_glued_producer_line,
    append_ids_of,
    commit_main_tracked_drift,
    plan_main_tracked_drift,
)
from lib.sweep_text import read_text_verbatim  # noqa: E402


def adopt(work: Path):
    """Plan + commit in one call — the sweep's two-phase adoption, as the sweep runs it."""
    plan = plan_main_tracked_drift(work, h.outbox(work))
    if plan.status != "adoptable":
        return plan
    return commit_main_tracked_drift(plan, work, h.outbox(work))


def test_a_glued_drift_line_refuses_but_names_the_repair_tool(seeded) -> None:  # noqa: F811
    """An UNCOMMITTED drift line glues two well-formed appends onto one physical line —
    the same unterminated-write shape ``append_ids_of`` now recovers for the PROTECTION
    universe. Adoption still refuses to move it (moving would carry the glue into the
    outbox verbatim, not un-corrupt it) — but unlike a genuinely corrupt line, the
    refusal must say WHY and name the tool that fixes it.

    ``--project-root <root>``, not ``.``: internal Opus plan review caught that
    ``main_root`` is never the caller's cwd, so a literal ``.`` would point the repair
    at the wrong tree — the exact escapability this run exists to provide."""
    work = seeded
    glued = h.item("trg-glued-a") + h.item("trg-glued-b")  # no separating newline
    body = h.write_tracked(work, h.HEADER, h.item("trg-seed"), glued)

    result = adopt(work)

    assert result.status == "refused"
    assert result.reason.startswith("main_tracked_glued_line"), result.reason
    assert "triage_repair.py" in result.reason, "the escape hatch is unnamed: " + result.reason
    assert "--project-root <root>" in result.reason, "wrong tree named: " + result.reason
    assert "commit" in result.reason, (
        "doubt review, medium: triage_repair never commits, so a repair-then-stop leaves "
        "the log diverged from HEAD; the hint must say to commit it: " + result.reason
    )
    assert read_text_verbatim(work / h.TRIAGE) == body, "the glued line was rewritten"
    assert not h.outbox(work).exists(), "a glued line reached the delivery buffer"


def test_a_truncated_predecessor_glued_to_a_full_append_is_also_recognised(seeded) -> None:  # noqa: F811
    """Internal Opus plan review finding 2. ``lib.jsonl_records`` names a damaged
    PREFIX — a truncated predecessor write appended onto — the PRIMARY corruption
    shape, not only the two-complete-records case AC14 fixed. Missing it here would
    silently fall back to ``main_tracked_unparseable`` for the shape the card actually
    describes ("an unterminated predecessor write"). A wrong ``glued`` label costs only
    message precision (adoption refuses either way); this proves the backward-resync
    widening actually recovers it."""
    work = seeded
    truncated = '{"event":"append" BROKEN'  # never decodes on its own
    glued = truncated + h.item("trg-recovered")
    body = h.write_tracked(work, h.HEADER, h.item("trg-seed"), glued)

    result = adopt(work)

    assert result.status == "refused"
    assert result.reason.startswith("main_tracked_glued_line"), result.reason
    assert read_text_verbatim(work / h.TRIAGE) == body


def test_is_glued_producer_line_distinguishes_glue_from_corruption_and_from_clean() -> None:
    """The predicate the adoption gate calls to compose its refusal reason must not
    fire on either of the two things it is NOT for: an already-clean single event
    (nothing to explain) or genuine corruption (no producer event recoverable at all,
    with nothing valid behind it either)."""
    assert _is_glued_producer_line(h.item("trg-a") + h.item("trg-b"))
    assert _is_glued_producer_line(h.item("trg-a") + h.status("trg-a", "dismissed"))
    assert not _is_glued_producer_line(h.item("trg-clean")), "a clean event is not glued"
    assert not _is_glued_producer_line("{ BROKEN"), "genuine corruption is not glued"
    assert not _is_glued_producer_line(""), "a blank line is not glued"
    assert not _is_glued_producer_line('{"foo":1}'), "a decodable non-record is not glued"


def test_is_glued_producer_line_fires_on_a_record_followed_by_unrelated_garbage() -> None:
    """External plan review (GPT), finding 2. ``True`` here means "a producer record
    is recoverable somewhere on this line", not "the rest of the line is benign" — a
    valid record glued to trailing garbage is still ``main_tracked_glued_line``, and
    that garbage is exactly what ``triage_repair.py`` quarantines on repair, so the
    hint remains an accurate pointer."""
    assert _is_glued_producer_line(h.item("trg-a") + '{"not":"a producer event"}')


@pytest.mark.parametrize("second", [
    h.item("trg-glued-b"),
    h.status("trg-glued-a", "dismissed"),
], ids=["append+append", "append+status"])
def test_is_glued_producer_line_agrees_with_the_protection_universe(second: str) -> None:
    """AC5, made a real composition rather than an asserted-but-unexercised claim
    (internal Opus plan review finding 3; parametrized per external plan review
    (GPT) finding 3): whatever ``append_ids_of`` recovers from a glued line,
    ``_is_glued_producer_line`` must also recognise as glued — never as unexplained
    corruption — across the append+append and append+status shapes. The two
    predicates do not use identical event sets (``append_ids_of`` counts only
    ``append``; this one accepts ``append`` or ``status``), so the guarantee is
    directional, not symmetric — pinned honestly rather than tested as a false
    equivalence."""
    glued = h.item("trg-glued-a") + second

    ids = append_ids_of([glued])

    assert ids, "setup: the fixture must actually be a recoverable glued line"
    assert _is_glued_producer_line(glued), "append_ids_of recovered it but adoption did not"
