"""Is the recovered history COMPLETE? (campaign S7)

``test_fr_change_history_recovers_compacted_history.py`` asks whether the query
matches the recovery. This module asks the question one layer down: does the
recovery match the source?

That distinction has teeth. The provenance check in the sibling module asserts
every id in the tables appears in the pre-S6 file — a direction an **incomplete**
recovery satisfies trivially. An id present in the file but missing from the
tables would be invisible to it, and would mean the acceptance-criterion finding
was measured against a partial set, i.e. the headline number would be wrong.
Here the assertion is set EQUALITY, per requirement, against that requirement's
own section.

It also reconciles a second discrepancy the first publication left unstated:
ADR-109 and the S7 spec quote **block** counts (FR-01.11 six, FR-01.14 five)
while the recovery collects **run ids** (five each). Unexplained, that reads as
a run id having been dropped. It was not — see :data:`BLOCK_RECONCILIATION`.

Document-facing checks live in ``test_fr_history_published_counts.py``.
"""

from __future__ import annotations

import re

import pytest

# NB: no `sys.path` insert and no `_REPO`. This module imports nothing from
# `lib`, and `shared/scripts` on `sys.path` binds the ambiguous top-level name
# `lib` for the whole session (ADR-045) — a real shadowing hazard for zero
# benefit. Path resolution lives in `_fr_history_docs`.
from _fr_history_docs import pre_s6_sections, run_ids_in
from _fr_history_recovered_history import (  # noqa: E402
    ATTRIBUTIONS_NAMING_NO_RUN_ID,
    BLOCK_RECONCILIATION,
    FRS as _FRS,
    NOT_IN_EVENT_LOG,
    RECOVERED_EXACT,
    RECOVERED_UNDER_ADR_ID,
)


@pytest.mark.parametrize("fr_id", _FRS)
def test_no_run_id_in_the_source_was_left_out_of_the_tables(fr_id):
    """The direction the sibling module's provenance check cannot see.

    It proves every id in the tables appears in the file. This proves the
    converse: every id in the file is in the tables. Only both together mean the
    recovery is complete, and only a complete recovery makes the headline
    finding a measurement rather than a sample.
    """
    section = pre_s6_sections()[fr_id]
    in_source = run_ids_in(section)
    in_tables = (
        set(RECOVERED_EXACT[fr_id])
        | set(RECOVERED_UNDER_ADR_ID[fr_id])
        | set(NOT_IN_EVENT_LOG[fr_id])
    )
    assert in_source == in_tables, (
        f"{fr_id}: the recovered tables and the pre-S6 source disagree.\n"
        f"  in the source but NOT recovered: {sorted(in_source - in_tables)}\n"
        f"  recovered but NOT in the source: {sorted(in_tables - in_source)}"
    )


@pytest.mark.parametrize("fr_id", _FRS)
def test_the_block_count_reconciles_with_the_number_of_run_ids_recovered(fr_id):
    """Why "six blocks" and "five run ids" are both true for FR-01.11.

    Pinned so the published block counts, the reason for each gap, and the
    tables cannot drift apart — and so the gap can never again read as a
    silently dropped run id.
    """
    section = pre_s6_sections()[fr_id]
    expected = BLOCK_RECONCILIATION[fr_id]

    blocks = len(re.findall(r"Refined by", section))
    assert blocks == expected["blocks"], (
        f"{fr_id}: the pre-S6 source has {blocks} 'Refined by' block(s), but "
        f"{expected['blocks']} is published. Reason on record: {expected['reason']}"
    )

    run_ids = run_ids_in(section)
    assert len(run_ids) == expected["run_ids"], (
        f"{fr_id}: {len(run_ids)} distinct run id(s) in the source, "
        f"{expected['run_ids']} recorded."
    )


def test_fr_0114s_published_reason_for_its_gap_is_asserted():
    """FR-01.14's reason had nothing pointing at it — only a 5 == 5 count.

    That count is exactly the check called fragile when arguing for set
    equality: FR-01.14 reconciles 5 blocks to 5 run ids only by coincidence
    (four distinct ids reachable from ``Refined by``, one inline duplicate, plus
    a fifth named by ``Backfilled by``). With
    ``ATTRIBUTIONS_NAMING_NO_RUN_ID["FR-01.14"] = ()`` the sibling loop runs zero
    times, so a section carrying five plain ``Refined by`` blocks would satisfy
    every existing assertion while ADR-110's published explanation was false.

    This asserts the two facts that explanation actually rests on.
    """
    section = pre_s6_sections()["FR-01.14"]

    assert "Backfilled by" in section, (
        "ADR-110 states a separate 'Backfilled by' marker names FR-01.14's "
        "fifth run id; the source no longer contains one, so the published "
        "reason is false."
    )

    refined_lines = "\n".join(
        ln for ln in section.splitlines() if "Refined by" in ln
    )
    from_refined = run_ids_in(refined_lines)
    assert len(from_refined) == 4, (
        f"ADR-110 states four DISTINCT run ids are reachable from FR-01.14's "
        f"'Refined by' blocks (one of the five being an inline cross-reference "
        f"to an id another block owns); the source yields "
        f"{len(from_refined)}: {sorted(from_refined)}."
    )

    all_ids = run_ids_in(section)
    only_backfilled = all_ids - from_refined
    assert len(only_backfilled) == 1, (
        f"exactly one run id should be reachable ONLY via 'Backfilled by'; "
        f"found {sorted(only_backfilled)}."
    )


@pytest.mark.parametrize("fr_id", _FRS)
def test_attributions_naming_no_run_are_still_present_in_the_source(fr_id):
    """FR-01.11's sixth block attributes to ``BP-1``, which is not a run.

    That single fact is the whole of the six-vs-five reconciliation, so it is
    asserted against the source rather than trusted. If the block ever stops
    existing, the recorded reason is stale and the counts need re-deriving.
    """
    section = pre_s6_sections()[fr_id]
    for token in ATTRIBUTIONS_NAMING_NO_RUN_ID[fr_id]:
        assert f"Refined by {token}" in section, (
            f"{fr_id}: recorded as attributing a block to {token!r}, which names "
            f"no run — but the source no longer contains that block, so the "
            f"block-vs-run-id reconciliation no longer holds."
        )
        assert not run_ids_in(token), (
            f"{token!r} is recorded as naming no run, but it parses as a run id."
        )


def test_the_reconciliation_covers_every_requirement_that_was_recovered():
    """No requirement may be recovered without its block count reconciled."""
    assert set(BLOCK_RECONCILIATION) == set(_FRS)
    assert set(ATTRIBUTIONS_NAMING_NO_RUN_ID) == set(_FRS)


def test_the_section_scoping_does_not_run_to_end_of_file():
    """Guard on the helper the completeness check depends on.

    An ``awk``-style range that runs ``### FR-01.14`` to EOF attributes every
    later block to that one requirement — which is how a first count of this
    came back at 22. If the scoping regresses, the equality assertions above
    would start passing against an over-broad section.
    """
    sections = pre_s6_sections()
    assert len(sections) >= 7, "the pre-S6 catalog should hold several FR sections"
    for fr_id, body in sections.items():
        heads = [ln for ln in body.splitlines() if ln.startswith("### ")]
        assert len(heads) == 1, (
            f"{fr_id}'s section contains {len(heads)} '###' headings; it should "
            f"stop at the next one."
        )


def test_an_unreachable_pre_s6_commit_fails_rather_than_skipping(monkeypatch):
    """FIX 3, asserted directly — a mutation cannot reach this branch.

    Injecting a ``pytest.skip`` into the error path proves nothing here, because
    the path only executes when ``git show`` fails, which it does not in a full
    checkout. So the behaviour is driven instead: point the helper at a commit
    that cannot resolve and require a hard failure.

    Six nodes route through ``pre_s6_sections``, including the set-equality
    completeness check that is the entire fix for "was a run id dropped?". A
    skip there would delete all six on any shallow CI clone and report green.
    """
    import _fr_history_docs as docs

    monkeypatch.setattr(docs, "PRE_S6_COMMIT", "0000000000000000000000000000000000000000")

    # `pytest.raises(AssertionError)` is NOT sufficient here. `pytest.skip()`
    # raises `Skipped`, which derives from BaseException, so a reintroduced skip
    # would propagate and skip THIS test — reporting green rather than red, the
    # very invisibility being guarded against. Catching BaseException converts
    # any non-AssertionError outcome into a failure.
    #
    # The message assertions live INSIDE the handler that binds `message`,
    # rather than after the try/except. Both other branches end in
    # `pytest.fail()`, which never returns — but that is a fact about pytest's
    # runtime, not something a reader (or a static analyser) can see locally.
    # Keeping the checks next to the value they inspect makes the binding
    # provable where it is used.
    try:
        docs.pre_s6_sections()
    except AssertionError as exc:
        message = str(exc)
        assert "fetch-depth" in message, (
            "the failure must name the remedy; an unexplained red on a shallow "
            "clone is only marginally better than a silent skip"
        )
        assert "skipping them would report green" in message
    except BaseException as exc:  # noqa: BLE001 - see above
        pytest.fail(
            f"expected a hard AssertionError, got {type(exc).__name__}: {exc}. "
            f"If this is a Skipped, the skip hatch is back and six checks "
            f"vanish silently on a shallow clone."
        )
    else:
        pytest.fail("pre_s6_sections() accepted an unreachable commit")


def test_the_fr_0114_reason_check_would_fail_on_a_section_that_disproved_it():
    """FIX 4's guard, proven to bite — git history cannot be mutated.

    The published reason rests on two facts about the source. If FR-01.14's
    section instead carried five plain ``Refined by`` blocks naming five
    distinct ids, ADR-110's explanation would be false; this shows the
    predicates would say so, rather than passing as the old 5 == 5 count did.
    """
    fabricated = "\n".join(
        f"Refined by `iterate-2026-01-{n:02d}-fake` (something):" for n in range(1, 6)
    )
    assert "Backfilled by" not in fabricated
    refined_lines = "\n".join(
        ln for ln in fabricated.splitlines() if "Refined by" in ln
    )
    assert len(run_ids_in(refined_lines)) == 5, (
        "the fabricated section should expose five distinct ids from 'Refined "
        "by' alone — the shape the published reason denies"
    )
    assert not (run_ids_in(fabricated) - run_ids_in(refined_lines)), (
        "and nothing reachable only via 'Backfilled by'"
    )
