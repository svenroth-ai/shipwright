"""Corruption must never read as absence — IT-1 audit finding 22.

``triage._iter_raw_lines_at`` warned once per fragment and then **discarded**
``RecordRead.corrupt``, so for every ``read_all_items`` consumer an unrecoverable
span read as absence — the exact invariant ``lib/jsonl_records.py`` declares can
never be violated. ``warnings.warn`` is also globally suppressible, so the one
report that did exist vanished under ``-W ignore`` or any library that installs a
blanket filter.

Part of iterate-2026-08-06-p2-19c-corruption-absence (card ``trg-8652bf24``).
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import triage  # noqa: E402
from lib.triage_integrity import (  # noqa: E402
    format_corruption_notice,
    span_bytes,
    store_corruption,
)


def _j(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"))


def _damaged(tmp_path: Path, name: str = "store.jsonl") -> Path:
    good = {"event": "append", "id": "trg-good0001", "ts": "2026-01-01T00:00:00Z"}
    path = tmp_path / name
    path.write_bytes((_j(good) + "\n" + "}{unrecoverable\n").encode())
    return path


# ---------------------------------------------------------------------------
# Corruption is retrievable as data
# ---------------------------------------------------------------------------

def test_store_corruption_reports_the_damaged_span(tmp_path: Path) -> None:
    fragments = store_corruption(_damaged(tmp_path))
    assert len(fragments) == 1
    assert fragments[0].line_no == 2


def test_store_corruption_spans_every_given_store(tmp_path: Path) -> None:
    """Tracked AND outbox — a consumer asks one question about the whole store."""
    a = _damaged(tmp_path, "triage.jsonl")
    b = _damaged(tmp_path, "triage.outbox.jsonl")
    fragments = store_corruption(a, b)
    assert {Path(f.path).name for f in fragments} == {
        "triage.jsonl", "triage.outbox.jsonl",
    }


def test_store_corruption_tolerates_a_missing_file(tmp_path: Path) -> None:
    assert store_corruption(tmp_path / "absent.jsonl") == []


def test_a_clean_store_reports_nothing(tmp_path: Path) -> None:
    path = tmp_path / "clean.jsonl"
    path.write_bytes(b'{"event":"append","id":"trg-1"}\n')
    assert store_corruption(path) == []
    assert format_corruption_notice(store_corruption(path)) is None


# ---------------------------------------------------------------------------
# The report is not silenceable, and does not echo untrusted bytes
# ---------------------------------------------------------------------------

def test_corruption_notice_survives_a_global_warnings_filter(tmp_path: Path) -> None:
    """``warnings.warn`` was globally suppressible; the replacement must not be."""
    fragments = store_corruption(_damaged(tmp_path))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        notice = format_corruption_notice(fragments)
    assert notice is not None
    assert "store.jsonl" in notice


def test_corruption_notice_names_the_repair_tool(tmp_path: Path) -> None:
    """A gate that blocks must print a repair that runs."""
    notice = format_corruption_notice(store_corruption(_damaged(tmp_path)))
    assert "triage_repair.py" in notice


def test_corruption_notice_never_echoes_the_fragment_bytes(tmp_path: Path) -> None:
    """Untrusted bytes reach an operator terminal; report shape, never content.

    ``read_jsonl_records`` preserves undecodable bytes via ``surrogateescape``, so
    echoing a fragment would put arbitrary bytes — including terminal control
    sequences — on stderr (external plan review, security finding).
    """
    path = tmp_path / "store.jsonl"
    path.write_bytes(b'{"ok":1}\n\x1b[31mDANGER\x07{"broken":\n')
    notice = format_corruption_notice(store_corruption(path))
    assert notice is not None
    assert "DANGER" not in notice
    assert "\x1b" not in notice
    assert "\x07" not in notice


def test_corruption_notice_is_ascii_safe(tmp_path: Path) -> None:
    """It reaches a Windows cp1252 console; a raw non-ASCII byte would raise there."""
    path = tmp_path / "stück.jsonl"
    path.write_bytes(b'{"ok":1}\n{"broken":\n')
    notice = format_corruption_notice(store_corruption(path))
    assert notice is not None
    notice.encode("ascii")


# ---------------------------------------------------------------------------
# The reader keeps its records, and reports through the non-suppressible path
# ---------------------------------------------------------------------------

def test_reader_still_returns_the_valid_neighbour(tmp_path: Path) -> None:
    """Recovering corruption as data must not cost the records around it."""
    path = _damaged(tmp_path)
    rows = triage._iter_raw_lines_at(path)
    assert [r["id"] for r in rows] == ["trg-good0001"]


def test_iter_raw_lines_reports_corruption_to_stderr(tmp_path: Path, capsys) -> None:
    """The one operator notice, on the stream that machine output does not use."""
    triage._iter_raw_lines_at(_damaged(tmp_path))
    captured = capsys.readouterr()
    assert "store.jsonl" in captured.err
    assert captured.out == ""


def test_iter_raw_lines_reports_even_under_a_blanket_warnings_filter(
    tmp_path: Path, capsys,
) -> None:
    """The regression this finding is about: ``-W ignore`` hid the only signal."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        triage._iter_raw_lines_at(_damaged(tmp_path))
    assert "store.jsonl" in capsys.readouterr().err


def test_one_damaged_span_is_announced_once_per_process(tmp_path: Path, capsys) -> None:
    """A single ``list`` reads each store several times; the operator sees it once.

    Repeating the same span four times reads as four separate problems (external
    plan review round 2). Suppression is display-only — ``store_corruption``
    recomputes from the files on every call, so no consumer's view changes.
    """
    path = _damaged(tmp_path, "repeat.jsonl")
    triage._iter_raw_lines_at(path)
    first = capsys.readouterr().err
    assert "repeat.jsonl" in first

    triage._iter_raw_lines_at(path)
    triage._iter_raw_lines_at(path)
    assert capsys.readouterr().err == ""
    # The data channel is unaffected by the display suppression.
    assert len(store_corruption(path)) == 1


def test_the_notice_counts_BYTES_not_code_points(tmp_path: Path) -> None:
    """The contract says "bytes"; ``len(text)`` counts code points.

    A span holding one two-byte UTF-8 character was reported as 1 byte by both the
    stderr notice and the JSON block (external code review).
    """
    path = tmp_path / "store.jsonl"
    path.write_bytes('{"broken":"ü"'.encode("utf-8") + b"\n")
    frag = store_corruption(path)[0]
    assert span_bytes(frag) == len(frag.text.encode("utf-8"))
    assert span_bytes(frag) > len(frag.text)
    assert f"{span_bytes(frag)} bytes" in format_corruption_notice([frag])


def test_the_notice_is_bounded_on_a_badly_damaged_store(tmp_path: Path) -> None:
    """A hostile log must not produce an unbounded stderr report.

    The JSON block was capped from the start; this one was not (external code
    review). The header still carries the TRUE total, so a capped report cannot
    read as a complete one.
    """
    path = tmp_path / "many.jsonl"
    path.write_bytes(b"}{broken\n" * 60)
    notice = format_corruption_notice(store_corruption(path))
    assert "60 unrecoverable span(s)" in notice
    assert "more not shown" in notice
    assert len(notice.splitlines()) < 60


def test_a_clean_store_produces_no_stderr_noise(tmp_path: Path, capsys) -> None:
    path = tmp_path / "clean.jsonl"
    path.write_bytes(b'{"event":"append","id":"trg-1"}\n')
    triage._iter_raw_lines_at(path)
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""
