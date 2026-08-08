"""Unit tests for ``lib.triage_validate`` — the triage-log validator + orphan-status
classifier extracted from ``churn_merge`` (iterate-2026-06-30-sweep-outbox-quarantine-orphans).

Covers the classifier the outbox sweep relies on to distinguish the recoverable
orphan-status class from genuine corruption, and pins that ``validate_triage_text``'s
string-error API is unchanged (and still re-exported from ``churn_merge``).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.triage_validate import (  # noqa: E402
    TriageValidation,
    classify_triage_text,
    validate_triage_text,
)

HEADER = '{"v":1,"schema":"triage","created":"2026-06-08T00:00:00Z"}'
APPEND = '{"event":"append","id":"trg-a","status":"triage"}'
APPEND_B = '{"event":"append","id":"trg-b","status":"triage"}'
ORPHAN = '{"event":"status","id":"trg-ghost","newStatus":"dismissed"}'
ORPHAN_AMEND = '{"event":"amend","id":"trg-ghost","by":"cli","title":"x"}'
#: The remedy every un-recoverable-fragment message must name, so an operator is
#: never told the log is corrupt without being told what fixes it.
REPAIR_TOOL = "triage_repair.py"


def _log(*lines: str) -> str:
    return "\n".join([HEADER, *lines]) + "\n"


def test_clean_log_has_no_errors() -> None:
    v = classify_triage_text(_log(APPEND))
    assert isinstance(v, TriageValidation)
    assert v.errors == []
    assert v.orphan_status_ids == frozenset()
    assert v.has_non_orphan_error is False


def test_orphan_status_only_is_recoverable() -> None:
    v = classify_triage_text(_log(APPEND, ORPHAN))
    assert v.errors  # the orphan IS reported as an error...
    assert v.orphan_status_ids == frozenset({"trg-ghost"})  # ...but classified recoverable
    assert v.has_non_orphan_error is False


def test_status_with_matching_append_is_clean() -> None:
    # A status whose append exists (order-insensitive) is NOT an orphan.
    paired = '{"event":"status","id":"trg-a","newStatus":"dismissed"}'
    v = classify_triage_text(_log(APPEND, paired))
    assert v.errors == [] and v.orphan_status_ids == frozenset()


def test_invalid_json_is_non_orphan_error() -> None:
    v = classify_triage_text(_log(APPEND, '{"event":"status" BROKEN'))
    assert v.has_non_orphan_error is True


def test_duplicate_append_is_non_orphan_error() -> None:
    v = classify_triage_text(_log(APPEND, APPEND.replace("triage", "open")))
    # two appends, same id, different content (dedup not applied here) → duplicate
    assert v.has_non_orphan_error is True


def test_missing_header_is_non_orphan_error() -> None:
    v = classify_triage_text(APPEND + "\n")  # first line is not the header
    assert v.has_non_orphan_error is True


def test_mixed_orphan_and_corruption_flags_both() -> None:
    v = classify_triage_text(_log(APPEND, ORPHAN, '{"event":"append" BROKEN'))
    assert v.orphan_status_ids == frozenset({"trg-ghost"})
    assert v.has_non_orphan_error is True  # corruption present → caller must hard-block


# --- record-boundary recovery (finding 15) ----------------------------------
#
# The log's one-record-per-line invariant is not enforced at the append
# boundary, so an interrupted or external write leaves two records glued onto
# one physical line. The READER recovers such a line (``split_records``) and the
# event-log twin ``validate_events_text`` was converted in 2026-07-20; this
# validator was not, so one glued line blocked triage delivery permanently while
# the board — reading through the recovering reader — showed the item applied.


def test_concatenated_records_recover() -> None:
    """AC1. Two records on one physical line is a union artefact, not corruption."""
    v = classify_triage_text(_log(APPEND + APPEND_B))

    assert v.errors == [], v.errors
    assert v.has_non_orphan_error is False


def test_header_glued_to_first_event() -> None:
    """AC1. The header is the first RECORD, not the first LINE. The pre-fix code
    consumed the whole first line as 'the header' and skipped whatever rode with it."""
    v = classify_triage_text(HEADER + APPEND + "\n")

    assert v.errors == [], v.errors


def test_deeply_nested_line_is_reported_not_raised() -> None:
    """AC-4 (card trg-57d0d6d3 / P2.19g) — DRIFT PIN, not a red/green fix.

    ``classify_triage_text`` already parses via ``split_records``, which
    explicitly catches ``RecursionError`` at both its own ``json`` call sites
    (``lib/jsonl_records.py`` lines 195, 251) — this function was fixed
    independently by iterate-2026-08-06-triage-validate-deadends, BEFORE this
    card was even filed. This test exists so the two resolvers this card names
    (this one and ``lib.triage_dedup._parsed_append``, fixed in this same run)
    cannot silently diverge again — mirroring AC-5 of
    iterate-2026-08-05-it1-audit-remainder, which did the same thing for the
    ``status``-event resolver pair. This test is expected to ALREADY pass
    before any code in this run changes; it pins existing behaviour, not new.
    """
    deep = '{"a":' * 20000 + "1" + "}" * 20000
    line = f'{{"event":"append","id":"trg-classify-deep","ts":"2026-08-07T00:00:00Z","val":{deep}}}'
    v = classify_triage_text(_log(APPEND, line))

    assert v.has_non_orphan_error is True
    assert any("not valid JSON (unrecoverable fragment)" in e for e in v.errors), v.errors
    assert any(REPAIR_TOOL in e for e in v.errors), v.errors


def test_unrecoverable_fragment_names_the_repair_tool() -> None:
    """AC2. Genuine corruption still blocks — but never without a remedy. The
    pre-fix message said only 'union may have corrupted a historic line'."""
    v = classify_triage_text(_log(APPEND, '{"event":"status" BROKEN'))

    assert v.has_non_orphan_error is True
    assert any(REPAIR_TOOL in e for e in v.errors), v.errors


def test_bare_scalar_line_is_a_fragment() -> None:
    """AC2. A bare scalar is valid JSON but no reader can use it; ``split_records``
    calls it a fragment, so the validator now reports it instead of passing it
    through in silence. Deliberate strictness change — remediable by the tool the
    message names."""
    v = classify_triage_text(_log(APPEND, "123"))

    assert v.has_non_orphan_error is True
    assert any(REPAIR_TOOL in e for e in v.errors), v.errors


def test_duplicate_append_inside_a_glued_line() -> None:
    """AC3. Records hidden inside a concatenated line were invisible to every
    check — the pre-fix parser failed the whole line and saw neither record."""
    v = classify_triage_text(_log(APPEND, APPEND.replace("triage", "open") + APPEND_B))

    assert v.has_non_orphan_error is True
    assert any("duplicate append" in e for e in v.errors), v.errors


def test_orphan_status_inside_a_glued_line() -> None:
    """AC3. Same, for the orphan class: the status is now seen and classified."""
    v = classify_triage_text(_log(APPEND, APPEND_B + ORPHAN))

    assert v.orphan_status_ids == frozenset({"trg-ghost"})
    assert v.has_non_orphan_error is False


def test_triage_validate_boundary_roundtrip() -> None:
    """Round-trip over the record boundary: whatever the reader recovers from a
    physical line is exactly what the validator judges. These two disagreeing on
    identical bytes IS finding 15."""
    from lib.jsonl_records import split_records

    for line in (APPEND, APPEND + APPEND_B, HEADER + APPEND):
        records, remainder = split_records(line)
        clean = classify_triage_text(
            line + "\n" if line.startswith(HEADER) else _log(line)
        )
        assert remainder == ""
        assert records, line
        # The reader recovered every record; the validator raised nothing.
        assert clean.errors == [], (line, clean.errors)


# --- a status with no usable id (finding 18) --------------------------------


def test_status_without_usable_id_is_its_own_class() -> None:
    """AC6. Recorded as an error but NOT as an orphan, so ``decide`` could neither
    quarantine it (selection is by id) nor block-with-a-remedy: a dead end. It is
    now its own class the caller can act on."""
    for bad in (
        '{"event":"status","newStatus":"dismissed"}',        # id missing
        '{"event":"status","id":123,"newStatus":"dismissed"}',  # id not a str
    ):
        v = classify_triage_text(_log(APPEND, bad))

        assert v.unidentified_status is True, bad
        assert v.orphan_status_ids == frozenset(), bad
        assert v.has_non_orphan_error is False, bad
        assert any("usable id" in e for e in v.errors), (bad, v.errors)


def test_unidentified_status_is_absent_from_a_clean_log() -> None:
    assert classify_triage_text(_log(APPEND)).unidentified_status is False


# --- orphan amend (AC11, iterate-2026-08-08-triage-amend-event) -------------
# Mirrors the orphan-status tests above: `orphan_amend_ids` is the SAME
# recoverable class, for the `amend` event kind.


def test_orphan_amend_only_is_recoverable() -> None:
    v = classify_triage_text(_log(APPEND, ORPHAN_AMEND))
    assert v.errors  # the orphan IS reported as an error...
    assert v.orphan_amend_ids == frozenset({"trg-ghost"})  # ...but classified recoverable
    assert v.has_non_orphan_error is False


def test_amend_with_matching_append_is_clean() -> None:
    paired = '{"event":"amend","id":"trg-a","by":"cli","title":"x"}'
    v = classify_triage_text(_log(APPEND, paired))
    assert v.errors == [] and v.orphan_amend_ids == frozenset()


def test_mixed_status_and_amend_orphans_both_classify() -> None:
    """A status orphan and an amend orphan for DIFFERENT ids must both be
    classified into their own set — the two loops must not cross-contaminate."""
    other_amend_orphan = '{"event":"amend","id":"trg-other-ghost","by":"cli","title":"x"}'
    v = classify_triage_text(_log(APPEND, ORPHAN, other_amend_orphan))
    assert v.orphan_status_ids == frozenset({"trg-ghost"})
    assert v.orphan_amend_ids == frozenset({"trg-other-ghost"})
    assert v.has_non_orphan_error is False


def test_orphan_amend_and_status_errors_report_in_file_order() -> None:
    """Stage-2 code review finding 11: the classifier's second pass sweeps
    both referencing kinds in ONE file-order pass, not kind-major — so an
    amend orphan on an earlier line must be reported before a status orphan
    on a later line, matching `validate_triage_text`'s "same order [as] the
    classifier found" promise."""
    other_status_orphan = '{"event":"status","id":"trg-other-ghost","newStatus":"dismissed"}'
    v = classify_triage_text(_log(APPEND, ORPHAN_AMEND, other_status_orphan))
    amend_idx = next(i for i, e in enumerate(v.errors) if "amend for id" in e)
    status_idx = next(i for i, e in enumerate(v.errors) if "status for id" in e)
    assert amend_idx < status_idx, v.errors


def test_amend_without_usable_id_is_its_own_class() -> None:
    for bad in (
        '{"event":"amend","by":"cli","title":"x"}',           # id missing
        '{"event":"amend","id":123,"by":"cli","title":"x"}',  # id not a str
    ):
        v = classify_triage_text(_log(APPEND, bad))

        assert v.unidentified_status is True, bad
        assert v.orphan_amend_ids == frozenset(), bad
        assert v.has_non_orphan_error is False, bad
        assert any("usable id" in e for e in v.errors), (bad, v.errors)


def test_orphan_amend_inside_a_glued_line() -> None:
    v = classify_triage_text(_log(APPEND, APPEND_B + ORPHAN_AMEND))
    assert v.orphan_amend_ids == frozenset({"trg-ghost"})
    assert v.has_non_orphan_error is False


def test_churn_resolver_triage_validation_shift() -> None:
    """R7. ``resolve_churn_conflicts._reconcile_triage`` turns a non-empty error
    list into ``triage_invalid`` and aborts the merge. This change moves exactly
    THREE shapes across that line — pinned so the whole trade is visible rather
    than incidental."""
    # 1. WAS a false abort (the merge resolver's own union produces these), now clean.
    assert validate_triage_text(_log(APPEND + APPEND_B)) == []
    # 2. WAS silently tolerated, now reported — no reader can use a bare scalar.
    assert validate_triage_text(_log(APPEND, "123")) != []
    # 3. WAS reported as a duplicate the dedup can never collapse — i.e. a log that
    #    could never be delivered again — now clean, because a non-str id carries no
    #    identity anywhere (AC13).
    dup_non_str = '{"event":"append","id":7,"status":"triage"}'
    assert validate_triage_text(_log(dup_non_str, dup_non_str.replace("triage", "open"))) == []


def test_validate_triage_text_projects_classifier_strings() -> None:
    text = _log(APPEND, ORPHAN)
    assert validate_triage_text(text) == list(classify_triage_text(text).errors)


def test_validate_triage_text_reexported_from_churn_merge() -> None:
    from lib.churn_merge import classify_triage_text as cm_classify
    from lib.churn_merge import validate_triage_text as cm_validate

    assert cm_validate is validate_triage_text
    assert cm_classify is classify_triage_text
