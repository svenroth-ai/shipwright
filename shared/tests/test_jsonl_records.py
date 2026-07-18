"""Record-boundary + newline-termination invariants for the append-only triage log.

Regression home for iterate-2026-07-18-outbox-newline-corruption: a record written
without a trailing newline let the next writer append onto the same physical line,
and the tolerant reader dropped BOTH records as a single unparseable line — silent
loss on a log whose entire contract is that nothing is ever lost.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.jsonl_records import (  # noqa: E402
    ends_without_newline,
    read_jsonl_records,
    split_records,
)

APPEND = {"event": "append", "id": "trg-aaaaaaaa", "ts": "2026-07-18T10:00:00Z"}
STATUS = {"event": "status", "id": "trg-aaaaaaaa", "newStatus": "dismissed"}


def _j(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"))


# ---------------------------------------------------------------------------
# ends_without_newline — the writer-side probe (AC1)
# ---------------------------------------------------------------------------

def test_missing_file_is_safely_appendable(tmp_path: Path) -> None:
    assert ends_without_newline(tmp_path / "nope.jsonl") is False


def test_zero_byte_file_is_safely_appendable(tmp_path: Path) -> None:
    p = tmp_path / "empty.jsonl"
    p.write_bytes(b"")
    assert ends_without_newline(p) is False


def test_terminated_file_needs_no_separator(tmp_path: Path) -> None:
    p = tmp_path / "ok.jsonl"
    p.write_bytes(_j(APPEND).encode() + b"\n")
    assert ends_without_newline(p) is False


def test_crlf_terminated_file_counts_as_terminated(tmp_path: Path) -> None:
    """A CRLF-written log is terminated; prefixing another newline would add a blank."""
    p = tmp_path / "crlf.jsonl"
    p.write_bytes(_j(APPEND).encode() + b"\r\n")
    assert ends_without_newline(p) is False


def test_unterminated_file_is_detected(tmp_path: Path) -> None:
    p = tmp_path / "bad.jsonl"
    p.write_bytes(_j(APPEND).encode())  # no trailing newline
    assert ends_without_newline(p) is True


# ---------------------------------------------------------------------------
# split_records — record-boundary recovery (AC2)
# ---------------------------------------------------------------------------

def test_single_record_round_trips(tmp_path: Path) -> None:
    records, remainder = split_records(_j(APPEND))
    assert records == [APPEND]
    assert remainder == ""


def test_two_concatenated_records_both_recovered() -> None:
    """The observed incident: an append and a WebUI status on one physical line."""
    records, remainder = split_records(_j(APPEND) + _j(STATUS))
    assert records == [APPEND, STATUS]
    assert remainder == ""


def test_whitespace_between_concatenated_records_is_skipped() -> None:
    records, remainder = split_records(f"{_j(APPEND)}  \t {_j(STATUS)}")
    assert records == [APPEND, STATUS]
    assert remainder == ""


def test_valid_prefix_survives_an_unrecoverable_tail() -> None:
    """All-or-nothing recovery would re-drop the valid record (external review #1)."""
    line = _j(APPEND) + _j(STATUS) + '{"event":"status","id":'  # truncated third
    records, remainder = split_records(line)
    assert records == [APPEND, STATUS]
    assert remainder == '{"event":"status","id":'


def test_wholly_unrecoverable_line_yields_no_records_and_full_remainder() -> None:
    records, remainder = split_records("not json at all")
    assert records == []
    assert remainder == "not json at all"


def test_non_dict_json_is_a_fragment_not_a_record() -> None:
    """A scalar is valid JSON but not a triage record; callers do raw.get(...)."""
    records, remainder = split_records("123")
    assert records == []
    assert remainder == "123"


def test_blank_line_is_not_corruption() -> None:
    records, remainder = split_records("   ")
    assert records == []
    assert remainder == ""


# ---------------------------------------------------------------------------
# read_jsonl_records — the tolerant reader (AC2 + AC3 + AC5)
# ---------------------------------------------------------------------------

def test_reader_recovers_the_observed_corruption(tmp_path: Path) -> None:
    p = tmp_path / "triage.outbox.jsonl"
    p.write_bytes((_j(APPEND) + _j(STATUS) + "\n").encode())
    result = read_jsonl_records(p)
    assert result.records == [APPEND, STATUS]
    assert result.corrupt == []


def test_reader_reports_unrecoverable_text_as_data(tmp_path: Path) -> None:
    p = tmp_path / "triage.jsonl"
    p.write_bytes((_j(APPEND) + "\n" + "garbage\n").encode())
    result = read_jsonl_records(p)
    assert result.records == [APPEND]
    assert len(result.corrupt) == 1
    frag = result.corrupt[0]
    assert frag.text == "garbage"
    assert frag.line_no == 2
    assert Path(frag.path).name == "triage.jsonl"


def test_reader_preserves_order_across_recovered_and_clean_lines(tmp_path: Path) -> None:
    other = {"event": "append", "id": "trg-bbbbbbbb"}
    p = tmp_path / "t.jsonl"
    p.write_bytes((_j(APPEND) + _j(STATUS) + "\n" + _j(other) + "\n").encode())
    assert read_jsonl_records(p).records == [APPEND, STATUS, other]


def test_missing_file_reads_empty(tmp_path: Path) -> None:
    result = read_jsonl_records(tmp_path / "absent.jsonl")
    assert result.records == []
    assert result.corrupt == []


def test_reader_leaks_no_file_handle(tmp_path: Path, recwarn: pytest.WarningsRecorder) -> None:
    """The pre-fix reader iterated path.open(...) with no context manager."""
    p = tmp_path / "t.jsonl"
    p.write_bytes((_j(APPEND) + "\n").encode())
    read_jsonl_records(p)
    assert not [w for w in recwarn if issubclass(w.category, ResourceWarning)]


def test_leaf_never_prints(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """Reporting belongs at the command boundary, not in a reusable library."""
    p = tmp_path / "t.jsonl"
    p.write_bytes(b"garbage\n")
    read_jsonl_records(p)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


# ---------------------------------------------------------------------------
# Degrade, never blackout (external + code review)
# ---------------------------------------------------------------------------

def test_invalid_utf8_degrades_to_a_fragment_instead_of_raising(tmp_path: Path) -> None:
    """An interrupted write truncates mid multi-byte sequence. A strict decode would
    raise out of every reader — the fail-closed blackout the spec rejected."""
    p = tmp_path / "t.jsonl"
    p.write_bytes(_j(APPEND).encode() + b"\n" + b"\xff\xfe garbage\n")
    result = read_jsonl_records(p)
    assert result.records == [APPEND]
    assert len(result.corrupt) == 1


def test_deeply_nested_blob_does_not_raise_recursionerror() -> None:
    """json's scanner raises RecursionError, which is NOT a ValueError."""
    records, remainder = split_records(_j(APPEND) + "[" * 20000)
    assert records == [APPEND]
    assert remainder.startswith("[")


def test_unicode_whitespace_is_not_accepted_between_records() -> None:
    """str.isspace() would accept NBSP/U+000C; JSON does not."""
    records, remainder = split_records(_j(APPEND) + "\x0c" + _j(STATUS))
    assert records == [APPEND]
    assert remainder == "\x0c" + _j(STATUS)
