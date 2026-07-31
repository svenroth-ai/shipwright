"""Fail-safe direction of the triage-store primitives (S1 of IT-1).

Each test below pins a failure path that previously either crashed a caller or
lost data while reporting success. The success paths are unchanged and are
covered by the existing ``test_sweep_*`` / ``test_triage_*`` modules.

Run-ID: iterate-2026-07-31-triage-store-failsafe
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.jsonl_records import ends_without_newline, read_jsonl_records  # noqa: E402
from lib.sweep_text import read_text_verbatim  # noqa: E402
from lib.triage_header import ensure_header, has_header  # noqa: E402

#: A lone continuation byte: valid as the tail of a multi-byte sequence, never
#: valid on its own. This is what an append interrupted mid-character leaves.
TRUNCATED_UTF8 = b'{"event":"append","id":"trg-aaaaaaaa","title":"caf\xc3'


# ---------------------------------------------------------------------------
# AC-1 — the sweep readers must not raise on an interrupted append
# ---------------------------------------------------------------------------

def test_read_text_verbatim_survives_truncated_multibyte(tmp_path: Path) -> None:
    """A store truncated mid multi-byte sequence must READ, not crash.

    ``read_text_verbatim`` is called from ``setup_iterate_worktree`` step 5, i.e.
    AFTER ``git worktree add`` has already succeeded — a raise there orphans the
    worktree it just created. Its sibling ``jsonl_records.read_jsonl_records``
    already decodes with ``surrogateescape`` and documents exactly this reason.
    """
    p = tmp_path / "triage.outbox.jsonl"
    p.write_bytes(TRUNCATED_UTF8 + b"\n")

    text = read_text_verbatim(p)  # must not raise UnicodeDecodeError

    assert text.startswith('{"event":"append"')
    # Round-trips back to the ORIGINAL bytes — surrogateescape, not a lossy
    # replacement character, so a repair pass can still recover the real bytes.
    assert text.encode("utf-8", errors="surrogateescape") == TRUNCATED_UTF8 + b"\n"


def test_read_text_verbatim_preserves_crlf_and_adds_no_newline(tmp_path: Path) -> None:
    """The decode change must not disturb the verbatim contract it exists for."""
    p = tmp_path / "t.jsonl"
    p.write_bytes(b'{"a":1}\r\n{"b":2}')
    assert read_text_verbatim(p) == '{"a":1}\r\n{"b":2}'


# ---------------------------------------------------------------------------
# AC-4 — ends_without_newline is PREVENTION, so it must fail CLOSED
# ---------------------------------------------------------------------------

def test_unreadable_file_is_treated_as_unterminated(tmp_path: Path, monkeypatch) -> None:
    """An I/O error must NOT read as "safely appendable".

    The asymmetry is the whole argument: a wrong ``True`` costs one blank line,
    which ``read_jsonl_records`` skips outright. A wrong ``False`` lets the next
    writer append onto the same physical line, and the reader then loses BOTH
    records — the exact corruption this module was created to prevent.
    """
    p = tmp_path / "t.jsonl"
    p.write_bytes(b'{"a":1}\n')

    def boom(*_a, **_k):
        raise OSError(5, "I/O error")

    monkeypatch.setattr(Path, "open", boom)
    assert ends_without_newline(p) is True


def test_missing_and_empty_stay_safely_appendable(tmp_path: Path) -> None:
    """The two states that genuinely ARE appendable must stay False.

    Fail-closed must not become fail-always: a missing or zero-byte file is the
    normal first-append case, and returning True there would inject a leading
    blank line into every freshly created store.
    """
    empty = tmp_path / "empty.jsonl"
    empty.write_bytes(b"")
    assert ends_without_newline(tmp_path / "absent.jsonl") is False
    assert ends_without_newline(empty) is False


def test_blank_line_from_a_defensive_prefix_is_skipped_by_the_reader(tmp_path: Path) -> None:
    """Proves the cost of a wrong ``True`` is genuinely nil, rather than assumed."""
    p = tmp_path / "t.jsonl"
    p.write_bytes(b'{"event":"append","id":"a"}\n\n{"event":"append","id":"b"}\n')
    result = read_jsonl_records(p)
    assert [r["id"] for r in result.records] == ["a", "b"]
    assert result.corrupt == []


# ---------------------------------------------------------------------------
# AC-2 — the header recovery path must not truncate-then-write the tracked SSoT
# ---------------------------------------------------------------------------

def test_ensure_header_prepend_preserves_crlf_bytes(tmp_path: Path) -> None:
    """Prepending a header must not rewrite the whole file's line endings.

    ``read_text``/``write_text`` translate on BOTH sides, so on Windows a CRLF
    store came back as a whole-file LF->CRLF diff — on a ``merge=union`` artifact,
    where a whole-file diff is maximally expensive.
    """
    p = tmp_path / "triage.jsonl"
    body = b'{"event":"append","id":"trg-aaaaaaaa"}\r\n{"event":"append","id":"trg-bbbbbbbb"}\r\n'
    p.write_bytes(body)

    ensure_header(p, schema_version=1, now="2026-07-31T00:00:00Z")

    raw = p.read_bytes()
    assert raw.endswith(body), (
        "the pre-existing bytes were rewritten, not preserved:\n"
        f"{raw!r}"
    )
    assert has_header(p)
    # 3, not 2: the two original records PLUS the header, which now takes the file's
    # own EOL rather than a bare LF. A mixed line 1 would be rewritten by the next
    # reconcile fold — a permanent one-line diff on a merge=union artifact.
    assert raw.count(b"\r\n") == 3, f"line endings were translated: {raw!r}"
    assert b"\n" not in raw.replace(b"\r\n", b""), f"a bare LF crept in: {raw!r}"


def test_ensure_header_prepend_is_atomic(tmp_path: Path, monkeypatch) -> None:
    """A crash during the prepend must leave the ORIGINAL store intact.

    The pre-fix ``write_text`` truncates first, so an interruption left the
    tracked SSoT empty or half-written. With a durable atomic write the rename
    either happened or it did not.
    """
    import lib.triage_header as th

    p = tmp_path / "triage.jsonl"
    original = b'{"event":"append","id":"trg-aaaaaaaa"}\n'
    p.write_bytes(original)

    def boom(*_a, **_k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(th, "_durable_atomic_write", boom)
    with pytest.raises(OSError):
        ensure_header(p, schema_version=1, now="2026-07-31T00:00:00Z")

    assert p.read_bytes() == original, "the store was truncated by a failed prepend"


def test_ensure_header_survives_a_truncated_multibyte_store(tmp_path: Path) -> None:
    """The header check runs on EVERY tracked append and must not crash on the store
    state the rest of this diff exists to survive.

    Found by Stage-2 review: the first cut fixed the WRITE and left `has_header`'s
    strict `read_text` in place one call earlier — so `ensure_header` still raised
    `UnicodeDecodeError` (a `ValueError`, which its `except OSError` never caught),
    straight out through `triage._append_line`, which has no handler. Reproduced
    before fixing: the bad byte was on a line far below the header being inspected.
    """
    p = tmp_path / "triage.jsonl"
    p.write_bytes(TRUNCATED_UTF8 + b"\n")

    assert has_header(p) is False  # must ANSWER, not raise
    ensure_header(p, schema_version=1, now="2026-07-31T00:00:00Z")

    raw = p.read_bytes()
    assert has_header(p)
    assert raw.endswith(TRUNCATED_UTF8 + b"\n"), "the corrupt bytes were not preserved"


def test_ensure_header_takes_the_files_own_eol(tmp_path: Path) -> None:
    """A CRLF store gets a CRLF header line, so line 1 does not become a permanent
    one-line diff against every CRLF record appended after it."""
    p = tmp_path / "triage.jsonl"
    p.write_bytes(b'{"event":"append","id":"trg-a"}\r\n')
    ensure_header(p, schema_version=1, now="2026-07-31T00:00:00Z")
    raw = p.read_bytes()
    assert raw.count(b"\r\n") == 2, raw
    assert b"\n" not in raw.replace(b"\r\n", b""), f"a bare LF crept in: {raw!r}"


def test_bare_json_scalar_first_line_answers_rather_than_raising(tmp_path: Path) -> None:
    """`42` is valid JSON but not a mapping, and `.get` on it raises AttributeError
    past the JSONDecodeError handler. `jsonl_records` treats exactly that shape as a
    recognised corruption fragment, so it is a state the store really reaches."""
    p = tmp_path / "triage.jsonl"
    p.write_bytes(b"42\n")
    assert has_header(p) is False
    ensure_header(p, schema_version=1, now="2026-07-31T00:00:00Z")
    assert has_header(p)
    assert p.read_bytes().endswith(b"42\n")


def test_ensure_header_is_still_idempotent(tmp_path: Path) -> None:
    """The behaviour the function already guaranteed must be unchanged."""
    p = tmp_path / "triage.jsonl"
    ensure_header(p, schema_version=1, now="2026-07-31T00:00:00Z")
    first = p.read_bytes()
    ensure_header(p, schema_version=1, now="2026-07-31T99:99:99Z")
    assert p.read_bytes() == first


def test_quarantine_round_trips_an_undecodable_line(tmp_path: Path) -> None:
    """Row 37's real pin: the quarantine log's own surrogateescape encode.

    Doubt review found the row cited an existing suite with no surrogate case, so the
    `.encode("utf-8", errors="surrogateescape")` in `append_quarantine` was executed
    by nothing. It matters precisely here: a quarantined line reached us through a
    surrogate-escaped read, so a strict encode would crash on exactly the corrupt line
    the quarantine exists to preserve.
    """
    from lib.sweep_quarantine import append_quarantine
    from lib.sweep_text import read_text_verbatim

    corrupt = tmp_path / "outbox.jsonl"
    corrupt.write_bytes(TRUNCATED_UTF8 + b"\n")
    line = read_text_verbatim(corrupt).rstrip("\n")

    qpath = tmp_path / "quarantine.jsonl"
    append_quarantine(qpath, [line], reason="test", now="2026-07-31T00:00:00Z")

    raw = qpath.read_bytes()
    assert b"\xc3" in raw, f"the undecodable byte was not preserved: {raw!r}"
    # Appending again must not lose the first record either.
    append_quarantine(qpath, [line], reason="test", now="2026-07-31T00:00:01Z")
    assert qpath.read_bytes().count(b"\xc3") == 2


def test_created_header_matches_what_the_appender_actually_writes(tmp_path: Path) -> None:
    """Row 48, de-tautologised.

    The previous version asserted `os.linesep` on both sides — and the implementation
    also used `os.linesep`, so it compared the code to itself and would have gone RED
    when someone made `_append_line` correct. This calls the REAL appender and
    compares bytes, so it tracks the coupling rather than the constant.
    """
    import triage

    root = tmp_path
    (root / ".shipwright").mkdir(parents=True)
    triage.append_triage_item(
        root, source="plugin-sync", severity="low", kind="maintenance",
        title="t", detail="d", to_outbox=False,
    )
    raw = (root / ".shipwright" / "triage.jsonl").read_bytes()

    assert b"\r\n" not in raw, f"header/appender disagree on EOL: {raw!r}"
    assert raw.count(b"\n") == 2, f"expected header + one record: {raw!r}"
