"""Durable read + separator alphabet — IT-1 audit finding 5.

Part of iterate-2026-08-06-p2-19c-corruption-absence (card ``trg-8652bf24``).
Split from ``test_triage_record_boundary_recovery.py`` at the 300-line limit; that
file keeps the AC1 recovery half.

``read_jsonl_records`` used a bare ``open`` on a file published by
``durable_atomic_write``, so unlocked readers raced the sweep's rewrite instead of
retrying past the Windows delete-pending window. Routing it through
``durable_read_text`` must NOT change which byte sequences separate records —
``str.splitlines()`` breaks on nine characters the old file-handle iteration did
not, and would shatter a valid record holding one of them.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.jsonl_records import read_jsonl_records  # noqa: E402


def _j(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"))



def _damaged_store(tmp_path: Path) -> Path:
    good = {
        "event": "append", "id": "trg-good0001", "ts": "2026-01-01T00:00:00Z",
        "source": "manual", "severity": "low", "kind": "bug",
        "title": "t", "detail": "d", "status": "triage",
    }
    path = tmp_path / "store.jsonl"
    path.write_bytes((_j(good) + "\n" + "}{unrecoverable\n").encode())
    return path


def test_reader_goes_through_the_durable_read_path(tmp_path: Path, monkeypatch) -> None:
    """Pin the call site: a bare ``open`` does not retry the publish window."""
    import lib.jsonl_records as jsonl_records

    seen: list[Path] = []
    real = jsonl_records.durable_read_text

    def spy(path, **kwargs):
        seen.append(Path(path))
        return real(path, **kwargs)

    monkeypatch.setattr(jsonl_records, "durable_read_text", spy)
    path = _damaged_store(tmp_path)
    read_jsonl_records(path)
    assert seen == [path]


def test_record_separators_are_unchanged_by_the_durable_read(tmp_path: Path) -> None:
    """LF / CRLF / lone CR / no-final-newline must split exactly as before.

    Measured equivalence, not assumed: ``str.splitlines()`` would additionally
    break on VT, FF, NEL and U+2028, shattering one valid record into three.
    """
    cases = {
        "lf": b'{"a":1}\n{"b":2}\n',
        "crlf": b'{"a":1}\r\n{"b":2}\r\n',
        "lone_cr": b'{"a":1}\r{"b":2}\r',
        "no_final_newline": b'{"a":1}\n{"b":2}',
    }
    for name, data in cases.items():
        path = tmp_path / f"{name}.jsonl"
        path.write_bytes(data)
        result = read_jsonl_records(path)
        assert [sorted(r) for r in result.records] == [["a"], ["b"]], name
        assert result.corrupt == [], name


def test_raw_control_bytes_stay_on_one_physical_line(tmp_path: Path) -> None:
    """VT and FF must not become record separators.

    A raw control byte inside a JSON string is invalid JSON either way, so the
    discriminating observable is not whether the record decodes — it is how many
    physical lines the span becomes. ``str.splitlines()`` would break here and
    report THREE fragments on three line numbers; the reader must report exactly
    one, on line 1, carrying the span intact.
    """
    path = tmp_path / "vt.jsonl"
    path.write_bytes(b'{"a":"x\x0by\x0cz"}\n')
    result = read_jsonl_records(path)
    assert len(result.corrupt) == 1
    assert result.corrupt[0].line_no == 1
    assert result.corrupt[0].text == '{"a":"x\x0by\x0cz"}'


def test_unicode_line_separator_inside_a_record_does_not_split_it(tmp_path: Path) -> None:
    """U+2028 is legal unescaped in a JSON string, so the record must survive whole.

    The sharpest of the ``splitlines()`` cases: it would shatter a VALID record
    into two undecodable fragments, losing it outright.
    """
    path = tmp_path / "u2028.jsonl"
    path.write_bytes('{"a":"x y"}\n'.encode("utf-8"))
    result = read_jsonl_records(path)
    assert len(result.records) == 1
    assert result.records[0]["a"] == "x y"


def test_undecodable_bytes_still_degrade_to_a_fragment(tmp_path: Path) -> None:
    """surrogateescape must survive the switch — a strict decode would blackout."""
    path = tmp_path / "bad.jsonl"
    path.write_bytes(b'{"a":"\xff\xfe"}\n{"b":2}\n')
    result = read_jsonl_records(path)
    assert any(r.get("b") == 2 for r in result.records)


def test_missing_file_still_reads_empty(tmp_path: Path) -> None:
    result = read_jsonl_records(tmp_path / "absent.jsonl")
    assert result.records == []
    assert result.corrupt == []
